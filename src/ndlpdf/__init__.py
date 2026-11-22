from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Sequence

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ContentStream, NameObject


@dataclass
class OcrConfig:
    ndlocr_cmd: str = "ndlocr-lite"
    device: str = "cpu"
    enable_tcy: bool = False
    dpi: float = 150.0
    visible_text: bool = False
    save_text: bool = False
    save_json: bool = False
    save_xml: bool = False
    skip_existing_text: bool = True
    redo_ocr: bool = False
    overwrite: bool = False
    suffix: str = "_ocr"


def resolve_ndlocr_command(cmd_or_path: str = "ndlocr-lite") -> str:
    """`uv tool install .` で導入された `ndlocr-lite` コマンドを解決する。"""
    found = shutil.which(cmd_or_path)
    if found:
        return found

    # ~/.local/bin/ndlocr-lite など一般的な uv tool bin パスもフォールバック確認
    fallback = Path.home() / ".local" / "bin" / "ndlocr-lite"
    if cmd_or_path == "ndlocr-lite" and fallback.is_file():
        return str(fallback)

    raise RuntimeError(
        f"`{cmd_or_path}` コマンドが見つかりません。\n"
        "NDLOCR-Lite 公式の手順でインストールされているか確認してください:\n"
        "  git clone https://github.com/ndl-lab/ndlocr-lite\n"
        "  cd ndlocr-lite\n"
        "  uv tool install ."
    )


def has_embedded_text(pdf_path: Path) -> bool:
    """PDF にすでにテキストが埋め込まれているか判定する。"""
    try:
        reader = PdfReader(str(pdf_path))
        for page in reader.pages:
            text = (page.extract_text() or "").strip()
            if text:
                return True
    except Exception:
        return False
    return False


def strip_embedded_text_from_pdf(input_pdf: Path, output_pdf: Path) -> None:
    """PDF の各ページから既存の埋め込みテキスト（BT ... ET ブロック）を除去して保存する。

    スキャン画像（XObject Do 等）やベクターグラフィックスはそのまま保持し、
    テキスト描画オペレータのみを取り除くことで、再 OCR 時にテキストが二重に検索されるのを防ぐ。
    """
    reader = PdfReader(str(input_pdf))
    writer = PdfWriter()

    for page in reader.pages:
        writer.add_page(page)

    for page in writer.pages:
        contents = page.get_contents()
        if contents is None:
            continue
        stream = ContentStream(contents, writer)
        new_operations = []
        in_text_block = False
        for operands, operator in stream.operations:
            if operator == b"BT":
                in_text_block = True
                continue
            if operator == b"ET":
                in_text_block = False
                continue
            if in_text_block:
                continue
            if operator in (b"Tj", b"TJ", b"'", b'"'):
                continue
            new_operations.append((operands, operator))
        stream.operations = new_operations
        page[NameObject("/Contents")] = stream

    with output_pdf.open("wb") as wf:
        writer.write(wf)


def get_pdf_page_count(pdf_path: Path) -> int:
    """PDF のページ数を取得する。"""
    try:
        reader = PdfReader(str(pdf_path))
        return len(reader.pages)
    except Exception:
        return 0


def collect_pdf_files(
    inputs: Sequence[str],
    recursive: bool = False,
    exclude_suffix: str | None = None,
) -> list[Path]:
    """指定されたファイルやディレクトリから PDF ファイル一覧を取得する。"""
    pdf_files: list[Path] = []
    seen: set[Path] = set()

    for raw in inputs:
        path = Path(raw).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"入力パスが見つかりません: {path}")

        if path.is_file():
            if path.suffix.lower() != ".pdf":
                raise ValueError(f"PDF ファイルではありません: {path}")
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                pdf_files.append(path)
        elif path.is_dir():
            patterns = ("**/*.pdf", "**/*.PDF") if recursive else ("*.pdf", "*.PDF")
            for pattern in patterns:
                for candidate in sorted(path.glob(pattern)):
                    if candidate.is_file():
                        if (
                            exclude_suffix
                            and candidate.stem.endswith(exclude_suffix)
                        ):
                            continue
                        resolved = candidate.resolve()
                        if resolved not in seen:
                            seen.add(resolved)
                            pdf_files.append(candidate)

    return pdf_files


def resolve_output_pdf_path(
    input_pdf: Path,
    output_arg: str | None,
    multiple_inputs: bool,
    suffix: str,
) -> Path:
    """入力 PDF に対する出力先 PDF パスを決定する。"""
    if output_arg is None:
        return input_pdf.with_name(f"{input_pdf.stem}{suffix}.pdf")

    out_path = Path(output_arg).expanduser()
    if multiple_inputs or out_path.is_dir() or output_arg.endswith(("/", "\\")):
        return out_path / f"{input_pdf.stem}{suffix}.pdf"

    if out_path.suffix.lower() == ".pdf":
        return out_path

    return out_path / f"{input_pdf.stem}{suffix}.pdf"


class NdlOcrPdfProcessor:
    """`ndlocr-lite` CLI コマンドを呼び出して PDF に透明テキストを埋め込むプロセッサ。"""

    def __init__(self, config: OcrConfig):
        self.config = config
        self._ndlocr_bin = resolve_ndlocr_command(config.ndlocr_cmd)

    def process_single_pdf(self, input_pdf: Path, output_pdf: Path) -> dict:
        """1つの PDF ファイルを `ndlocr-lite` で OCR して透明テキスト付き PDF を生成する。"""
        input_resolved = input_pdf.resolve()
        output_resolved = output_pdf.resolve()

        if (
            output_resolved.exists()
            and not self.config.overwrite
            and input_resolved != output_resolved
        ):
            raise FileExistsError(
                f"出力ファイルが既に存在します（上書きする場合は --overwrite を指定してください）: {output_pdf}"
            )

        start_time = time.time()
        output_pdf.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as tmp_dir_str:
            tmp_dir = Path(tmp_dir_str)
            tmp_pdf_output = tmp_dir / f"{input_pdf.stem}_text.pdf"

            # 既に埋め込みテキストがある PDF に対して再 OCR を行う場合、
            # 二重に透明テキストが重なって検索時に2重ヒットするのを防ぐため、
            # 事前に既存のテキストレイヤーを除去した PDF を作成してから OCR に渡す。
            source_pdf_for_ocr = input_pdf
            if has_embedded_text(input_pdf):
                stripped_pdf = tmp_dir / f"{input_pdf.stem}_stripped.pdf"
                strip_embedded_text_from_pdf(input_pdf, stripped_pdf)
                source_pdf_for_ocr = stripped_pdf

            cmd = [
                self._ndlocr_bin,
                "--sourcepdf",
                str(source_pdf_for_ocr),
                "--output",
                str(tmp_dir),
                "--pdf-output",
                str(tmp_pdf_output),
                "--pdf-render-dpi",
                str(self.config.dpi),
                "--no-pdf-page-output",
                "--device",
                self.config.device,
            ]

            if self.config.enable_tcy:
                cmd.append("--enable-tcy")
            if self.config.visible_text:
                cmd.append("--pdf-visible-text")
            if not (self.config.save_text or self.config.save_xml):
                cmd.append("--json-only")

            proc = subprocess.run(cmd)
            if proc.returncode != 0:
                raise RuntimeError(
                    f"ndlocr-lite の実行に失敗しました (終了コード: {proc.returncode})"
                )

            if not tmp_pdf_output.exists():
                raise RuntimeError(
                    f"ndlocr-lite から埋め込み PDF が生成されませんでした: {tmp_pdf_output}"
                )

            shutil.move(str(tmp_pdf_output), str(output_pdf))

            # オプションの副産物出力 (.txt / .json / .xml)
            self._copy_sidecar_files(source_pdf_for_ocr.stem, tmp_dir, output_pdf)

        elapsed = time.time() - start_time
        page_count = get_pdf_page_count(output_pdf)
        return {
            "input_pdf": str(input_pdf),
            "output_pdf": str(output_pdf),
            "page_count": page_count,
            "elapsed_sec": elapsed,
        }

    def _copy_sidecar_files(
        self, input_stem: str, tmp_dir: Path, output_pdf: Path
    ) -> None:
        base_out = output_pdf.with_suffix("")
        ext_flags = [
            (".txt", self.config.save_text),
            (".json", self.config.save_json),
            (".xml", self.config.save_xml),
        ]
        for ext, enabled in ext_flags:
            if not enabled:
                continue
            src_file = tmp_dir / f"{input_stem}{ext}"
            if src_file.exists():
                shutil.move(str(src_file), str(base_out.with_suffix(ext)))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ndlpdf",
        description="NDLOCR-Lite (`ndlocr-lite` コマンド) を使って PDF を OCR し、透明テキストを埋め込んだ検索可能 PDF を作成します。",
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="入力 PDF ファイルまたは PDF が入ったディレクトリ（複数指定可）",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="出力 PDF ファイルパス、または出力先ディレクトリ（省略時は <元ファイル名>_ocr.pdf）",
    )
    parser.add_argument(
        "--suffix",
        type=str,
        default="_ocr",
        help="出力ファイル名に付与するサフィックス（デフォルト: _ocr）",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="入力にディレクトリを指定した場合、サブディレクトリ内の PDF も再帰的に検索する",
    )
    parser.add_argument(
        "--dpi",
        type=float,
        default=150.0,
        help="PDF ページを画像化する際の解像度 DPI（デフォルト: 150.0、高精度にしたい場合は 200〜300）",
    )
    parser.add_argument(
        "--device",
        choices=["cpu", "cuda"],
        default="cpu",
        help="推論デバイス（デフォルト: cpu）",
    )
    parser.add_argument(
        "--enable-tcy",
        action="store_true",
        help="縦書き内の縦中横（新聞など）の認識改善を有効にする",
    )
    parser.add_argument(
        "--visible-text",
        action="store_true",
        help="デバッグ用: 埋め込みテキストを透明ではなく青色文字で可視化して描画する",
    )
    parser.add_argument(
        "--save-text",
        action="store_true",
        help="OCR 結果のプレーンテキスト（.txt）も同時に保存する",
    )
    parser.add_argument(
        "--save-json",
        action="store_true",
        help="OCR 結果の座標付き JSON（.json）も同時に保存する",
    )
    parser.add_argument(
        "--save-xml",
        action="store_true",
        help="OCR 結果の XML（.xml）も同時に保存する",
    )
    parser.add_argument(
        "--skip-existing-text",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="すでにテキストが埋め込まれている PDF は処理をスキップする（デフォルト: 有効）",
    )
    parser.add_argument(
        "--redo-ocr",
        action="store_true",
        help="すでにテキストが埋め込まれている PDF でも、既存のテキストを除去してから再 OCR して置き換える（二重検索を防止）",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="出力先ファイルが既に存在する場合に上書きする",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="元の PDF ファイルを直接テキスト埋め込み PDF で上書きする",
    )
    parser.add_argument(
        "--ndlocr-cmd",
        type=str,
        default="ndlocr-lite",
        help="使用する ndlocr-lite コマンドのパス（デフォルト: ndlocr-lite）",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    try:
        pdf_files = collect_pdf_files(
            args.inputs,
            recursive=args.recursive,
            exclude_suffix=args.suffix if not args.in_place else None,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    if not pdf_files:
        print("[WARN] 処理対象の PDF ファイルが見つかりませんでした。", file=sys.stderr)
        return 1

    skip_existing = args.skip_existing_text and not args.redo_ocr

    config = OcrConfig(
        ndlocr_cmd=args.ndlocr_cmd,
        dpi=args.dpi,
        device=args.device,
        enable_tcy=args.enable_tcy,
        visible_text=args.visible_text,
        save_text=args.save_text,
        save_json=args.save_json,
        save_xml=args.save_xml,
        skip_existing_text=skip_existing,
        redo_ocr=args.redo_ocr,
        overwrite=args.overwrite or args.in_place,
        suffix=args.suffix,
    )

    try:
        processor = NdlOcrPdfProcessor(config)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    multiple_inputs = len(pdf_files) > 1 or any(
        Path(p).expanduser().is_dir() for p in args.inputs
    )

    success_count = 0
    skip_count = 0
    error_count = 0

    for input_pdf in pdf_files:
        if config.skip_existing_text and has_embedded_text(input_pdf):
            print(
                f"[SKIP] 既にテキストが埋め込まれているためスキップしました "
                f"（既存テキストを消去して再OCRする場合は --redo-ocr を指定してください）: {input_pdf}"
            )
            skip_count += 1
            continue

        if args.in_place:
            output_pdf = input_pdf
        else:
            output_pdf = resolve_output_pdf_path(
                input_pdf=input_pdf,
                output_arg=args.output,
                multiple_inputs=multiple_inputs,
                suffix=config.suffix,
            )

        try:
            result = processor.process_single_pdf(input_pdf, output_pdf)
            print(
                f"[OK] {result['output_pdf']} "
                f"({result['page_count']} pages, {result['elapsed_sec']:.1f}s)"
            )
            success_count += 1
        except Exception as exc:
            print(f"[ERROR] {input_pdf}: {exc}", file=sys.stderr)
            error_count += 1

    if len(pdf_files) > 1:
        print(
            f"\n完了: 成功 {success_count} 件 / スキップ {skip_count} 件 / エラー {error_count} 件"
        )

    return 0 if error_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

from pathlib import Path
import subprocess
import tempfile
import unittest

from pypdf import PdfReader

from ndlpdf import (
    collect_pdf_files,
    has_embedded_text,
    main,
    resolve_ndlocr_command,
    resolve_output_pdf_path,
    strip_embedded_text_from_pdf,
)


def _create_test_image_pdf(pdf_path: Path) -> None:
    """テスト用: ndlocr-lite 環境の Python (ReportLab + Pillow) で画像のみの PDF を動的生成する。"""
    ndlocr_bin = Path(resolve_ndlocr_command())
    tool_python = ndlocr_bin.resolve().parent / "python"
    if not tool_python.exists():
        first_line = ndlocr_bin.read_text(encoding="utf-8").splitlines()[0]
        if first_line.startswith("#!"):
            tool_python = Path(first_line[2:].strip())

    script = """
import sys
from io import BytesIO
import pypdfium2
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

buf = BytesIO()
c = canvas.Canvas(buf, pagesize=(400, 120))
pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
c.setFont("HeiseiKakuGo-W5", 24)
c.drawString(20, 60, "国立国会図書館デジタルコレクション")
c.showPage()
c.save()
buf.seek(0)

doc = pypdfium2.PdfDocument(buf.getvalue())
pil_img = doc[0].render(scale=2.0).to_pil().convert("RGB")
pil_img.save(sys.argv[1], "PDF", resolution=150.0)
"""
    subprocess.run([str(tool_python), "-c", script, str(pdf_path)], check=True)


class NdlPdfTests(unittest.TestCase):
    def test_resolve_output_pdf_path(self):
        src = Path("/tmp/example/doc.pdf")
        self.assertEqual(
            resolve_output_pdf_path(src, None, False, "_ocr"),
            Path("/tmp/example/doc_ocr.pdf"),
        )
        self.assertEqual(
            resolve_output_pdf_path(src, "/tmp/custom.pdf", False, "_ocr"),
            Path("/tmp/custom.pdf"),
        )
        self.assertEqual(
            resolve_output_pdf_path(src, "/tmp/outdir/", False, "_ocr"),
            Path("/tmp/outdir/doc_ocr.pdf"),
        )
        self.assertEqual(
            resolve_output_pdf_path(src, "/tmp/outdir", True, "_ocr"),
            Path("/tmp/outdir/doc_ocr.pdf"),
        )

    def test_end_to_end_ocr_and_prevent_duplicate_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            input_pdf = tmp_dir / "sample_scan.pdf"
            output_pdf = tmp_dir / "sample_scan_ocr.pdf"
            redo_pdf = tmp_dir / "sample_scan_redo.pdf"

            _create_test_image_pdf(input_pdf)

            self.assertFalse(has_embedded_text(input_pdf))
            collected = collect_pdf_files([str(tmp_dir)], exclude_suffix="_ocr")
            self.assertEqual(len(collected), 1)

            # 1. 初回 OCR
            exit_code = main(
                [
                    str(input_pdf),
                    "-o",
                    str(output_pdf),
                    "--save-text",
                    "--save-json",
                ]
            )
            self.assertEqual(exit_code, 0)
            self.assertTrue(output_pdf.exists())
            self.assertTrue((tmp_dir / "sample_scan_ocr.txt").exists())
            self.assertTrue((tmp_dir / "sample_scan_ocr.json").exists())

            # 生成された PDF から埋め込みテキストが抽出できることを確認
            self.assertTrue(has_embedded_text(output_pdf))
            reader1 = PdfReader(str(output_pdf))
            extracted1 = reader1.pages[0].extract_text()
            self.assertIn("国立国会図書館", extracted1)
            self.assertEqual(extracted1.count("国立国会図書館"), 1)

            # 2. 既に透明テキストがある PDF を再度デフォルト実行するとスキップされること
            skip_out = tmp_dir / "should_not_be_created.pdf"
            exit_code_skip = main([str(output_pdf), "-o", str(skip_out)])
            self.assertEqual(exit_code_skip, 0)
            self.assertFalse(skip_out.exists())

            # 3. 既存テキストの除去関数単体の検証
            stripped_pdf = tmp_dir / "stripped.pdf"
            strip_embedded_text_from_pdf(output_pdf, stripped_pdf)
            self.assertFalse(has_embedded_text(stripped_pdf))

            # 4. --redo-ocr で再 OCR したときに既存テキストが除去され、二重に埋め込まれないこと
            exit_code_redo = main(
                [str(output_pdf), "-o", str(redo_pdf), "--redo-ocr"]
            )
            self.assertEqual(exit_code_redo, 0)
            self.assertTrue(redo_pdf.exists())
            reader2 = PdfReader(str(redo_pdf))
            extracted2 = reader2.pages[0].extract_text()
            self.assertIn("国立国会図書館", extracted2)
            self.assertEqual(extracted2.count("国立国会図書館"), 1)


if __name__ == "__main__":
    unittest.main()

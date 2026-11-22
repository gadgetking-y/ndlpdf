# ndlpdf

[NDLOCR-Lite](https://github.com/ndl-lab/ndlocr-lite) を `uv tool install .` で導入した環境で、**`ndlocr-lite` コマンドを利用して PDF を OCR し、認識テキストを透明テキストとして埋め込んだ検索可能 PDF（Searchable PDF）を作成する CLI ツール**です。

- **二重埋め込み（二重検索）防止機能**:
  - **デフォルトで自動スキップ**: すでにテキストが埋め込まれている PDF は自動的にスキップします。また、フォルダ一括処理時には出力済みの `*_ocr.pdf` を自動的に除外します。
  - **既存テキストを消去して再 OCR（`--redo-ocr`）**: 既存の透明テキストをやり直したい場合は、`--redo-ocr` を指定すると元の PDF から既存のテキストレイヤー（`BT...ET`）を完全に除去した上で新しい透明テキストを埋め込むため、検索時に同じ箇所が二重にヒットすることがありません。
- **ローカルパスへのハードコードなし**: `uv tool install .` で導入された `ndlocr-lite` コマンドを直接呼び出すため、`ndlocr-lite` のクローン先ディレクトリに依存しません。
- **軽量な依存関係**: プロジェクト自体の依存ライブラリは `pypdf` のみで、`uv sync` が一瞬で完了します。
- **単一 PDF・フォルダ一括処理対応**: `ndlocr-lite` 標準 CLI では中間ファイル出力用の `--output` ディレクトリ指定が必須ですが、本ツールでは一時ディレクトリを自動管理し、目的のテキスト埋め込み PDF のみをシンプルに出力します。

---

## 前提条件（NDLOCR-Lite の uv での導入）

公式リポジトリ（<https://github.com/ndl-lab/ndlocr-lite>）の案内通り、`uv` で `ndlocr-lite` がインストールされている状態で動作します。

```bash
git clone https://github.com/ndl-lab/ndlocr-lite
cd ndlocr-lite
uv tool install .
```

`ndlocr-lite --version` または `ndlocr-lite --help` が実行できる状態であれば準備完了です。

---

## インストール・セットアップ

### `uv tool` で直接インストールする場合（推奨）

GitHub リポジトリから直接インストールすると、どのディレクトリからでも `ndlpdf` コマンドとして実行できます。

```bash
uv tool install git+https://github.com/gadgetking-y/ndlpdf
```

### リポジトリをクローンして使う場合

```bash
git clone https://github.com/gadgetking-y/ndlpdf
cd ndlpdf
uv sync
```

クローンしたディレクトリから `uv tool install .` でコマンド登録することも可能です。

---

## 使い方

### 1. 基本的な使い方（単一 PDF の変換）

```bash
uv run ndlpdf input.pdf
```

デフォルトでは同じフォルダに `input_ocr.pdf` が生成されます（一時ファイルや不要な JSON/XML は残りません）。
※ `input.pdf` にすでにテキストが埋め込まれている場合は自動でスキップされます。

### 2. 既存の透明テキストを消去して再 OCR する（二重検索防止）

すでに別の OCR ソフトや過去の実行で透明テキストが入っている PDF を再 OCR したい場合は `--redo-ocr` を指定します。既存の埋め込みテキストを除去してから新しく透明テキストを埋め込むため、検索時に二重ヒットしません。

```bash
uv run ndlpdf input_with_text.pdf --redo-ocr
```

### 3. 出力ファイル名（または出力先フォルダ）を指定する

```bash
uv run ndlpdf input.pdf -o output.pdf
```

### 4. フォルダ内の PDF を一括変換する

```bash
# input_dir 内のテキスト未埋め込み PDF をすべて OCR し、output_dir に出力
uv run ndlpdf ./input_dir -o ./output_dir

# サブフォルダも含めて再帰的に処理
uv run ndlpdf ./input_dir -r -o ./output_dir
```

### 5. 解像度（DPI）や副産物出力の指定

```bash
# 300 DPI で OCR し、テキストファイル (.txt) も同時に出力
uv run ndlpdf input.pdf --dpi 300 --save-text
```

---

## オプション一覧

| オプション | 説明 |
| --- | --- |
| `inputs` | 入力 PDF ファイルまたはディレクトリ（複数指定可） |
| `-o`, `--output <PATH>` | 出力 PDF ファイルパス、または出力先ディレクトリ（省略時は `<元ファイル名>_ocr.pdf`） |
| `--suffix <STR>` | 出力ファイル名に付与するサフィックス（デフォルト: `_ocr`） |
| `-r`, `--recursive` | ディレクトリ指定時にサブディレクトリ内の PDF も再帰的に検索する |
| `--dpi <FLOAT>` | PDF ページを画像化する際の DPI（デフォルト: `150.0`） |
| `--device {cpu,cuda}` | 推論デバイス（デフォルト: `cpu`） |
| `--enable-tcy` | 縦書き内の縦中横（新聞など）の認識改善を有効にする |
| `--visible-text` | デバッグ用: 埋め込みテキストを透明ではなく青色文字で可視化する |
| `--save-text` | OCR 結果のプレーンテキスト（`.txt`）も同時に保存する |
| `--save-json` | OCR 結果の座標付き JSON（`.json`）も同時に保存する |
| `--save-xml` | OCR 結果の XML（`.xml`）も同時に保存する |
| `--skip-existing-text` / `--no-skip-existing-text` | すでにテキストが埋め込まれている PDF をスキップする（デフォルト: 有効） |
| `--redo-ocr` | すでにテキストが埋め込まれている PDF でも、既存テキストを除去してから再 OCR して置き換える |
| `--overwrite` | 出力先ファイルが既に存在する場合に上書きする |
| `--in-place` | 元の PDF ファイルを直接テキスト埋め込み PDF で上書きする |
| `--ndlocr-cmd <CMD>` | 使用する `ndlocr-lite` コマンド名またはパス（デフォルト: `ndlocr-lite`） |

---

## ライセンス

[MIT License](./LICENSE)

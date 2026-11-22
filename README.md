# ndlpdf

[NDLOCR-Lite](https://github.com/ndl-lab/ndlocr-lite) を `uv tool install .` で導入した環境で、**`ndlocr-lite` コマンドを利用して PDF を OCR し、認識テキストを透明テキストとして埋め込んだ検索可能 PDF（Searchable PDF）を作成する CLI ツール**です。

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

### 2. 出力ファイル名（または出力先フォルダ）を指定する

```bash
uv run ndlpdf input.pdf -o output.pdf
```

### 3. フォルダ内の PDF を一括変換する

```bash
# input_dir 内の PDF をすべて OCR し、output_dir に出力
uv run ndlpdf ./input_dir -o ./output_dir

# サブフォルダも含めて再帰的に処理し、既にテキストがある PDF はスキップ
uv run ndlpdf ./input_dir -r --skip-existing-text -o ./output_dir
```

### 4. 解像度（DPI）や副産物出力の指定

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
| `--skip-existing-text` | すでにテキストが埋め込まれている PDF は処理をスキップする |
| `--overwrite` | 出力先ファイルが既に存在する場合に上書きする |
| `--in-place` | 元の PDF ファイルを直接テキスト埋め込み PDF で上書きする |
| `--ndlocr-cmd <CMD>` | 使用する `ndlocr-lite` コマンド名またはパス（デフォルト: `ndlocr-lite`） |

---

## ライセンス

[MIT License](./LICENSE)


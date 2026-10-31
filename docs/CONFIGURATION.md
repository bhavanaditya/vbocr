# Configuration

All settings are in the `config` folder:

| File | Purpose |
|---|---|
| `config/settings.yaml` | General settings: server, OCR model, output format, column names |
| `config/suppliers.yaml` | Per-supplier adjustments, see [ADDING_SUPPLIERS.md](ADDING_SUPPLIERS.md) |
| `config/settings.local.yaml` | Optional. Settings for **this PC only**, see below |
| `config/item_master.csv` | Optional item list, see [`item_master`](#item_master) |

Edit them with Notepad (or any text editor), save, and **restart the server**.

> YAML files are sensitive to indentation. Use spaces, not tabs, and keep the same
> indentation as the surrounding lines.

To keep the configuration somewhere else, set the environment variable
`VBOCR_CONFIG_DIR=D:\vbocr-config`, or pass `--config D:\vbocr-config` on the command line.

## `settings.local.yaml`: settings for this PC

Put your own changes in `config\settings.local.yaml` instead of editing `settings.yaml`. Only
write the values you change; everything else comes from `settings.yaml`:

```yaml
server:
  host: 0.0.0.0
  api_key: "a-long-secret-only-your-office-knows"
ocr:
  enable_mkldnn: false
```

This file is not part of git and `update.bat` never touches it, so an update keeps your settings.
`install.bat` writes `enable_mkldnn: false` here on PCs that need it.

## `server`

```yaml
server:
  host: 127.0.0.1   # 0.0.0.0 = accept connections from other PCs
  port: 5000
  api_key: ""       # set in settings.local.yaml when other PCs can connect
```

With `api_key` set, scans, the history and `/csv` need the key: the browser page asks for it once,
the VB.NET client sends `VbOcrClient.ApiKey`, curl sends `-H "X-API-Key: ..."`. The server prints a
warning when it is open to other PCs without a key.

## `ocr`

These options are passed directly to PaddleOCR.

```yaml
ocr:
  lang: en
  text_detection_model_name: PP-OCRv6_small_det
  text_recognition_model_name: PP-OCRv6_small_rec
  use_doc_orientation_classify: true
  use_doc_unwarping: false
  use_textline_orientation: true
```

### OCR model size

| Model | Speed | Accuracy | Use when |
|---|---|---|---|
| `PP-OCRv6_small_det` / `PP-OCRv6_small_rec` | Fast | Very good | **Default.** Clear prints and normal phone photos |
| `PP-OCRv6_medium_det` / `PP-OCRv6_medium_rec` | About 2× slower | Best | Faint prints, small fonts, poor photos |
| `PP-OCRv6_tiny_*` | Fastest | Poor on invoices | Not recommended: it misreads digits |

After changing models, run `.venv\Scripts\python.exe -m vbocr setup` once (with internet) to download them.

### Other options

| Option | Default | Effect |
|---|---|---|
| `use_doc_orientation_classify` | `true` | Detects photos taken sideways or upside down and rotates them |
| `use_doc_unwarping` | `false` | Flattens curled or folded paper. Slower, and can blur clean scans |
| `use_textline_orientation` | `true` | Reads individual text lines that are upside down |
| `text_det_limit_side_len` | (PaddleOCR default) | Larger values help with very large images and small text, but are slower |
| `enable_mkldnn` | (not set) | oneDNN = Intel CPU acceleration. Some Windows PCs fail with *ConvertPirAttribute2RuntimeAttribute not support*. VB OCR then switches it off by itself, and `install.bat` saves `enable_mkldnn: false` here so later starts skip the failed attempt. Set it to `false` yourself to force it off |

## `output`

```yaml
output:
  date_format: "%d-%m-%Y"
  include_total_row: true
  fill_date_with_today: false
  quantity_priority: ["total qty", "qty", "quantity", "mtrs", "meters", "pcs", "nos"]
  amount_priority: ["total", "total amt", "total amount", "net amount", "amount", "value", "taxable value"]
```

| Option | Description |
|---|---|
| `date_format` | Format of all dates. `%d-%m-%Y` → `03-01-2026`, `%d/%m/%Y` → `03/01/2026`, `%Y-%m-%d` → `2026-01-03` |
| `include_total_row` | Add the `Total` row at the end of the CSV |
| `fill_date_with_today` | Put today's date in the **Date** column |
| `quantity_priority` | Table columns tried, in order, for **Quantity**. The first that exists in the invoice wins |
| `amount_priority` | Same for **Amount**. To get the amount **before GST**, move `"taxable value"` to the front |

## `header_fields`

The labels printed before each header value on invoices. Matching ignores upper/lower case,
punctuation and the `:` separator. The first label found wins.

```yaml
header_fields:
  invoice_number: ["invoice no", "invoice number", "inv no", "bill no", "ref no"]
  invoice_date: ["invoice date", "inv date", "bill date", "ref date", "dated"]
  po_number: ["po no", "p o no", "po number", "order no", "purchase order no"]
  po_date: ["po date", "p o date", "order date", "purchase order date"]
  lr_booking_date: ["lr date", "l r date", "lr no & date", "lr no and date", "lr booking date"]
  brand: ["brand"]
```

The value can be in the same text (`Invoice No. : HO/123`) or just to the right of the label.
Date fields accept `03-01-2026`, `03/01/2026`, `03.01.26` and `03-Jan-2026`.

## `item_columns`

The table header names for each item column. Matching ignores case, spaces and punctuation,
so `S.No.`, `S No` and `SNO` are the same.

```yaml
item_columns:
  serial: ["s.no", "sl.no", "sr.no", ...]   # used to find the table, required
  sku: ["item", "item code", "sku", ...]
  description: ["description of goods", "description", "particulars", ...]
  ...
```

If a supplier uses a header name that is not listed, add it here (for all suppliers) or in that
supplier's profile.

## `description_patterns`

Splits a combined description into separate columns, using
[regular expressions](https://docs.python.org/3/library/re.html#regular-expression-syntax)
with named groups. Group names must be CSV fields: `brand`, `design_name`, `article_id`, `sku`, `size`, `colour`.

```yaml
description_patterns:
  # RAYMOND/CLASSIQUE/1315177 -> brand, design_name, article_id
  - '^(?P<brand>[^/]+)/(?P<design_name>.+)/(?P<article_id>[^/]+)$'
```

The first matching pattern is used. If none match, the whole description goes to **Design Name**.

## `colour_codes`

Colour abbreviations used at the end of SKU codes. Only used for suppliers whose profile has
`colour_from_sku_suffix`. A code that is not in the list is written as it is. The default list
has 44 common garment colour codes; the ones seen on the Opus Fashions / Maybell invoices are
marked with `*`. Add your suppliers' own codes here.

```yaml
colour_codes:
  BLK: Black
  MST: Mustard
  ...
```

## `pdf`

```yaml
pdf:
  use_text_layer: true
  min_characters: 40
  render_dpi: 200
```

PDFs made by a computer (e-mailed invoices, exported from billing software) contain real text.
VB OCR reads that text directly: exact and much faster than OCR. A page with fewer than
`min_characters` characters is treated as a scanned page and read with OCR at `render_dpi`.
Set `use_text_layer: false` to always use OCR.

## `checks`

```yaml
checks:
  min_confidence: 0.90
  total_labels: ["grand total", "net amount", ...]
  total_tolerance: 1.00
```

- Values the OCR read with confidence below `min_confidence` (0 to 1), and numbers where a letter
  was read as a digit (`l299.00`), are marked **unsure** (amber in the browser and the scan dialog).
- The sum of the item amounts is compared with the amount next to the first of `total_labels`
  found on the invoice. A difference above `total_tolerance` rupees gives a warning. Totals that
  match after adding 3, 5, 12, 18 or 28 % GST also count as a match.

## `history`

```yaml
history:
  enabled: true
  folder: history
  keep_days: 365
  warn_duplicates: true
```

Every scan is saved as a JSON file (values, warnings and CSV) in `history\YYYY-MM\`. Used for
**Recent scans**, for saving corrections, and for the "Already scanned on …" warning when the same
supplier and invoice number comes in again. Scans older than `keep_days` are deleted (0 = keep).
The images themselves are not stored.

## `item_master`

```yaml
item_master:
  file: config/item_master.csv
  overwrite: false
```

An optional list of your items, for example exported from your billing software. When a scanned
SKU is in the list, empty columns (Article ID, Brand Name, Design Name, Size, Cup Size, Colour,
Cost Price, M.R.P) are filled from it. With `overwrite: true` the list also replaces values read
from the invoice.

Copy `config\item_master.example.csv` to `config\item_master.csv` and fill it in. Only the
`SKU No./Item ID.` column is required; other common titles (`SKU`, `Item Code`, `MRP`, `Color`, …)
work too. Comma, semicolon or tab separated. SKUs match ignoring case, spaces and punctuation.
An optional `Supplier` column limits a row to invoices from that supplier. The file is re-read
automatically when it changes.

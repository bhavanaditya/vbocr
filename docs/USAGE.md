# Usage

There are three ways to scan invoices:

| Method | Best for |
|---|---|
| [Browser test page](#1-browser-test-page) | Trying it out, checking a difficult invoice |
| [Command line](#2-command-line) | Batch jobs, scripts, calling from VB.NET without a server |
| [HTTP API](#3-http-api) | The VB.NET application (fastest for repeated scans) |

## Tips for good results

- Photograph the invoice **flat**, in good light, filling the frame.
- Sideways or upside-down photos are fine. They are rotated automatically.
- Keep the **whole item table** in the picture, including the header row (S.No, Item, Qty, ...).
- **Multi-page invoices:** send all pages together in one request. The items are joined into one CSV.
- PDFs work too. Every PDF page is read. Every page of a multi-page TIFF is read too.
- Supported files: `jpg`, `jpeg`, `jfif`, `png`, `bmp`, `tif`, `tiff`, `webp`, `gif`, `pdf`
  (max 25 MB each). PNG screenshots with a transparent background are fine.

## Ways to upload

| How | Browser page | VB.NET dialog | Command line |
|---|---|---|---|
| Choose one or more files | **Files** | **Files...** | `scan.bat a.jpg b.png` |
| A whole folder | **Folder** or drop the folder | **Folder...** or drop the folder | `scan.bat C:\Invoices` or `scan-folder.bat C:\Invoices` |
| Drag and drop | Drop anywhere on the page | Drop on the page list or the dashed box | Drop files on `scan.bat` in Explorer |
| Paste from the clipboard (screenshot, image copied from WhatsApp / browser) | Ctrl+V | **Paste** button or Ctrl+V | — |
| Phone camera | **Camera** (when the page is opened on a phone on the same network) | — | — |
| Wildcards | — | — | `scan.bat "C:\Invoices\*.png" --each` |

**One invoice or many?** Several files can mean two things:

- **Pages of one invoice** (default): the items are joined into **one** CSV. The page order is the list order.
- **Separate invoices**: one CSV per file. Choose *separate invoices* on the browser page, use
  `--each` (or a folder) on the command line, or `VbOcrClient.ScanEach` in VB.NET.

## How long does a scan take?

Scanning runs on the processor (CPU). Times measured with the default `small` model:

| Invoice | Apple M4 CPU |
|---|---|
| 4 item rows, phone photo | about 11 s |
| 28 item rows, full A4 page | about 45 s |

An office PC with a recent Intel Core i5 or Ryzen 5 should be in the same range. Older PCs will be slower.
The first scan after the server starts also includes model loading.
See [CONFIGURATION.md](CONFIGURATION.md#ocr-model-size) to trade speed against accuracy.

---

## 1. Browser test page

1. Start the server: `start-server.bat`
2. Open <http://127.0.0.1:5000>
3. Add the files: **Files**, **Folder**, **Camera**, drag and drop, or paste an image with Ctrl+V.
   Change the order with the arrows or by dragging a page, remove pages with ✕.
4. Choose whether the files are **pages of one invoice** or **separate invoices**.
5. Click **Scan**. The results appear on the right: item count, total quantity, total amount and
   the **printed total** (✓ when the items add up to the total on the invoice, ✗ when a row is
   probably missing or misread), the invoice details, the item table and anything to check.
6. **Check and correct.** Values the OCR was not sure about have an **amber** background. Click any
   value to change it; changed values get a blue mark and the totals update. Delete a wrong row
   with ✕, add a missing one with **+ Row**. **Save corrections** stores them in the scan history.
7. Use **Download CSV** or **Copy** (paste straight into Excel) on each invoice, or **Download all
   (ZIP)** for separate invoices. These always use your corrected values.

**Recent scans** (top right) lists earlier scans, newest first, with a search box (supplier,
invoice number or file name). Click one to open it, correct it again or download its CSV.
When the same supplier and invoice number was scanned before, the result says
"Already scanned on …" with links to the earlier scans.

When the server has an access key (see [CONFIGURATION.md](CONFIGURATION.md#server)), the page asks
for it once and remembers it in this browser.

The status in the top right shows whether the server is **Ready**, still **Loading** the OCR
engine, or **offline**. The page follows the Windows light / dark setting.

## 2. Command line

`scan.bat` works **without** the server running. It loads the OCR engine each time, so it is
slower per file than the server.

```bat
rem One image, CSV saved next to it as bill.csv
scan.bat C:\Invoices\bill.jpg

rem Choose the output file
scan.bat C:\Invoices\bill.jpg -o C:\Output\bill.csv

rem Multi-page invoice (one CSV)
scan.bat C:\Invoices\page1.jpg C:\Invoices\page2.png -o C:\Output\bill.csv

rem Several separate invoices: one CSV next to each image
scan.bat --each C:\Invoices\bill1.jpg C:\Invoices\bill2.png

rem Every image / PDF in a folder, each a separate invoice
scan-folder.bat C:\Invoices
scan-folder.bat C:\Invoices -o C:\Output

rem Wildcards
scan.bat "C:\Invoices\*.png" --each

rem JSON instead of CSV
scan.bat C:\Invoices\bill.jpg --json -o C:\Output\bill.json
```

The full command (useful from scripts or `Process.Start`):

```bat
C:\vbocr\.venv\Scripts\python.exe -m vbocr scan <files, folders or wildcards...> [--each] [-o OUTPUT] [--json] [--config CONFIG_DIR]
```

With `--each` or a folder, `-o` is an output **folder**. Without `-o` the CSVs are saved next to the images.
One file that cannot be read does not stop the others.

You can also drag files onto `scan.bat` (pages of one invoice) or a folder onto `scan-folder.bat`
in Explorer. The window stays open at the end so you can read the result.

| Exit code | Meaning |
|---|---|
| `0` | Success, at least one item found |
| `1` | Read the file, but no items were found (check the warnings) |
| `2` | Input file not found |
| `3` | Error while scanning (with `--each`: at least one file failed). The details are saved in `logs\last-error.txt` |

Warnings (for example `Item 3: missing quantity`) are printed to the error output, prefixed with `WARNING:`.

### Other commands

```bat
.venv\Scripts\python.exe -m vbocr serve [--host HOST] [--port PORT]   rem start the server
.venv\Scripts\python.exe -m vbocr setup                               rem download models
.venv\Scripts\python.exe -m vbocr --version
```

## 3. HTTP API

Base URL: `http://127.0.0.1:5000` (change it in `config/settings.yaml`).

**Access key.** When `server.api_key` is set, every request except `/` and `/health` needs the key
in the header `X-API-Key: <key>` (or `?key=<key>` in the URL). Without it the server answers `401`.

### `GET /health`

Shows whether the server is ready. `status` is `loading` while the OCR engine starts; other
requests then answer `503`.

```json
{"status": "ok", "version": "1.0.0", "key_required": false}
```

### `POST /scan`

Scans one invoice.

| Part | Value |
|---|---|
| Body | `multipart/form-data`, one or more files in the field **`files`** |
| Query `format` | `csv` (default) or `json` |
| Query `mode` | `pages` (default): all files are pages of **one** invoice. `each`: every file is a **separate** invoice |

**`mode=each`** returns, for `format=json`:

```json
{"invoices": [
  {"file": "bill1.jpg", "header": {...}, "items": [...], "warnings": [], "csv": "..."},
  {"file": "bad.png", "error": "ValueError: Cannot read image bad.png: ..."}
]}
```

and for `format=csv` a ZIP file `invoices.zip` with one CSV per file, a `<name>.ERROR.txt` for each
file that failed, and `summary.json`. The headers below are only sent in `pages` mode.

**Response headers**

| Header | Meaning |
|---|---|
| `X-VBOCR-Item-Count` | Number of item rows found |
| `X-VBOCR-Warnings` | Problems found, separated by ` \| `. Only present when there are warnings |
| `X-VBOCR-Unsure` | Values the OCR was not sure about, separated by `;`. `Invoice Number` = a header value, `3:Quantity` = the quantity of item 3 |
| `X-VBOCR-Total-Check` | `status\|items total\|printed total`, e.g. `mismatch\|4741.10\|5743.10`. Status: `ok`, `mismatch`, `not_found`, `no_items` |
| `X-VBOCR-Scan-Id` | ID of the scan in the history (when history is on) |
| `X-VBOCR-Source` | `ocr`, or `pdf-text` when every page was read from a digital PDF's text |

**Status codes**

| Code | Meaning |
|---|---|
| `200` | Scanned (check `X-VBOCR-Item-Count` and warnings) |
| `400` | Unsupported file type, or the image file is damaged |
| `401` | Access key missing or wrong |
| `413` | File larger than 25 MB |
| `422` | No file sent, or wrong `format` value |
| `500` | Unexpected error. See the server window for details |

**Example with curl** (`curl` is included with Windows 10 and 11):

```bat
curl -F "files=@C:\Invoices\bill.jpg" "http://127.0.0.1:5000/scan?format=csv" -o bill.csv
curl -F "files=@page1.jpg" -F "files=@page2.png" "http://127.0.0.1:5000/scan?format=json"
curl -F "files=@bill1.jpg" -F "files=@bill2.png" "http://127.0.0.1:5000/scan?mode=each" -o invoices.zip
```

**JSON response**

```json
{
  "header": {
    "date": "",
    "supplier_name": "Sample Garments Pvt Ltd",
    "po_date": "02-01-2026",
    "po_number": "",
    "lr_booking_date": "",
    "stock_received_date": "",
    "invoice_number": "SG/25-26/0042",
    "invoice_date": "03-01-2026",
    "grn_number": ""
  },
  "items": [
    {
      "sku": "LMN0101MST",
      "article_id": "",
      "brand": "Lumina",
      "design_name": "NIGHTWEAR",
      "size": "",
      "cup_size": "",
      "colour": "Mustard",
      "quantity": "2",
      "cost_price": "669.33",
      "mrp": "999.00",
      "amount": "1335.32"
    }
  ],
  "supplier_profile": "Sample Garments Pvt Ltd",
  "warnings": [],
  "unsure": [{"row": 0, "field": "invoice_number"}, {"row": 3, "field": "quantity"}],
  "total_check": {"status": "ok", "items_total": "4741.10", "printed_total": "4741.10",
                  "label": "Grand Total", "note": ""},
  "scan_id": "20260131-101502-123-SG-25-26-0042",
  "duplicates": [],
  "source": "ocr",
  "csv": ",Date,Supplier Name,..."
}
```

`supplier_profile` is the name of the matching profile in `config/suppliers.yaml`, or empty when the
supplier is unknown. `csv` is the same text that `format=csv` returns. All values are strings. Numbers have thousands separators removed.
In `unsure`, row `0` is a header value and `1` the first item. `duplicates` lists earlier scans of
the same supplier and invoice number (`id`, `scanned`).

### `POST /csv`

Turns a JSON invoice (`header` and `items` as above, for example after the user corrected values)
into the purchase-entry CSV. When the JSON has the `scan_id` of a scan, the corrections are also
saved in the scan history.

```bat
curl -H "Content-Type: application/json" -d @invoice.json http://127.0.0.1:5000/csv -o invoice.csv
```

### `GET /history`

Recent scans, newest first: `{"enabled": true, "scans": [{"id", "scanned", "supplier_name",
"invoice_number", "invoice_date", "items", "amount", "warnings", "files", "corrected"}, ...]}`.
Query `limit` (default 50, max 500) and `q` (search supplier, invoice number, file name).

`GET /history/{id}` returns one saved scan (the JSON above plus `files`, `scanned`, `csv`), and
`GET /history/{id}.csv` its CSV.

Interactive API documentation is available at <http://127.0.0.1:5000/docs> while the server is running.

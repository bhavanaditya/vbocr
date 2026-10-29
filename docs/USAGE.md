# Usage

There are three ways to scan an invoice:

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
- PDFs work too. Every PDF page is read.
- Supported files: `jpg`, `jpeg`, `png`, `bmp`, `tif`, `tiff`, `webp`, `pdf` (max 25 MB each).

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
3. Choose the image file(s), pick **CSV** or **JSON**, and click **Scan**.

## 2. Command line

`scan.bat` works **without** the server running. It loads the OCR engine each time, so it is
slower per file than the server.

```bat
rem One image, CSV saved next to it as bill.csv
scan.bat C:\Invoices\bill.jpg

rem Choose the output file
scan.bat C:\Invoices\bill.jpg -o C:\Output\bill.csv

rem Multi-page invoice
scan.bat C:\Invoices\page1.jpg C:\Invoices\page2.jpg -o C:\Output\bill.csv

rem JSON instead of CSV
scan.bat C:\Invoices\bill.jpg --json -o C:\Output\bill.json
```

The full command (useful from scripts or `Process.Start`):

```bat
C:\vbocr\.venv\Scripts\python.exe -m vbocr scan <files...> [-o OUTPUT] [--json] [--config CONFIG_DIR]
```

| Exit code | Meaning |
|---|---|
| `0` | Success, at least one item found |
| `1` | Read the file, but no items were found (check the warnings) |
| `2` | Input file not found |

Warnings (for example `Item 3: missing quantity`) are printed to the error output, prefixed with `WARNING:`.

### Other commands

```bat
.venv\Scripts\python.exe -m vbocr serve [--host HOST] [--port PORT]   rem start the server
.venv\Scripts\python.exe -m vbocr setup                               rem download models
.venv\Scripts\python.exe -m vbocr --version
```

## 3. HTTP API

Base URL: `http://127.0.0.1:5000` (change it in `config/settings.yaml`).

### `GET /health`

Shows whether the server is ready.

```json
{"status": "ok", "version": "1.0.0"}
```

### `POST /scan`

Scans one invoice.

| Part | Value |
|---|---|
| Body | `multipart/form-data`, one or more files in the field **`files`** |
| Query `format` | `csv` (default) or `json` |

Several files in one request are treated as **pages of the same invoice**.
To scan several separate invoices, send one request per invoice.

**Response headers**

| Header | Meaning |
|---|---|
| `X-VBOCR-Item-Count` | Number of item rows found |
| `X-VBOCR-Warnings` | Problems found, separated by ` \| `. Only present when there are warnings |

**Status codes**

| Code | Meaning |
|---|---|
| `200` | Scanned (check `X-VBOCR-Item-Count` and warnings) |
| `400` | Unsupported file type |
| `413` | File larger than 25 MB |
| `422` | No file sent, or wrong `format` value |
| `500` | Unexpected error. See the server window for details |

**Example with curl** (`curl` is included with Windows 10 and 11):

```bat
curl -F "files=@C:\Invoices\bill.jpg" "http://127.0.0.1:5000/scan?format=csv" -o bill.csv
curl -F "files=@page1.jpg" -F "files=@page2.jpg" "http://127.0.0.1:5000/scan?format=json"
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
  "warnings": []
}
```

`supplier_profile` is the name of the matching profile in `config/suppliers.yaml`, or empty when the
supplier is unknown. All values are strings. Numbers have thousands separators removed.

Interactive API documentation is available at <http://127.0.0.1:5000/docs> while the server is running.

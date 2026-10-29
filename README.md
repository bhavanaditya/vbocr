# VB OCR

Read supplier invoice photos and scans and turn them into a **purchase-entry CSV** for a VB.NET application.

- **Free and open source.** No subscriptions, API keys or per-scan charges.
- **Runs offline** on your own Windows PC. Internet is needed only once, during installation.
- Handles **phone photos**, including sideways and slightly tilted pictures.
- Works with **any supplier layout** that has an item table with a serial-number column.
- Outputs the **exact CSV layout** of the purchase-entry Excel sheet.

Built on [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) (Apache-2.0), [FastAPI](https://fastapi.tiangolo.com/) (MIT) and [Uvicorn](https://www.uvicorn.org/) (BSD).

---

## How it works

```
 ┌────────────────────┐   invoice image    ┌──────────────────────────────┐
 │  VB.NET            │ ─────────────────► │  VB OCR server (this repo)   │
 │  application       │                    │  http://127.0.0.1:5000       │
 │                    │ ◄───────────────── │  PaddleOCR + table reader    │
 └────────────────────┘    CSV / JSON      └──────────────────────────────┘
          both run on the same Windows PC - no internet needed
```

1. The VB.NET app sends the invoice image (or PDF) to the local server.
2. PaddleOCR finds every piece of text and its position on the page.
3. VB OCR rebuilds the item table, reads the header values (invoice number, dates, ...) and maps everything to the purchase-entry columns.
4. The CSV comes back to the VB.NET app for further processing.

## Output

The CSV has the same layout as the purchase-entry Excel sheet:

```csv
,Date,Supplier Name,Purchase Order Date,Purchase Order Number,L.R Booking Date,Stock Received Date,Invoice Number,Invoice Date,GRN Number
,,Sample Garments Pvt Ltd,02-01-2026,,,,SG/25-26/0042,03-01-2026,

Sl.No,SKU No./Item ID.,Article ID,Brand Name,Design Name,Size,Cup Size,Colour,Quantity,Cost Price,M.R.P,Amount
1,LMN0101MST,,Lumina,NIGHTWEAR,,,Mustard,2,669.33,999.00,1335.32
2,LMN0102PUR,,Lumina,NIGHTWEAR,,,Purple,1,669.33,999.00,667.66
...
Total,,,,,,,,60,,,47210.46
```

Values that are never printed on a supplier invoice (**GRN Number**, **Stock Received Date**, **Date**) stay empty so the VB.NET application can fill them in. See [docs/OUTPUT_FORMAT.md](docs/OUTPUT_FORMAT.md) for every column.

## Quick start (Windows)

1. Install **Python 3.11 (64-bit)** from <https://www.python.org/downloads/windows/>.
   Tick **"Add python.exe to PATH"** during setup.
2. Download this repository and extract it, for example to `C:\vbocr`.
3. Double-click **`install.bat`**. It takes 5–10 minutes and downloads about 1 GB once.
4. Double-click **`start-server.bat`** and keep the window open.
5. Open <http://127.0.0.1:5000> in a browser and upload an invoice to test it.

Full instructions: [docs/INSTALLATION.md](docs/INSTALLATION.md)

## Use from VB.NET

Copy [`clients/vbnet/OcrClient.vb`](clients/vbnet/OcrClient.vb) into your project:

```vb
Using client As New OcrClient()
    Await client.EnsureServerRunningAsync("C:\vbocr")
    Dim result = Await client.ScanAsync("C:\Invoices\bill.jpg")
    Dim invoice = InvoiceCsv.Parse(result.Csv)

    Dim invoiceNo = invoice.Header("Invoice Number")
    For Each row As DataRow In invoice.Items.Rows
        Debug.Print(row("SKU No./Item ID.") & "  " & row("Quantity") & "  " & row("Amount"))
    Next
End Using
```

Full guide: [docs/VBNET_INTEGRATION.md](docs/VBNET_INTEGRATION.md)

## Use from the command line

```bat
scan.bat C:\Invoices\bill.jpg
```

This writes `C:\Invoices\bill.csv`. More options are in [docs/USAGE.md](docs/USAGE.md).

## Documentation

| Document | What it covers |
|---|---|
| [INSTALLATION.md](docs/INSTALLATION.md) | Requirements, step-by-step install, running at Windows start-up, updating, uninstalling |
| [USAGE.md](docs/USAGE.md) | Browser test page, command line, HTTP API reference |
| [VBNET_INTEGRATION.md](docs/VBNET_INTEGRATION.md) | Calling VB OCR from a VB.NET application |
| [OUTPUT_FORMAT.md](docs/OUTPUT_FORMAT.md) | CSV and JSON layout, where each value comes from |
| [CONFIGURATION.md](docs/CONFIGURATION.md) | `settings.yaml`: OCR model, date format, column names |
| [ADDING_SUPPLIERS.md](docs/ADDING_SUPPLIERS.md) | Handling a new supplier's invoice format |
| [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common problems and fixes |
| [DEVELOPMENT.md](docs/DEVELOPMENT.md) | Project layout, running tests, how the table reader works |

## Requirements at a glance

| | Minimum | Recommended |
|---|---|---|
| OS | Windows 10 64-bit | Windows 10/11 64-bit |
| CPU | 64-bit with AVX (most PCs from 2013 onwards) | 4+ cores |
| RAM | 4 GB free | 8 GB+ |
| Disk | 2 GB | 3 GB |
| Python | 3.10 – 3.13 (64-bit) | 3.11 |
| Graphics card | Not needed | Not needed |
| Internet | Only during installation | — |

## Licences of the components used

| Component | Licence | Cost |
|---|---|---|
| PaddleOCR / PaddlePaddle | Apache-2.0 | Free, commercial use allowed |
| FastAPI | MIT | Free |
| Uvicorn | BSD-3-Clause | Free |
| PyYAML | MIT | Free |
| Python | PSF | Free |

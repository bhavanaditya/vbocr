# Development

## Project layout

```
vbocr/
├── install.bat, update.bat, start-server.bat, scan.bat, scan-folder.bat,
│   autostart-on.bat, autostart-off.bat        Windows scripts
├── install.sh, start-server.sh                macOS / Linux scripts
├── requirements.txt                           runtime packages (pinned OCR versions)
├── requirements-dev.txt                       + test tools
├── config/
│   ├── settings.yaml                          general settings
│   ├── settings.local.yaml                    this PC's overrides (git-ignored)
│   ├── suppliers.yaml                         supplier profiles
│   └── item_master.example.csv                example item list
├── vbocr/                                     Python package
│   ├── cli.py            command line (scan / serve / setup)
│   ├── server.py         HTTP server (FastAPI)
│   ├── upload.html       browser upload page (files, folder, drag and drop, paste)
│   ├── scanner.py        files in → Invoice / CSV out
│   ├── engine.py         image loading (Pillow) + PaddleOCR wrapper → Page / Word objects
│   ├── pdf.py            digital PDF text layer (pypdfium2); scanned pages rendered for OCR
│   ├── preprocess.py     phone photos: flatten the page, remove shadows
│   ├── watcher.py        watch folder
│   ├── samples.py        test bench with your own invoices
│   ├── table.py          rebuilds the item table from text boxes
│   ├── extractor.py      header values, column mapping, supplier rules, total check, unsure values
│   ├── item_master.py    optional item list that fills empty columns
│   ├── history.py        scan history, duplicate warning
│   ├── csv_output.py     purchase-entry CSV layout
│   ├── config.py         loads the YAML files
│   ├── models.py         data classes
│   └── text_utils.py     number / date clean-up
├── clients/vbnet/                             VB.NET client and scan dialog
├── models/                                    downloaded OCR models (git-ignored)
├── tests/                                     tests (most need no OCR engine)
│   ├── make_test_files.py                     generates test invoices (image, photo, PDFs)
│   ├── test_ocr_end_to_end.py                 real OCR, only with VBOCR_OCR_TESTS=1
│   └── test_samples.py                        your own invoices (samples/), see below
├── clients/vbnet/tests/                       VB.NET build check (.NET 2.0 / 4.5) and client test
├── .github/workflows/ci.yml                   tests on Linux and Windows for every push
└── docs/
```

## Setup

```bash
./install.sh                         # macOS / Linux
# or on Windows:
install.bat
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

## Running the tests

```bash
.venv/bin/python -m pytest tests
```

Most tests use hand-made OCR boxes, so they run in about a second and do not load PaddleOCR.
The end-to-end tests read generated invoices (clean image, transparent PNG, angled photo with a
shadow, upside-down photo, digital and 2-invoice PDFs) with the real engine:

```bat
set VBOCR_OCR_TESTS=1
.venv\Scripts\python.exe -m pytest tests
```

**On every push** GitHub Actions (`.github/workflows/ci.yml`) runs the fast tests on Linux and
Windows, and on a clean Windows machine: `install.bat` (including the oneDNN self-test), all
end-to-end tests, `scan.bat`, the VB.NET build for .NET 2.0 and 4.5, the VB.NET client against a
running server with an access key, `autostart-on/off.bat` and `update.bat`. See the **Actions**
tab on GitHub.

## Testing with your own invoices

The generated invoices cannot show every supplier's layout. Keep a few of your real invoices as
a test bench, and check them after every change or update:

```bat
rem 1. add an invoice (several files = pages of one invoice)
.venv\Scripts\python.exe -m vbocr add-sample C:\Invoices\opus_0042.jpg --name opus-photo

rem 2. open samples\opus-photo\expected.csv in Excel, correct every wrong value, save as CSV

rem 3. any time later
.venv\Scripts\python.exe -m vbocr check-samples
```

`check-samples` reads every sample again and lists each value that differs from `expected.csv`,
with the share of values right. Good samples: one photo and one scan per regular supplier, a
digital PDF, a multi-page invoice, a bad photo (angle, shadow). With `VBOCR_OCR_TESTS=1`,
pytest runs them too (`tests/test_samples.py`); `VBOCR_SAMPLES` points to another folder.

**Do not commit real invoices.** They contain business data. `samples/` and `*.csv` are
git-ignored.

## How the table reader works

PaddleOCR returns each line of text with its bounding box. `table.py` turns those into rows
and columns:

1. **Find the header.** Look for a serial-number header (`S.No`, `Sl.No`, …). Words on the same
   horizontal band become column titles. Titles printed on two lines (`Total` / `Qty`) are
   merged when they overlap horizontally. The band ends above the first item row.
2. **Column boundaries.** Halfway between neighbouring header titles.
3. **Rows.** Every integer under the serial header starts a row (1, 2, 3 …). It stops at a
   break in the sequence, so footer numbers are not mistaken for rows.
4. **Skew.** Cells are placed column by column, moving away from the serial column. Each
   column's row positions are taken from the previous column, so a photo tilted by a few
   degrees still lines up.
5. **Wrapped text.** A line that falls between two rows joins the row above.
6. **Merged boxes.** When OCR joins two neighbouring empty cells into one box
   (`NIGHTWEAR62082100`), it is split again at spaces or letter/digit boundaries.

`extractor.py` then:

- matches a supplier profile using its `match` keywords
- reads header values next to their labels (same text box or the box to the right)
- maps table columns to CSV fields using the name lists in the configuration
- applies description patterns, the default brand and colour codes
- cleans numbers and dates

## Adding a test for a new layout

Copy one of the page builders in `tests/test_extractor.py` (for example `fabric_invoice`) and
enter the boxes with **made-up values**. To see the real boxes for an image:

```python
from vbocr.config import Settings
from vbocr.engine import OcrEngine

page = OcrEngine(Settings().ocr).read("samples/invoice.jpg")[0]
for w in page.words:
    print(round(w.x1), round(w.y1), round(w.x2), round(w.y2), w.text)
```

## Versions

PaddleOCR and PaddlePaddle are pinned in `requirements.txt`, because model names and result
formats change between major versions. Test with real invoices before raising them.

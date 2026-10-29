# Development

## Project layout

```
vbocr/
├── install.bat, start-server.bat, scan.bat    Windows scripts
├── install.sh, start-server.sh                macOS / Linux scripts
├── requirements.txt                           runtime packages (pinned OCR versions)
├── requirements-dev.txt                       + test tools
├── config/
│   ├── settings.yaml                          general settings
│   └── suppliers.yaml                         supplier profiles
├── vbocr/                                     Python package
│   ├── cli.py            command line (scan / serve / setup)
│   ├── server.py         HTTP server (FastAPI)
│   ├── scanner.py        files in → Invoice / CSV out
│   ├── engine.py         PaddleOCR wrapper → Page / Word objects
│   ├── table.py          rebuilds the item table from text boxes
│   ├── extractor.py      header values, column mapping, supplier rules
│   ├── csv_output.py     purchase-entry CSV layout
│   ├── config.py         loads the YAML files
│   ├── models.py         data classes
│   └── text_utils.py     number / date clean-up
├── clients/vbnet/                             VB.NET client and scan dialog
├── models/                                    downloaded OCR models (git-ignored)
├── tests/                                     tests (no OCR engine needed)
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

The tests use hand-made OCR boxes, so they run in under a second and do not load PaddleOCR.
**Do not commit real invoices.** They contain business data. `samples/` and `*.csv` are
git-ignored so you can keep test images locally.

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

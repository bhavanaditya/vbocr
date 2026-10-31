# Troubleshooting

## Installation

### "Python 3.10 - 3.13 (64-bit) was not found"

- Install Python 3.11 **64-bit** from <https://www.python.org/downloads/windows/> and tick
  **"Add python.exe to PATH"**.
- Close and reopen Command Prompt, then run `install.bat` again.
- Check with `py -0`. It lists installed versions; `-64` means 64-bit.

### `pip install` fails with "No matching distribution found for paddlepaddle"

You are using 32-bit Python, or a Python version outside 3.10–3.13. Install Python 3.11 64-bit,
delete the `.venv` folder and run `install.bat` again.

### Installation fails part way (network error, timeout)

Run `install.bat` again. It continues where it stopped. Behind a company proxy, set it first:

```bat
set HTTPS_PROXY=http://proxy.company.local:8080
install.bat
```

### "Filename too long" / path errors

Move the folder to a short path such as `C:\vbocr`.

### Model download fails during `vbocr setup`

The models are downloaded from Hugging Face by default. If that site is blocked, use the
PaddlePaddle mirror instead:

```bat
set PADDLE_PDX_MODEL_SOURCE=BOS
.venv\Scripts\python.exe -m vbocr setup
```

## Starting the server

### Crash on start, "illegal instruction"

The CPU does not support AVX, which PaddlePaddle needs. Use a newer PC (any Intel Core / AMD
Ryzen from the last 10 years).

### "DLL load failed"

Install the **Microsoft Visual C++ Redistributable (x64)**:
<https://aka.ms/vs/17/release/vc_redist.x64.exe>, then restart the PC.

### "Address already in use" / port 5000 busy

Another program is using port 5000, or the server is already running (for example started by
the VB.NET app or Task Scheduler). Either stop the other copy, or change `server.port` in
`config\settings.yaml` and use the same port in `New VbOcrClient("http://127.0.0.1:5001")`.

### `EnsureServerRunning` returns False / "The VB OCR server did not start"

Run `start-server.bat` by hand to see the error message in the window.

### Scan fails with "ConvertPirAttribute2RuntimeAttribute not support" or "onednn_instruction"

This is a bug in PaddlePaddle's oneDNN CPU acceleration on some Intel/AMD Windows PCs. VB OCR now
handles it automatically: it retries without oneDNN and prints
`Retrying without oneDNN CPU acceleration`. To stop it trying oneDNN at every start, run
`install.bat` again (it tests the OCR and saves the setting), or add this line under `ocr:` in
`config\settings.yaml`:

```yaml
  enable_mkldnn: false
```

### The error scrolls off the screen

The command line saves the full error in `logs\last-error.txt` in the VB OCR folder. Send that
file when asking for help.

## Scan results

### PNG / screenshot gives no text or a black image

Fixed: transparent PNGs (for example from the Snipping Tool or a browser) are now put on a white
background before reading. Update VB OCR if you still see this.

### "item table not found"

- The photo must include the table **header row**.
- The serial-number column header is not recognised. Add its name (for example `"Line"`,
  `"No."`) to `item_columns.serial` in `settings.yaml` or the supplier profile.

### Some rows are missing

- Rows are found by the serial number (1, 2, 3 …) in the first column. If a number is unreadable
  (folded paper, pen marks), that row and the rows after it may be missed. Retake the photo.
- Rows numbered with letters (a, b, c) are not supported.

### Values end up in the wrong column

- The photo is strongly tilted. Small tilts are handled, strong ones are not. Hold the phone
  parallel to the paper.
- Two table headers are printed very close together. Try `PP-OCRv6_medium_*` models (see
  [CONFIGURATION.md](CONFIGURATION.md#ocr-model-size)).

### A digit is wrong (8 read as 3, etc.)

- Use better light, avoid shadows, and photograph closer so the table fills the picture.
- Switch to the `medium` models.
- Always compare the CSV **Total** with the total printed on the invoice. A difference means a
  digit was misread.

### Header value (invoice number, date) is empty

The label on the invoice is not in `header_fields`. Add it, see [CONFIGURATION.md](CONFIGURATION.md#header_fields).

### Supplier name is wrong or garbled

Large decorative logos are hard to read. Add a supplier profile with the correct `name`
([ADDING_SUPPLIERS.md](ADDING_SUPPLIERS.md)).

### Scanning is slow

- Make sure the default `small` models are used.
- Use the server rather than `scan.bat`. The server keeps the engine loaded.
- Very large photos (over 4000 px) take longer. Phone cameras at normal resolution are fine.
- Close other heavy programs. OCR uses all CPU cores while scanning.

## Getting help

When reporting a problem, include:

1. The text in the server window, or `logs\last-error.txt`
2. The output of `.venv\Scripts\python.exe -m vbocr --version`
3. The output of `.venv\Scripts\python.exe -m vbocr scan <file> --json`
4. If possible, the invoice image with confidential details covered

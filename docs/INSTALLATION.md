# Installation

This guide installs VB OCR on the **same Windows PC** as the VB.NET application.
Installing it on another PC on the network is covered in [Network use](#network-use) below.

## 1. What you need

### Hardware

| | Minimum | Recommended |
|---|---|---|
| Processor | 64-bit CPU with AVX support (Intel/AMD from about 2013 onwards) | 4 or more cores |
| Memory | 4 GB free RAM | 8 GB or more |
| Disk space | 2 GB | 3 GB |
| Graphics card | Not needed | Not needed |

> **Checking AVX:** almost every Intel Core i3/i5/i7 and AMD Ryzen supports it. Very old
> Pentium/Celeron/Atom CPUs may not. If install works but scanning crashes immediately,
> see [TROUBLESHOOTING.md](TROUBLESHOOTING.md#crash-on-start-illegal-instruction).

### Software (all free)

| Software | Version | Where to get it |
|---|---|---|
| Windows | 10 or 11, **64-bit** | — |
| Python | 3.10, 3.11, 3.12 or 3.13, **64-bit** (3.11 recommended) | <https://www.python.org/downloads/windows/> |
| Microsoft Visual C++ Redistributable | 2015–2022 (x64) | <https://aka.ms/vs/17/release/vc_redist.x64.exe> (usually already installed) |

### Internet

Needed **only during installation**: about 800 MB of Python packages plus about 40 MB of OCR models.
After that, VB OCR works fully offline.

## 2. Install Python

1. Download **Windows installer (64-bit)** for Python 3.11 from <https://www.python.org/downloads/windows/>.
2. Run it and, on the first screen, tick **"Add python.exe to PATH"**.
3. Click **Install Now**.
4. Open **Command Prompt** and check:

   ```bat
   py -3.11 --version
   ```

   It should print `Python 3.11.x`.

## 3. Download VB OCR

**Option A: ZIP download (no Git needed)**

1. Open <https://github.com/bhavanaditya/vbocr>.
2. Click **Code → Download ZIP**.
3. Extract it to **`C:\vbocr`**, so that `C:\vbocr\install.bat` exists.

**Option B: Git**

```bat
git clone https://github.com/bhavanaditya/vbocr.git C:\vbocr
```

> Use a short path without spaces, such as `C:\vbocr`. Very long paths can break the
> package installation on Windows.

## 4. Run the installer

Double-click **`C:\vbocr\install.bat`**, or run it from Command Prompt:

```bat
cd C:\vbocr
install.bat
```

The installer:

1. finds Python 3.10–3.13
2. creates a private Python environment in `C:\vbocr\.venv`, so your other Python programs are not affected
3. installs PaddleOCR, PaddlePaddle, FastAPI, Uvicorn and PyYAML
4. downloads the OCR models to `C:\vbocr\models`, so every Windows user on the PC can use them offline

It finishes with:

```
============================================================
 VB OCR is installed.
```

## 5. Start the server

Double-click **`start-server.bat`**. Wait until you see:

```
... INFO OCR engine ready
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:5000 (Press CTRL+C to quit)
```

The first start takes 10–30 seconds while the OCR models load.

Keep this window open while scanning. Closing it stops the server.

## 6. Test it

1. Open <http://127.0.0.1:5000> in a browser.
2. Choose an invoice image and click **Scan**.
3. A CSV file is downloaded. Open it in Excel and check the values.

Or from Command Prompt:

```bat
cd C:\vbocr
scan.bat C:\Invoices\bill.jpg
```

## 7. Start automatically with Windows (optional)

You can start the server yourself, let the VB.NET app start it, or have Windows start it at log-on.

**Option A: let the VB.NET application start it.**
The scan dialog (`VbOcrScanForm`) and `VbOcrClient.EnsureServerRunning("C:\vbocr")` start the server in the background
when it is not running. See [VBNET_INTEGRATION.md](VBNET_INTEGRATION.md). This is the simplest option.

**Option B: double-click `autostart-on.bat`.**
The server then starts hidden every time you log on to Windows (and right away).
`autostart-off.bat` undoes it. Output goes to `logs\server.log`.

**Option C: start at Windows log-on with Task Scheduler** (for example to run before anyone logs on).

1. Open **Task Scheduler** → **Create Task…**
2. **General** tab: name `VB OCR`, select *Run only when user is logged on*.
3. **Triggers** tab → **New…** → *At log on*.
4. **Actions** tab → **New…**
   - Program: `C:\vbocr\.venv\Scripts\pythonw.exe`
   - Arguments: `-m vbocr serve`
   - Start in: `C:\vbocr`
5. **Settings** tab: untick *Stop the task if it runs longer than…*
6. Click **OK**.

`pythonw.exe` runs the server without a console window. To stop it, end the
`pythonw.exe` process in Task Manager.

## Network use

To run VB OCR on one PC and scan from several PCs:

1. Create `config\settings.local.yaml` with:

   ```yaml
   server:
     host: 0.0.0.0
     port: 5000
     api_key: "a-long-secret-only-your-office-knows"
   ```

   With the key, other PCs can only scan or see the scan history when they know it.

2. Allow the port through Windows Firewall (Command Prompt **as Administrator**):

   ```bat
   netsh advfirewall firewall add rule name="VB OCR" dir=in action=allow protocol=TCP localport=5000
   ```

3. In the VB.NET app, use the server PC's address:
   `New VbOcrClient("http://192.168.1.20:5000")` and `client.ApiKey = "..."`
   (or set `ServerUrl` and `ApiKey` on `VbOcrScanForm`). In the browser, open
   `http://192.168.1.20:5000`; it asks for the key once.

> The traffic is plain HTTP. Only open the server on a trusted office network, never to the internet.

## Updating

Double-click **`update.bat`**. It stops a running server, downloads the newest version
(`git pull`, when the folder was installed with git), updates the Python packages and runs the
test read again. Then start the server again.

Your `config\settings.local.yaml`, `config\item_master.csv` and `history` folder are kept.
If you changed `config\settings.yaml` or `config\suppliers.yaml` yourself, back them up first
(and move your settings to `settings.local.yaml`, which updates never touch).

If you used the ZIP download, extract the new ZIP over the old folder, then run `update.bat`.

The test read at the end checks PaddlePaddle's oneDNN acceleration. On PCs where it fails, it
prints `saved enable_mkldnn: false` and writes that setting into `config\settings.local.yaml`.

## Uninstalling

1. Stop the server (close its window, or end `pythonw.exe` in Task Manager).
2. Delete `C:\vbocr`.
3. Remove the Task Scheduler task if you created one.

## macOS / Linux (for development)

```bash
./install.sh
./start-server.sh
```

The same Python version range applies.

# VB.NET integration

Reference for the VB.NET client. For a click-by-click walkthrough of adding a **Scan Invoice**
button to an existing application, see [INTEGRATE_EXISTING_APP.md](INTEGRATE_EXISTING_APP.md).

| File | What it is |
|---|---|
| [`clients/vbnet/VbOcrClient.vb`](../clients/vbnet/VbOcrClient.vb) | `VbOcrClient` (talks to VB OCR) and `VbOcrInvoice` (CSV → header values + `DataTable`) |
| [`clients/vbnet/VbOcrScanForm.vb`](../clients/vbnet/VbOcrScanForm.vb) | Ready-made **Scan invoice** dialog: choose files, scan, check and correct values, OK |

## Compatibility

| | Supported |
|---|---|
| Visual Studio | 2008 or later, including **VS 2017** |
| .NET | Framework **2.0 – 4.8**, including **4.5**, and .NET 6 / 8 for Windows |
| Project settings | `Option Strict On` or Off, `Option Infer` On or Off |
| Platform | x86, x64 or AnyCPU. The OCR runs in its own process, so your app's bitness does not matter |
| References | None to add. Uses only `System`, `System.Data`, `System.Windows.Forms`, `System.Drawing` and `Microsoft.VisualBasic`, which every WinForms project already has |
| NuGet packages | None |

**Verified:**

- Both files and all code samples from these guides compile with **0 errors and 0 warnings** for
  .NET Framework 4.5 / VB 15 (Visual Studio 2017) with `Option Strict On`, `Option Infer Off`,
  warnings treated as errors and an x86 target. They also compile for .NET Framework 2.0 / VB 9 (VS 2008).
- `VbOcrClient` and `VbOcrInvoice` were run against a live VB OCR server: scanning JPG and PNG
  (including transparent PNG), multi-page scans mixing JPG and PNG, `ScanEach` on a folder with a
  damaged image and a non-image file, error messages, CSV parsing and write-back, and number/date conversion on a PC set to a
  German number format (`,` as the decimal point).
- The dialog (`VbOcrScanForm`) compiles but has not been opened on Windows yet. Try it once
  during the test step: adding files, a folder, pasting, drag and drop, and the page order.

All class names start with `VbOcr`, so they will not clash with classes already in your project.
The files have no `Namespace`, so they end up in your project's root namespace.

## 1. Add the files to your project

1. Copy `VbOcrClient.vb` and `VbOcrScanForm.vb` into your project folder.
2. In Visual Studio 2017: **Solution Explorer → right-click the project → Add → Existing Item…**
   and select both files.
3. **Build → Rebuild Solution**.

`VbOcrScanForm.vb` is built entirely in code (no `.Designer.vb` or `.resx`). If your project is
not a Windows Forms application, add only `VbOcrClient.vb`.

## 2. Easiest way: the ready-made dialog

Put this behind a button or menu item, for example *Purchase → Scan supplier invoice*:

```vb
Private Sub btnScanInvoice_Click(sender As Object, e As EventArgs) Handles btnScanInvoice.Click
    Using dlg As New VbOcrScanForm()
        dlg.InstallFolder = "C:\vbocr"      ' where VB OCR is installed (default)
        If dlg.ShowDialog(Me) <> DialogResult.OK Then Return

        Dim invoice As VbOcrInvoice = dlg.Invoice

        ' ---- header ----
        txtSupplier.Text = invoice.GetHeader("Supplier Name")
        txtInvoiceNo.Text = invoice.GetHeader("Invoice Number")
        Dim invDate As DateTime
        If VbOcrInvoice.TryToDate(invoice.GetHeader("Invoice Date"), invDate) Then
            dtpInvoiceDate.Value = invDate
        End If

        ' ---- items ----
        For Each row As DataRow In invoice.Items.Rows
            Dim sku As String = CStr(row("SKU No./Item ID."))
            Dim qty As Decimal = VbOcrInvoice.ToDecimal(row("Quantity"))
            Dim cost As Decimal = VbOcrInvoice.ToDecimal(row("Cost Price"))
            Dim mrp As Decimal = VbOcrInvoice.ToDecimal(row("M.R.P"))
            Dim amount As Decimal = VbOcrInvoice.ToDecimal(row("Amount"))
            ' add to your purchase-entry grid / database here
        Next
    End Using
End Sub
```

The dialog uses the same indigo colour scheme as the browser page. On the left are the page list
and a preview of the selected page. On the right are a coloured status bar (blue = info,
green = all good, amber = please check, red = error), tiles for item count, total quantity and
total amount, the invoice details and the item table. The user adds the invoice pages in any of
these ways, then clicks **Scan**:

| Way | How |
|---|---|
| **Files...** | Select one or more files (jpg, png, bmp, tif, webp, gif, pdf) |
| **Folder...** | Every image / PDF in the folder, sorted by name |
| **Paste** or Ctrl+V | An image copied to the clipboard (Print Screen / Snipping Tool screenshot, image copied from WhatsApp Desktop or a browser), or files copied in Explorer |
| Drag and drop | Drop files or folders from Explorer onto the page list |

All listed files are pages of **one** invoice, scanned in list order. **Up** / **Down** change the
order, **Remove** (or the Delete key) and **Clear** take pages out. Files that are not images or
PDFs are skipped with a message. Pasted images are saved as temporary PNG files and deleted when
the dialog closes.

The dialog also:

- starts the VB OCR server in the background if it is not running (no window appears)
- scans on a background thread, so your application does not freeze
- shows the header values and items in editable grids, so the user can correct a misread value
- shows the total quantity and amount (in Indian number format, e.g. ₹ 1,23,456.00), updated
  as the user corrects values or deletes rows, to compare with the total printed on the invoice
- shows a preview of the selected page, so values can be checked against the picture
- returns the corrected values in `dlg.Invoice`

To scan files your application already has (for example from a scanner folder), set them
before opening the dialog and it starts at once:

```vb
dlg.FilesToScan = New String() {"C:\Scans\bill_p1.jpg", "C:\Scans\bill_p2.png"}
```

Or pre-fill the page list without scanning yet (files and folders both work):

```vb
dlg.AddFiles(New String() {"C:\Scans"})
```

After OK, `dlg.Files` returns the scanned files in page order, for example to archive them.

### Many separate invoices at once

The dialog is for one invoice. To process a pile of invoices (one per file), use
`VbOcrClient.ScanEach` on a background thread:

```vb
Dim client As New VbOcrClient()
client.EnsureServerRunning("C:\vbocr")
Dim files() As String = VbOcrClient.GetInvoiceFiles("C:\Scans\Today")
For Each result As VbOcrResult In client.ScanEach(files)
    If result.ErrorMessage.Length > 0 Then
        ' this file could not be read; the others are still processed
        Console.WriteLine(Path.GetFileName(result.SourceFile) & ": " & result.ErrorMessage)
        Continue For
    End If
    File.WriteAllText(Path.ChangeExtension(result.SourceFile, ".csv"), result.Csv, New System.Text.UTF8Encoding(True))
    For Each row As DataRow In result.Invoice.Items.Rows
        Dim qty As Decimal = VbOcrInvoice.ToDecimal(row("Quantity"))
    Next
Next
```

## 3. Without the dialog: `VbOcrClient`

`VbOcrClient` is synchronous. Run it on a background thread so the screen does not freeze.
With .NET 4.5 you can use `Async`/`Await` with `Task.Run`:

```vb
Private Async Sub btnScan_Click(sender As Object, e As EventArgs) Handles btnScan.Click
    btnScan.Enabled = False
    Try
        Dim path As String = "C:\Invoices\bill.jpg"
        Dim result As VbOcrResult = Await Task.Run(Function() ScanInvoice(path))

        DataGridView1.DataSource = result.Invoice.Items
        lblInvoiceNo.Text = result.Invoice.GetHeader("Invoice Number")
        If result.Warnings <> "" Then MessageBox.Show("Please check: " & result.Warnings)
    Catch ex As VbOcrException
        MessageBox.Show(ex.Message, "Scan invoice", MessageBoxButtons.OK, MessageBoxIcon.Error)
    Finally
        btnScan.Enabled = True
    End Try
End Sub

Private Function ScanInvoice(path As String) As VbOcrResult
    Dim client As New VbOcrClient()               ' http://127.0.0.1:5000
    If Not client.EnsureServerRunning("C:\vbocr") Then
        Throw New VbOcrException("VB OCR server did not start. Run C:\vbocr\start-server.bat to see why.")
    End If
    Return client.Scan(path)                      ' several paths = several pages
End Function
```

Add `Imports System.Threading.Tasks` at the top of the file for `Task.Run`.

### Start the server when your application starts (optional)

The first start of the server takes 10–30 seconds. To hide that wait, start it in the background
when your application opens, for example in the main form's `Load` event:

```vb
Private Sub MainForm_Load(sender As Object, e As EventArgs) Handles MyBase.Load
    Threading.ThreadPool.QueueUserWorkItem(AddressOf StartOcrServer)
End Sub

Private Sub StartOcrServer(state As Object)
    Try
        Dim client As New VbOcrClient()
        client.EnsureServerRunning("C:\vbocr")
    Catch ex As Exception
        ' VB OCR not installed on this PC - scanning will show the error later
    End Try
End Sub
```

The server keeps running after your application closes, so the next start is instant. It uses
almost no CPU while idle.

## 4. API reference

### `VbOcrClient`

| Member | Description |
|---|---|
| `New()` / `New(serverUrl)` | Default `http://127.0.0.1:5000`. Use e.g. `http://192.168.1.20:5000` for a server on another PC |
| `TimeoutSeconds` | Maximum time for one scan, default 300 |
| `IsReady() As Boolean` | `True` when the server is running and ready |
| `EnsureServerRunning(installFolder [, timeoutSeconds])` | Starts the server hidden if needed and waits until it is ready (default 120 s). Local server only |
| `Scan(ParamArray files()) As VbOcrResult` | Scans one invoice. Several files = several pages |
| `ScanEach(ParamArray files()) As VbOcrResult()` | Scans every file as a **separate** invoice. One result per file; a file that fails sets `ErrorMessage` instead of throwing |
| `Shared GetInvoiceFiles(folder) As String()` | All supported files in a folder, sorted by name |
| `Shared IsSupportedFile(path) As Boolean` | `True` for jpg, jpeg, jpe, jfif, png, bmp, tif, tiff, webp, gif, pdf |
| `Shared SupportedExtensions` / `FileDialogFilter` | The supported extensions, and a ready-made `OpenFileDialog.Filter` |
| `ScanToFile(outputCsv, ParamArray files())` | Same, and saves the CSV (UTF-8 with BOM, opens correctly in Excel) |
| `Shared ScanWithoutServer(installFolder, ParamArray files())` | Scans by running the command line instead of the server. Slower: the engine loads every time |

All problems (server not running, not installed, file not found, scan failed) throw
`VbOcrException` with a readable message.

### `VbOcrResult`

| Field | Description |
|---|---|
| `Invoice` | The parsed `VbOcrInvoice` |
| `Csv` | The raw CSV text |
| `ItemCount` | Number of items found |
| `Warnings` | `""`, or problems such as `Item 3: missing quantity` |
| `SourceFile` | `ScanEach` only: the file this result is for |
| `ErrorMessage` | `ScanEach` only: why the file failed, `""` when it worked. `Invoice` is `Nothing` then |

### `VbOcrInvoice`

| Member | Description |
|---|---|
| `Header` | `Dictionary(Of String, String)`. Keys are the titles in `HeaderTitles`, not case-sensitive |
| `GetHeader(title)` | Header value, or `""` |
| `Items` | `DataTable`. Columns are the titles in `ItemTitles`, all `String`. No `Total` row |
| `HeaderTitles`, `ItemTitles` | The CSV titles, in order |
| `Shared Parse(csv)` | CSV text → `VbOcrInvoice` |
| `ToCsv()` | Back to CSV in the same layout, with the Total row recalculated. Use it after corrections or after filling GRN Number |
| `Shared ToDecimal(value)` | `"1335.32"` → `1335.32D`. Always reads `.` as the decimal point, whatever the PC's regional settings. Empty → `0` |
| `Shared TryToDate(value, ByRef result)` | `"03-01-2026"` → `DateTime`. Returns `False` when empty |

Header titles: `Date`, `Supplier Name`, `Purchase Order Date`, `Purchase Order Number`,
`L.R Booking Date`, `Stock Received Date`, `Invoice Number`, `Invoice Date`, `GRN Number`.

Item titles: `Sl.No`, `SKU No./Item ID.`, `Article ID`, `Brand Name`, `Design Name`, `Size`,
`Cup Size`, `Colour`, `Quantity`, `Cost Price`, `M.R.P`, `Amount`.

> **Always convert numbers with `VbOcrInvoice.ToDecimal`**, not `CDec` or `Val`. On a PC set to a
> regional format that uses `,` as the decimal separator, `CDec("1335.32")` gives the wrong value.

## 5. Values that are not on the invoice

Suppliers do not print **GRN Number**, **Stock Received Date** or the entry **Date**, so these
are empty. Fill them in your application:

```vb
invoice.Header("GRN Number") = txtGrn.Text
invoice.Header("Stock Received Date") = DateTime.Today.ToString("dd-MM-yyyy")
IO.File.WriteAllText("C:\Output\bill.csv", invoice.ToCsv(), New Text.UTF8Encoding(True))
```

## 6. Checklist before going live

- [ ] VB OCR installed on the PC (`C:\vbocr\install.bat` finished without errors)
- [ ] `C:\vbocr\start-server.bat` starts and <http://127.0.0.1:5000> opens in the browser
- [ ] Both `.vb` files added to the project, and **Rebuild Solution** succeeds
- [ ] A test scan of an invoice from each regular supplier gives the right values
- [ ] Users check the total against the printed invoice total before saving

## Troubleshooting

| Message | Cause / fix |
|---|---|
| `VB OCR is not installed in C:\vbocr` | Wrong `InstallFolder`, or `install.bat` was not run |
| `Cannot reach the VB OCR server ...` | Server not running. Use `EnsureServerRunning`, or run `start-server.bat` |
| `The VB OCR server did not start` | Run `C:\vbocr\start-server.bat` by hand and read the error in the window |
| `Unsupported file type` | Only jpg, jpeg, jpe, jfif, png, bmp, tif, tiff, webp, gif and pdf are accepted |
| `VB OCR server error 400: Cannot read image ...` | The file is damaged or is not really an image (for example a renamed file). Open it in Paint to check |
| Timeout after 300 s | Very large image or slow PC. Increase `TimeoutSeconds`, or use smaller photos |
| Build warning `SYSLIB0014` (only on .NET 6/8) | Harmless. `HttpWebRequest` is used so that the same file also works on .NET Framework |

More in [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

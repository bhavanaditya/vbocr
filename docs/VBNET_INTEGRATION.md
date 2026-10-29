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
| Visual Studio | 2005 or later, including **VS 2017** |
| .NET | Framework **2.0 – 4.8**, including **4.5**, and .NET 6 / 8 for Windows |
| Project settings | `Option Strict On` or Off, `Option Infer` On or Off |
| Platform | x86, x64 or AnyCPU. The OCR runs in its own process, so your app's bitness does not matter |
| References | None to add. Uses only `System`, `System.Data`, `System.Windows.Forms`, `System.Drawing` and `Microsoft.VisualBasic`, which every WinForms project already has |
| NuGet packages | None |

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

The dialog:

- starts the VB OCR server in the background if it is not running (no window appears)
- scans on a background thread, so your application does not freeze
- shows the header values and items in editable grids, so the user can correct a misread value
- shows the total quantity and amount, to compare with the total printed on the invoice
- returns the corrected values in `dlg.Invoice`

To scan files your application already has (for example from a scanner folder), set them
before opening the dialog and it starts at once:

```vb
dlg.FilesToScan = New String() {"C:\Scans\bill_p1.jpg", "C:\Scans\bill_p2.jpg"}
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
| `VB OCR server error 400: Unsupported file type` | Only jpg, jpeg, png, bmp, tif, tiff, webp and pdf are accepted |
| Timeout after 300 s | Very large image or slow PC. Increase `TimeoutSeconds`, or use smaller photos |
| Build warning `SYSLIB0014` (only on .NET 6/8) | Harmless. `HttpWebRequest` is used so that the same file also works on .NET Framework |

More in [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

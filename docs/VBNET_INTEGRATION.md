# VB.NET integration

The ready-made client is in [`clients/vbnet`](../clients/vbnet):

| File | Contents |
|---|---|
| `OcrClient.vb` | `OcrClient` (talks to the server), `InvoiceCsv.Parse` (CSV → header + `DataTable`) |
| `ExampleForm.vb` | Example Windows Forms screen: pick files, scan, show items in a grid |

## Requirements

- .NET Framework **4.7.2 or later**, or .NET 6 / 8
- On .NET Framework, add a reference to **System.Net.Http** (Project → Add Reference → Assemblies)
- VB OCR installed on the PC (see [INSTALLATION.md](INSTALLATION.md))

## 1. Add the client to your project

1. Copy `clients\vbnet\OcrClient.vb` into your project folder.
2. In Visual Studio: **Project → Add Existing Item… → OcrClient.vb**.

## 2. Scan an invoice

```vb
Imports System.Data

Private Async Function ImportInvoiceAsync(imagePath As String) As Task
    Using client As New OcrClient()   ' default: http://127.0.0.1:5000

        ' Starts the server in the background if it is not running yet
        If Not Await client.EnsureServerRunningAsync("C:\vbocr") Then
            MessageBox.Show("OCR server did not start. Run C:\vbocr\start-server.bat to see why.")
            Return
        End If

        Dim result As OcrResult = Await client.ScanAsync(imagePath)
        Dim invoice As InvoiceData = InvoiceCsv.Parse(result.Csv)

        ' Header values
        Dim supplier = invoice.Header("Supplier Name")
        Dim invoiceNo = invoice.Header("Invoice Number")
        Dim invoiceDate = invoice.Header("Invoice Date")    ' dd-MM-yyyy

        ' Item rows
        For Each row As DataRow In invoice.Items.Rows
            Dim sku = CStr(row("SKU No./Item ID."))
            Dim qty = Decimal.Parse(CStr(row("Quantity")), Globalization.CultureInfo.InvariantCulture)
            Dim amount = CStr(row("Amount"))
            ' ... save to your database
        Next

        If result.Warnings <> "" Then
            MessageBox.Show("Please check: " & result.Warnings)
        End If
    End Using
End Function
```

### Multi-page invoice

```vb
Dim result = Await client.ScanAsync("C:\Invoices\page1.jpg", "C:\Invoices\page2.jpg")
```

### Save the CSV to a file

```vb
Await client.ScanToFileAsync("C:\Output\bill.csv", "C:\Invoices\bill.jpg")
```

### Show the items in a grid

```vb
DataGridView1.DataSource = invoice.Items
```

## 3. API of `OcrClient`

| Member | Description |
|---|---|
| `New(Optional baseUrl As String = "http://127.0.0.1:5000")` | Use another address for a server on the network |
| `IsReadyAsync() As Task(Of Boolean)` | `True` when the server is running and the OCR engine is loaded |
| `EnsureServerRunningAsync(installFolder, Optional timeoutSeconds = 120)` | Starts `installFolder\.venv\Scripts\pythonw.exe -m vbocr serve` without a window if needed, then waits until ready |
| `ScanAsync(ParamArray filePaths()) As Task(Of OcrResult)` | Scans one invoice (several files = several pages) |
| `ScanToFileAsync(outputCsvPath, ParamArray filePaths())` | Same, and saves the CSV as UTF-8 with BOM (opens correctly in Excel) |

`OcrResult`:

| Property | Description |
|---|---|
| `Csv` | CSV text, see [OUTPUT_FORMAT.md](OUTPUT_FORMAT.md) |
| `ItemCount` | Number of items found |
| `Warnings` | Empty, or problems such as `Item 3: missing quantity` |

`InvoiceCsv.Parse(csv)` returns `InvoiceData`:

| Property | Description |
|---|---|
| `Header` | `Dictionary(Of String, String)` keyed by the CSV header titles (case-insensitive) |
| `Items` | `DataTable` with the item columns, all `String`. The `Total` row is left out |

Errors from the server throw `InvalidOperationException` with the server's message.
A server that is not running throws `HttpRequestException`.

## 4. Without the server (command line)

If you prefer not to run a server, call the command line from VB.NET. It is slower,
because the OCR engine loads on every call.

```vb
Imports System.Diagnostics

Public Function ScanWithCommandLine(imagePath As String, csvPath As String) As Boolean
    Dim info As New ProcessStartInfo("C:\vbocr\.venv\Scripts\python.exe") With {
        .Arguments = String.Format("-m vbocr scan ""{0}"" -o ""{1}""", imagePath, csvPath),
        .WorkingDirectory = "C:\vbocr",
        .UseShellExecute = False,
        .CreateNoWindow = True,
        .RedirectStandardError = True
    }
    Using p = Process.Start(info)
        Dim errors = p.StandardError.ReadToEnd()
        p.WaitForExit()
        Return p.ExitCode = 0   ' 0 = OK, 1 = no items found, 2 = file not found
    End Using
End Function
```

## 5. Filling the values not on the invoice

The CSV leaves these columns empty because suppliers do not print them:

- **Date**: the entry date (or enable `fill_date_with_today` in `settings.yaml`)
- **Stock Received Date**
- **GRN Number**
- **L.R Booking Date**: filled only when the invoice prints an LR date

Set them in your application before saving:

```vb
invoice.Header("GRN Number") = txtGrn.Text
invoice.Header("Stock Received Date") = dtpReceived.Value.ToString("dd-MM-yyyy")
```

## 6. Always let the user check

OCR is very accurate on clear prints, but a blurred photo can still give a wrong digit.
Show the scanned values in an editable grid before saving them, and compare the **Total**
with the invoice total printed on the paper.

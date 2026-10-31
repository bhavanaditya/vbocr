# Step-by-step: add invoice scanning to your existing VB.NET application

This guide is written for an application built with **Visual Studio 2017** on
**.NET Framework 4.5**. It works the same way for other versions (VS 2008+, .NET 2.0+); the
code samples split long lines without `_`, which needs VS 2010 or later.

At the end, your purchase-entry screen will have a **Scan Invoice** button that:

1. lets the user pick the invoice photo(s)
2. reads them with VB OCR
3. shows the result so the user can check and correct it
4. fills your purchase-entry screen, ready to save as usual

Nothing in your existing code is replaced. You add two files and one button.

```
 Purchase Entry screen                   VB OCR (C:\vbocr, same PC)
 ┌───────────────────────────┐
 │ [Scan Invoice]  ──────────┼──► VbOcrScanForm ──► VbOcrClient ──► http://127.0.0.1:5000
 │                           │          │
 │ Supplier  [__________]  ◄─┼──────────┘  checked values
 │ Invoice No[__________]    │
 │ grid of items           ◄─┤
 │                 [Save]    │   ← your existing save code
 └───────────────────────────┘
```

---

## Step 1. Install VB OCR on the development PC

Follow [INSTALLATION.md](INSTALLATION.md) steps 1–6. In short:

1. Install Python 3.11 (64-bit) and tick **Add python.exe to PATH**.
2. Extract this repository to `C:\vbocr`.
3. Run `C:\vbocr\install.bat`.
4. Run `C:\vbocr\start-server.bat`, open <http://127.0.0.1:5000> and test-scan one invoice.

**Do not continue until the browser test gives a correct CSV.** Then close the server window.
Your application will start the server itself.

## Step 2. Back up your project

Commit your project to source control, or copy the whole solution folder (for example
`PurchaseApp` → `PurchaseApp_backup`). The following steps only add files, but a backup costs nothing.

## Step 3. Add the two VB OCR files to the project

1. Copy these two files from `C:\vbocr\clients\vbnet\` into your project folder (where your
   other `.vb` files are):
   - `VbOcrClient.vb`
   - `VbOcrScanForm.vb`
2. Open your solution in Visual Studio 2017.
3. In **Solution Explorer**, right-click your project → **Add** → **Existing Item…**
4. Select both files → **Add**.
5. **Build** → **Rebuild Solution**. It must finish with **0 errors**.

Notes:

- `VbOcrScanForm.vb` appears in Solution Explorer as a form. **Do not open it in the designer**:
  it is built in code and has no designer file. Open it with **right-click → View Code** if needed.
- No references or NuGet packages need to be added.
- If the build reports that a name already exists, see [Troubleshooting](#troubleshooting).

## Step 4. Add a "Scan Invoice" button to the purchase-entry form

1. Open your purchase-entry form in the designer, for example `frmPurchaseEntry.vb`.
2. From the **Toolbox**, drag a **Button** onto the form.
3. In **Properties**, set:
   - `(Name)`: `btnScanInvoice`
   - `Text`: `Scan Invoice`
4. Double-click the button. Visual Studio creates `btnScanInvoice_Click`.

## Step 5. Open the scan dialog and fill your form

Paste this into the click handler. Then change the control names (`txtSupplierName`,
`dgvItems`, …) to the ones your form uses. The table after the code lists every value you can use.

```vb
Private Sub btnScanInvoice_Click(sender As Object, e As EventArgs) Handles btnScanInvoice.Click
    Using dlg As New VbOcrScanForm()
        dlg.InstallFolder = "C:\vbocr"
        If dlg.ShowDialog(Me) <> DialogResult.OK Then Return

        Dim invoice As VbOcrInvoice = dlg.Invoice

        ' ---------- header ----------
        txtSupplierName.Text = invoice.GetHeader("Supplier Name")
        txtInvoiceNo.Text = invoice.GetHeader("Invoice Number")
        txtPONumber.Text = invoice.GetHeader("Purchase Order Number")

        Dim d As DateTime
        If VbOcrInvoice.TryToDate(invoice.GetHeader("Invoice Date"), d) Then dtpInvoiceDate.Value = d
        If VbOcrInvoice.TryToDate(invoice.GetHeader("Purchase Order Date"), d) Then dtpPODate.Value = d
        If VbOcrInvoice.TryToDate(invoice.GetHeader("L.R Booking Date"), d) Then dtpLRDate.Value = d

        ' ---------- items ----------
        dgvItems.Rows.Clear()
        For Each row As DataRow In invoice.Items.Rows
            dgvItems.Rows.Add(
                row("Sl.No"),
                row("SKU No./Item ID."),
                row("Article ID"),
                row("Brand Name"),
                row("Design Name"),
                row("Size"),
                row("Cup Size"),
                row("Colour"),
                VbOcrInvoice.ToDecimal(row("Quantity")),
                VbOcrInvoice.ToDecimal(row("Cost Price")),
                VbOcrInvoice.ToDecimal(row("M.R.P")),
                VbOcrInvoice.ToDecimal(row("Amount")))
        Next

        ' Recalculate your totals the way the form normally does, e.g.:
        ' CalculateTotals()
    End Using
End Sub
```

The `dgvItems.Rows.Add(...)` call assumes the grid's columns are in the same order as the
purchase-entry sheet. If your grid has different columns, set cells by column name instead:

```vb
        For Each row As DataRow In invoice.Items.Rows
            Dim i As Integer = dgvItems.Rows.Add()
            dgvItems.Rows(i).Cells("colSKU").Value = row("SKU No./Item ID.")
            dgvItems.Rows(i).Cells("colQty").Value = VbOcrInvoice.ToDecimal(row("Quantity"))
            dgvItems.Rows(i).Cells("colRate").Value = VbOcrInvoice.ToDecimal(row("Cost Price"))
            dgvItems.Rows(i).Cells("colMRP").Value = VbOcrInvoice.ToDecimal(row("M.R.P"))
            dgvItems.Rows(i).Cells("colAmount").Value = VbOcrInvoice.ToDecimal(row("Amount"))
        Next
```

If your grid is bound to a `DataTable` (`dgvItems.DataSource = dtItems`), add rows to that
table instead:

```vb
        For Each row As DataRow In invoice.Items.Rows
            Dim r As DataRow = dtItems.NewRow()
            r("ItemCode") = row("SKU No./Item ID.")
            r("Qty") = VbOcrInvoice.ToDecimal(row("Quantity"))
            r("Rate") = VbOcrInvoice.ToDecimal(row("Cost Price"))
            dtItems.Rows.Add(r)
        Next
```

### Values you can use

| From | Name | Type to convert to |
|---|---|---|
| `invoice.GetHeader(...)` | `Supplier Name`, `Invoice Number`, `Purchase Order Number` | `String` |
| `invoice.GetHeader(...)` | `Invoice Date`, `Purchase Order Date`, `L.R Booking Date` | `DateTime` via `VbOcrInvoice.TryToDate` |
| `invoice.GetHeader(...)` | `Date`, `Stock Received Date`, `GRN Number` | Always empty. Your application fills these |
| `row(...)` in `invoice.Items.Rows` | `Sl.No`, `SKU No./Item ID.`, `Article ID`, `Brand Name`, `Design Name`, `Size`, `Cup Size`, `Colour` | `String` |
| `row(...)` in `invoice.Items.Rows` | `Quantity`, `Cost Price`, `M.R.P`, `Amount` | `Decimal` via `VbOcrInvoice.ToDecimal` |

> Always use `VbOcrInvoice.ToDecimal` and `VbOcrInvoice.TryToDate`. They give the same result
> on every PC, whatever its regional settings. `CDec("1335.32")` fails on a PC set to a
> European number format.

## Step 6. Match the supplier and items to your master data

OCR gives the supplier **name** and item **codes** as printed. Your database probably uses IDs.
Look them up before saving, using your existing lookup code:

```vb
' Supplier: find by name. Ask the user to pick one when not found.
Dim supplierId As Integer = FindSupplierIdByName(invoice.GetHeader("Supplier Name"))
If supplierId = 0 Then
    MessageBox.Show("Supplier '" & invoice.GetHeader("Supplier Name") & "' not found. Please select it.")
    cboSupplier.Focus()
End If

' Items: find by SKU / item code. Mark rows that are not in the item master.
For Each gridRow As DataGridViewRow In dgvItems.Rows
    If gridRow.IsNewRow Then Continue For
    Dim sku As String = Convert.ToString(gridRow.Cells("colSKU").Value)
    If Not ItemExists(sku) Then gridRow.DefaultCellStyle.BackColor = Color.MistyRose
Next
```

`FindSupplierIdByName` and `ItemExists` stand for your own functions. To make the supplier name
always match your master exactly, set the `name` in `C:\vbocr\config\suppliers.yaml` to the name
used in your database (see [ADDING_SUPPLIERS.md](ADDING_SUPPLIERS.md)).

## Step 7. Fill the values that are not printed on the invoice

```vb
txtGRNNo.Text = GetNextGrnNumber()               ' your existing GRN numbering
dtpStockReceived.Value = DateTime.Today
dtpEntryDate.Value = DateTime.Today
```

## Step 8. Save with your existing Save button

Nothing changes here. The form now holds the scanned values, and the user presses your normal
**Save**. Your validation and database code run as usual.

If you also want to keep the scanned CSV (for audit, or to import elsewhere):

```vb
Dim csvFolder As String = "D:\PurchaseScans"
IO.Directory.CreateDirectory(csvFolder)
invoice.Header("GRN Number") = txtGRNNo.Text
invoice.Header("Stock Received Date") = dtpStockReceived.Value.ToString("dd-MM-yyyy")
IO.File.WriteAllText(IO.Path.Combine(csvFolder, txtGRNNo.Text & ".csv"),
                     invoice.ToCsv(), New System.Text.UTF8Encoding(True))
```

For that, keep `invoice` in a form-level variable (`Private _scannedInvoice As VbOcrInvoice`)
instead of the local one in Step 5.

## Step 9. Start the server when the application opens (recommended)

The first scan has to wait 10–30 seconds while the server starts. To avoid the wait, start it
in the background when your application opens. Add this to your **main form** (MDI parent or
start-up form):

```vb
Private Sub frmMain_Load(sender As Object, e As EventArgs) Handles MyBase.Load
    ' ... your existing Load code ...
    Threading.ThreadPool.QueueUserWorkItem(AddressOf StartVbOcr)
End Sub

Private Sub StartVbOcr(state As Object)
    Try
        Dim client As New VbOcrClient()
        client.EnsureServerRunning("C:\vbocr")
    Catch ex As Exception
        ' VB OCR not installed on this PC: scanning shows a clear message when used.
    End Try
End Sub
```

This never blocks or slows down the start of your application.

## Step 10. Test

| Test | Expected |
|---|---|
| Click **Scan Invoice** → Cancel | Nothing changes on the form |
| Scan a clear invoice from a regular supplier | Header and items filled. Totals match the printed invoice |
| Scan a phone photo taken sideways | Same result as a straight photo |
| Scan a 2-page invoice (add both files, check the order) | All items from both pages |
| Scan a PNG screenshot, using **Paste (Ctrl+V)** after Print Screen / Snipping Tool | Same as a JPG |
| Drag a file and a folder from Explorer onto the page list | Both added; non-image files skipped with a message |
| Correct a value in the dialog, then OK | The corrected value appears on the form |
| Close `pythonw.exe` in Task Manager, then scan | Server starts automatically, then the scan works |
| Rename `C:\vbocr` temporarily, then scan | Message *"VB OCR is not installed in C:\vbocr"*, application keeps working |
| Save the scanned purchase | Saved exactly like a hand-entered purchase |

## Step 11. Roll out to the other PCs

On **each PC** where purchases are entered:

1. Install Python 3.11 (64-bit) with **Add python.exe to PATH**.
2. Copy the `C:\vbocr` folder from the development PC, **without** `.venv` (it is tied to
   one PC). Keep `models` and `config`.
3. Run `C:\vbocr\install.bat` (needs internet once).
4. Install the new build of your application as usual.

**Alternative: one OCR PC for the whole office.** Install VB OCR on one PC only, set it up for
network use ([INSTALLATION.md](INSTALLATION.md#network-use)), and point the application at it:

```vb
dlg.ServerUrl = "http://192.168.1.20:5000"    ' IP address of the OCR PC
```

That PC must be switched on, with the server running (start it with Task Scheduler,
[INSTALLATION.md](INSTALLATION.md#7-start-automatically-with-windows-optional)). Store the
address in your application's settings (`My.Settings`) rather than in code.

## Step 12. Make the paths configurable (recommended)

Instead of writing `C:\vbocr` in code, add two settings:
**Project → Properties → Settings**:

| Name | Type | Scope | Value |
|---|---|---|---|
| `VbOcrFolder` | String | Application | `C:\vbocr` |
| `VbOcrServerUrl` | String | Application | `http://127.0.0.1:5000` |

Then:

```vb
dlg.InstallFolder = My.Settings.VbOcrFolder
dlg.ServerUrl = My.Settings.VbOcrServerUrl
```

They can then be changed per PC in `YourApp.exe.config` without rebuilding.

---

## Undoing the integration

Remove the button and its click handler, remove the two files from the project
(**right-click → Exclude From Project**), and rebuild. Your application is back to how it was.
VB OCR can stay installed or be removed ([INSTALLATION.md](INSTALLATION.md#uninstalling)).

## Troubleshooting

| Problem | Fix |
|---|---|
| Build error *"'VbOcrClient' is ambiguous"* / *"already declared"* | A class with that name already exists in your project. Wrap both files in `Namespace VbOcr` … `End Namespace` and add `Imports YourRootNamespace.VbOcr` where you use them |
| Build error about `DataGridView` or `Form` | The project is not a Windows Forms project. Add only `VbOcrClient.vb` and use it as in [VBNET_INTEGRATION.md](VBNET_INTEGRATION.md#3-without-the-dialog-vbocrclient) |
| Double-clicking `VbOcrScanForm.vb` shows a designer error | Expected: the form has no designer file. Use **right-click → View Code** |
| *"VB OCR is not installed in C:\vbocr"* | Install VB OCR on this PC (Step 1), or correct `InstallFolder` |
| *"The VB OCR server did not start"* | Run `C:\vbocr\start-server.bat` to see the error. See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) |
| *"Cannot reach the VB OCR server at http://192.168…"* | The OCR PC is off, its server is not running, or the firewall blocks port 5000 |
| Wrong values in some columns | Check the supplier with the browser test page, then adjust [CONFIGURATION.md](CONFIGURATION.md) or [ADDING_SUPPLIERS.md](ADDING_SUPPLIERS.md) |
| Numbers 100× too big or small on some PCs | Use `VbOcrInvoice.ToDecimal`, not `CDec`/`Val`/`Decimal.Parse` |

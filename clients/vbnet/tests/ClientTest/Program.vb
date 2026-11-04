' End-to-end test of VbOcrClient against a running server. Exit code = number of failures.
Option Strict On
Imports System
Imports System.IO

Module Program
    Dim failures As Integer = 0

    Sub Check(ByVal name As String, ByVal ok As Boolean)
        Console.WriteLine(If(ok, "PASS ", "FAIL ") & name)
        If Not ok Then failures += 1
    End Sub

    Function Main(ByVal args() As String) As Integer
        If args.Length < 2 Then
            Console.WriteLine("Usage: ClientTest <server url> <test files folder> [api key]")
            Return 99
        End If
        ' A regional format with "," as decimal separator must not break the numbers.
        System.Threading.Thread.CurrentThread.CurrentCulture = New System.Globalization.CultureInfo("de-DE")
        Dim source As String = Path.GetFullPath(args(1))
        Dim c As New VbOcrClient(args(0))
        c.TimeoutSeconds = 600

        Check("server ready", c.IsReady())
        Check("png supported (upper case)", VbOcrClient.IsSupportedFile("X.PNG"))
        Check("txt not supported", Not VbOcrClient.IsSupportedFile("a.txt"))

        ' a folder with 3 invoice files and a text file
        Dim dir As String = Path.Combine(Path.GetTempPath(), "vbocr-client-test")
        If Directory.Exists(dir) Then Directory.Delete(dir, True)
        Directory.CreateDirectory(dir)
        For Each name As String In New String() {"a_bill.jpg", "b_bill.png", "c_bad.png", "readme.txt"}
            File.Copy(Path.Combine(source, name), Path.Combine(dir, name))
        Next
        Dim files() As String = VbOcrClient.GetInvoiceFiles(dir)
        Check("folder: 3 invoice files, txt skipped, sorted", files.Length = 3 AndAlso Path.GetFileName(files(0)) = "a_bill.jpg")

        If args.Length > 2 Then
            Try
                c.Scan(Path.Combine(dir, "b_bill.png"))
                Check("no key: rejected", False)
            Catch ex As VbOcrException
                Check("no key: rejected with hint", ex.Message.StartsWith("Access key missing") AndAlso ex.Message.Contains("ApiKey"))
            End Try
            c.ApiKey = " " & args(2) & " "
        End If

        Dim r As VbOcrResult = c.Scan(Path.Combine(dir, "b_bill.png"))
        Check("PNG scan: 3 items", r.ItemCount = 3 AndAlso r.Invoice.Items.Rows.Count = 3)
        Check("PNG scan: invoice no", r.Invoice.GetHeader("Invoice Number") = "SG/25-26/0042")
        Check("PNG scan: amount row 1", CStr(r.Invoice.Items.Rows(0)("Amount")) = "1335.32")
        Check("decimal under de-DE", VbOcrInvoice.ToDecimal(r.Invoice.Items.Rows(0)("Amount")) = 1335.32D)
        Check("total check mismatch", r.TotalCheck = "mismatch" AndAlso r.ItemsTotal = "4741.10" AndAlso r.PrintedTotal = "5743.10" AndAlso r.TotalMismatch())
        Check("scan id + source", r.ScanId.Length > 15 AndAlso r.Source = "ocr")

        Dim pdf As VbOcrResult = c.Scan(Path.Combine(source, "digital-invoice.pdf"))
        Check("digital pdf: exact text, total ok", pdf.Source = "pdf-text" AndAlso pdf.TotalCheck = "ok" AndAlso pdf.ItemCount = 3 AndAlso pdf.UnsureCells.Count = 0)

        Dim fake As New VbOcrResult()
        Dim h As New System.Net.WebHeaderCollection()
        h("X-VBOCR-Unsure") = "Invoice Number;3:Quantity;12:M.R.P"
        h("X-VBOCR-Total-Check") = "ok|4641.10|5060.00|4641.10"
        fake.ReadHeaders(h)
        Check("unsure parsed", fake.UnsureCells.Count = 3 AndAlso fake.IsUnsure(0, "invoice number") AndAlso fake.IsUnsure(3, "Quantity") AndAlso fake.IsUnsure(12, "M.R.P") AndAlso Not fake.IsUnsure(1, "Quantity"))
        Check("total check with taxes parsed", fake.TotalCheck = "ok" AndAlso fake.ExpectedItemsTotal = "4641.10" AndAlso Not fake.TotalMismatch())

        Dim two As VbOcrResult = c.Scan(Path.Combine(dir, "a_bill.jpg"), Path.Combine(dir, "b_bill.png"))
        Check("JPG + PNG as pages of one invoice: 6 items", two.ItemCount = 6)

        Dim batch() As VbOcrResult = c.ScanEach(files)
        Check("ScanEach: 3 results", batch.Length = 3)
        Check("ScanEach: jpg ok", batch(0).ErrorMessage = "" AndAlso batch(0).ItemCount = 3 AndAlso batch(0).SourceFile = files(0))
        Check("ScanEach: png ok", batch(1).ErrorMessage = "" AndAlso batch(1).ItemCount = 3)
        Check("ScanEach: bad file reported, not thrown", batch(2).ErrorMessage.Contains("c_bad.png") AndAlso batch(2).ErrorMessage.Contains("Cannot read image") AndAlso batch(2).Invoice Is Nothing)

        Dim missing() As VbOcrResult = c.ScanEach(Path.Combine(dir, "nope.png"), Path.Combine(dir, "readme.txt"))
        Check("ScanEach: missing file reported", missing(0).ErrorMessage.StartsWith("File not found"))
        Check("ScanEach: txt reported as unsupported", missing(1).ErrorMessage.StartsWith("Unsupported file type"))

        Console.WriteLine(If(failures = 0, "ALL PASSED", failures.ToString() & " FAILED"))
        Return failures
    End Function
End Module

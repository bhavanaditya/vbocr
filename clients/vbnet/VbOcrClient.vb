' VB OCR client for VB.NET applications
'
' Compatible with:
'   - Visual Studio 2008 or later
'   - .NET Framework 2.0 or later, and .NET 6 / 8 (Windows)
'   - Option Strict On, Option Explicit On, Option Infer On or Off
'   - x86, x64 and AnyCPU builds (the OCR runs in its own process)
' No extra references or NuGet packages are needed.
'
' Quick use (run it on a background thread - see VbOcrScanForm.vb or docs\VBNET_INTEGRATION.md):
'
'     Dim client As New VbOcrClient()
'     client.EnsureServerRunning("C:\vbocr")
'     Dim result As VbOcrResult = client.Scan("C:\Invoices\bill.jpg")
'     Dim invoiceNo As String = result.Invoice.GetHeader("Invoice Number")
'     For Each row As DataRow In result.Invoice.Items.Rows
'         Dim qty As Decimal = VbOcrInvoice.ToDecimal(row("Quantity"))
'     Next

Option Strict On
Option Explicit On

Imports System
Imports System.Collections.Generic
Imports System.Data
Imports System.Diagnostics
Imports System.Globalization
Imports System.IO
Imports System.Net
Imports System.Text
Imports System.Threading
Imports Microsoft.VisualBasic.FileIO

''' <summary>Error from VB OCR: server not reachable, not installed, or scan failed.</summary>
Public Class VbOcrException
    Inherits Exception

    Public Sub New(ByVal message As String)
        MyBase.New(message)
    End Sub

    Public Sub New(ByVal message As String, ByVal inner As Exception)
        MyBase.New(message, inner)
    End Sub
End Class

''' <summary>Result of one scan.</summary>
Public Class VbOcrResult
    ''' <summary>CSV text in the purchase-entry layout.</summary>
    Public Csv As String = ""
    ''' <summary>Number of item rows found.</summary>
    Public ItemCount As Integer
    ''' <summary>Problems found while reading, separated by " | ". Empty when all is well.</summary>
    Public Warnings As String = ""
    ''' <summary>The CSV split into header values and an item table.</summary>
    Public Invoice As VbOcrInvoice
    ''' <summary>ScanEach only: the file this result belongs to.</summary>
    Public SourceFile As String = ""
    ''' <summary>ScanEach only: why this file failed. Empty when it worked.</summary>
    Public ErrorMessage As String = ""
    ''' <summary>Values the OCR was not sure about. Show them to the user to check.</summary>
    Public UnsureCells As New List(Of VbOcrCell)
    ''' <summary>Items total compared with the total printed on the invoice:
    ''' "ok", "mismatch", "not_found", "no_items" or "" (old server / no check).</summary>
    Public TotalCheck As String = ""
    ''' <summary>Sum of the item amounts, as text (e.g. "4741.10").</summary>
    Public ItemsTotal As String = ""
    ''' <summary>Total printed on the invoice, as text. Empty when not found.</summary>
    Public PrintedTotal As String = ""
    ''' <summary>ID of this scan in the server's scan history (empty when history is off).</summary>
    Public ScanId As String = ""
    ''' <summary>"ocr" or "pdf-text" (read exactly from a digital PDF).</summary>
    Public Source As String = ""

    ''' <summary>True when the OCR was not sure about this value. row 0 = a header value,
    ''' 1 = first item row. title = CSV column title, e.g. "Quantity".</summary>
    Public Function IsUnsure(ByVal row As Integer, ByVal title As String) As Boolean
        For Each cell As VbOcrCell In UnsureCells
            If cell.Row = row AndAlso String.Equals(cell.Title, title, StringComparison.OrdinalIgnoreCase) Then Return True
        Next
        Return False
    End Function

    ''' <summary>True when the items add up to a different total than the invoice prints.</summary>
    Public Function TotalMismatch() As Boolean
        Return TotalCheck = "mismatch"
    End Function

    ' X-VBOCR-Unsure: "Invoice Number;3:Quantity" = a header value and the quantity of item 3
    Friend Sub ReadHeaders(ByVal headers As WebHeaderCollection)
        Integer.TryParse(headers("X-VBOCR-Item-Count"), ItemCount)
        If headers("X-VBOCR-Warnings") IsNot Nothing Then Warnings = headers("X-VBOCR-Warnings")
        If headers("X-VBOCR-Scan-Id") IsNot Nothing Then ScanId = headers("X-VBOCR-Scan-Id")
        If headers("X-VBOCR-Source") IsNot Nothing Then Source = headers("X-VBOCR-Source")
        Dim check As String = headers("X-VBOCR-Total-Check")
        If check IsNot Nothing Then
            Dim parts() As String = check.Split("|"c)
            TotalCheck = parts(0)
            If parts.Length > 1 Then ItemsTotal = parts(1)
            If parts.Length > 2 Then PrintedTotal = parts(2)
        End If
        Dim unsure As String = headers("X-VBOCR-Unsure")
        If unsure IsNot Nothing Then
            For Each part As String In unsure.Split(New Char() {";"c}, StringSplitOptions.RemoveEmptyEntries)
                Dim cell As New VbOcrCell()
                Dim colon As Integer = part.IndexOf(":"c)
                Dim rowNumber As Integer
                If colon > 0 AndAlso Integer.TryParse(part.Substring(0, colon), rowNumber) Then
                    cell.Row = rowNumber
                    cell.Title = part.Substring(colon + 1)
                Else
                    cell.Title = part
                End If
                UnsureCells.Add(cell)
            Next
        End If
    End Sub
End Class

''' <summary>One value of the invoice: Row 0 = header value, 1 = first item row.</summary>
Public Class VbOcrCell
    Public Row As Integer
    ''' <summary>CSV column title, e.g. "Invoice Number" or "Quantity".</summary>
    Public Title As String = ""
End Class

''' <summary>Talks to the VB OCR server. All methods are synchronous: call them from a
''' BackgroundWorker or thread so the screen does not freeze while scanning.</summary>
Public Class VbOcrClient

    Public Const DefaultServerUrl As String = "http://127.0.0.1:5000"
    Public Const DefaultInstallFolder As String = "C:\vbocr"

    Private Shared ReadOnly StartLock As New Object()
    Private Shared _lastStart As DateTime = DateTime.MinValue

    Private ReadOnly _baseUrl As String
    Private _timeoutSeconds As Integer = 300
    Private _apiKey As String = ""

    Public Sub New()
        Me.New(DefaultServerUrl)
    End Sub

    Public Sub New(ByVal serverUrl As String)
        _baseUrl = serverUrl.TrimEnd("/"c) & "/"
    End Sub

    ''' <summary>Maximum time for one scan (default 300 seconds).</summary>
    Public Property TimeoutSeconds() As Integer
        Get
            Return _timeoutSeconds
        End Get
        Set(ByVal value As Integer)
            _timeoutSeconds = value
        End Set
    End Property

    ''' <summary>Access key, when the server has server.api_key set (needed when the
    ''' server is shared on the network). Empty = no key.</summary>
    Public Property ApiKey() As String
        Get
            Return _apiKey
        End Get
        Set(ByVal value As String)
            If value Is Nothing Then value = ""
            _apiKey = value.Trim()
        End Set
    End Property

    ''' <summary>True when the server is running and ready to scan.</summary>
    Public Function IsReady() As Boolean
        Try
            Dim request As HttpWebRequest = CreateRequest("health", 5)
            Using response As HttpWebResponse = CType(request.GetResponse(), HttpWebResponse)
                Return ReadBody(response).IndexOf("""ok""", StringComparison.Ordinal) >= 0
            End Using
        Catch ex As WebException
            Return False
        End Try
    End Function

    ''' <summary>Starts the server (hidden, no window) if it is not running and waits up to
    ''' 120 seconds until it is ready. Only works for a server on this PC.</summary>
    Public Function EnsureServerRunning(ByVal installFolder As String) As Boolean
        Return EnsureServerRunning(installFolder, 120)
    End Function

    Public Function EnsureServerRunning(ByVal installFolder As String, ByVal timeoutSeconds As Integer) As Boolean
        If IsReady() Then Return True

        Dim pythonw As String = Path.Combine(Path.Combine(Path.Combine(installFolder, ".venv"), "Scripts"), "pythonw.exe")
        If Not File.Exists(pythonw) Then
            Throw New VbOcrException("VB OCR is not installed in " & installFolder & ". Run install.bat first.")
        End If

        SyncLock StartLock
            ' Do not start a second copy while the first one is still loading.
            If DateTime.Now.Subtract(_lastStart).TotalSeconds > timeoutSeconds Then
                Dim info As New ProcessStartInfo(pythonw, "-m vbocr serve")
                info.WorkingDirectory = installFolder
                info.UseShellExecute = False
                info.CreateNoWindow = True
                Process.Start(info)
                _lastStart = DateTime.Now
            End If
        End SyncLock

        Dim deadline As DateTime = DateTime.Now.AddSeconds(timeoutSeconds)
        Do While DateTime.Now < deadline
            Thread.Sleep(1000)
            If IsReady() Then Return True
        Loop
        Return False
    End Function

    ''' <summary>File types the server accepts (lower case, with dot).</summary>
    Public Shared ReadOnly SupportedExtensions() As String = New String() { _
        ".jpg", ".jpeg", ".jpe", ".jfif", ".png", ".bmp", ".tif", ".tiff", ".webp", ".gif", ".pdf"}

    ''' <summary>Filter for OpenFileDialog.Filter.</summary>
    Public Const FileDialogFilter As String = _
        "Invoice images and PDF|*.jpg;*.jpeg;*.jpe;*.jfif;*.png;*.bmp;*.tif;*.tiff;*.webp;*.gif;*.pdf|All files|*.*"

    ''' <summary>True when the file has a supported extension.</summary>
    Public Shared Function IsSupportedFile(ByVal filePath As String) As Boolean
        Dim ext As String = Path.GetExtension(filePath).ToLowerInvariant()
        Return Array.IndexOf(SupportedExtensions, ext) >= 0
    End Function

    ''' <summary>All supported files in a folder (not sub-folders), sorted by name.</summary>
    Public Shared Function GetInvoiceFiles(ByVal folder As String) As String()
        Dim found As New List(Of String)
        For Each filePath As String In Directory.GetFiles(folder)
            If IsSupportedFile(filePath) Then found.Add(filePath)
        Next
        found.Sort(StringComparer.OrdinalIgnoreCase)
        Return found.ToArray()
    End Function

    ''' <summary>Scans one invoice. Pass several files when the invoice has several pages.
    ''' Supported: jpg, jpeg, png, bmp, tif, tiff, webp, gif, pdf.</summary>
    Public Function Scan(ByVal ParamArray filePaths() As String) As VbOcrResult
        If filePaths Is Nothing OrElse filePaths.Length = 0 Then
            Throw New ArgumentException("At least one file is required.")
        End If

        Dim boundary As String = "----vbocr" & DateTime.Now.Ticks.ToString("x", CultureInfo.InvariantCulture)
        Dim body As New MemoryStream()
        For i As Integer = 0 To filePaths.Length - 1
            If Not File.Exists(filePaths(i)) Then
                Throw New VbOcrException("File not found: " & filePaths(i))
            End If
            If Not IsSupportedFile(filePaths(i)) Then
                Throw New VbOcrException("Unsupported file type: " & Path.GetFileName(filePaths(i)) & _
                    ". Use jpg, png, bmp, tif, webp, gif or pdf.")
            End If
            Dim name As String = SentName(i, filePaths(i))
            WriteAscii(body, "--" & boundary & vbCrLf & _
                "Content-Disposition: form-data; name=""files""; filename=""" & name & """" & vbCrLf & _
                "Content-Type: application/octet-stream" & vbCrLf & vbCrLf)
            Dim bytes() As Byte = File.ReadAllBytes(filePaths(i))
            body.Write(bytes, 0, bytes.Length)
            WriteAscii(body, vbCrLf)
        Next
        WriteAscii(body, "--" & boundary & "--" & vbCrLf)

        Dim request As HttpWebRequest = CreateRequest("scan?format=csv", _timeoutSeconds)
        request.Method = "POST"
        request.ContentType = "multipart/form-data; boundary=" & boundary
        request.ContentLength = body.Length

        Dim result As New VbOcrResult()
        Try
            Using stream As Stream = request.GetRequestStream()
                body.WriteTo(stream)
            End Using
            Using response As HttpWebResponse = CType(request.GetResponse(), HttpWebResponse)
                result.Csv = ReadBody(response)
                result.ReadHeaders(response.Headers)
            End Using
        Catch ex As WebException
            Dim errorResponse As HttpWebResponse = TryCast(ex.Response, HttpWebResponse)
            If errorResponse Is Nothing Then
                Throw New VbOcrException("Cannot reach the VB OCR server at " & _baseUrl & _
                    ". Start it with start-server.bat or EnsureServerRunning. (" & ex.Message & ")", ex)
            End If
            Dim message As String = ServerErrorText(ReadBody(errorResponse))
            ' Names with other characters are sent in plain ASCII: show the user's file names instead.
            For i As Integer = filePaths.Length - 1 To 0 Step -1
                message = message.Replace(SentName(i, filePaths(i)), Path.GetFileName(filePaths(i)))
            Next
            If errorResponse.StatusCode = HttpStatusCode.Unauthorized Then
                Throw New VbOcrException(message & " (Set VbOcrClient.ApiKey to the key in the server's config\settings.local.yaml.)", ex)
            End If
            Throw New VbOcrException("VB OCR server error " & CInt(errorResponse.StatusCode).ToString(CultureInfo.InvariantCulture) & ": " & message, ex)
        End Try

        result.Invoice = VbOcrInvoice.Parse(result.Csv)
        Return result
    End Function

    ''' <summary>Scans every file as a SEPARATE invoice (for example a folder of bills).
    ''' Returns one result per file, in the same order. A file that fails does not stop the
    ''' others: its result has Invoice = Nothing and the reason in ErrorMessage.</summary>
    Public Function ScanEach(ByVal ParamArray filePaths() As String) As VbOcrResult()
        If filePaths Is Nothing OrElse filePaths.Length = 0 Then
            Throw New ArgumentException("At least one file is required.")
        End If
        Dim results(filePaths.Length - 1) As VbOcrResult
        For i As Integer = 0 To filePaths.Length - 1
            Try
                results(i) = Scan(filePaths(i))
            Catch ex As VbOcrException
                results(i) = New VbOcrResult()
                results(i).ErrorMessage = ex.Message
            Catch ex As IOException
                results(i) = New VbOcrResult()
                results(i).ErrorMessage = ex.Message
            End Try
            results(i).SourceFile = filePaths(i)
        Next
        Return results
    End Function

    ''' <summary>Scans and saves the CSV (UTF-8 with BOM, so Excel opens it correctly).</summary>
    Public Function ScanToFile(ByVal outputCsvPath As String, ByVal ParamArray filePaths() As String) As VbOcrResult
        Dim result As VbOcrResult = Scan(filePaths)
        File.WriteAllText(outputCsvPath, result.Csv, New UTF8Encoding(True))
        Return result
    End Function

    ''' <summary>Scans without the server by running the command line. Slower (the OCR engine
    ''' loads on every call) but needs nothing running in the background.</summary>
    Public Shared Function ScanWithoutServer(ByVal installFolder As String, ByVal ParamArray filePaths() As String) As VbOcrResult
        If filePaths Is Nothing OrElse filePaths.Length = 0 Then
            Throw New ArgumentException("At least one file is required.")
        End If
        Dim python As String = Path.Combine(Path.Combine(Path.Combine(installFolder, ".venv"), "Scripts"), "python.exe")
        If Not File.Exists(python) Then
            Throw New VbOcrException("VB OCR is not installed in " & installFolder & ". Run install.bat first.")
        End If

        Dim outputCsv As String = Path.GetTempFileName()
        Dim args As New StringBuilder("-m vbocr scan")
        For Each filePath As String In filePaths
            args.Append(" """).Append(filePath).Append("""")
        Next
        args.Append(" -o """).Append(outputCsv).Append("""")

        Dim info As New ProcessStartInfo(python, args.ToString())
        info.WorkingDirectory = installFolder
        info.UseShellExecute = False
        info.CreateNoWindow = True
        info.RedirectStandardError = True

        Dim errors As String
        Dim exitCode As Integer
        Using p As Process = Process.Start(info)
            errors = p.StandardError.ReadToEnd()
            p.WaitForExit()
            exitCode = p.ExitCode
        End Using

        Try
            If exitCode <> 0 AndAlso exitCode <> 1 Then
                Throw New VbOcrException("VB OCR failed (exit code " & exitCode.ToString(CultureInfo.InvariantCulture) & "): " & LastLines(errors, 5))
            End If
            Dim result As New VbOcrResult()
            result.Csv = File.ReadAllText(outputCsv, Encoding.UTF8)
            result.Invoice = VbOcrInvoice.Parse(result.Csv)
            result.ItemCount = result.Invoice.Items.Rows.Count
            Dim warnings As New List(Of String)
            For Each line As String In errors.Split(New Char() {ControlChars.Cr, ControlChars.Lf}, StringSplitOptions.RemoveEmptyEntries)
                If line.StartsWith("WARNING: ", StringComparison.Ordinal) Then warnings.Add(line.Substring(9))
            Next
            result.Warnings = String.Join(" | ", warnings.ToArray())
            Return result
        Finally
            Try
                File.Delete(outputCsv)
            Catch ex As IOException
            End Try
        End Try
    End Function

    Private Function CreateRequest(ByVal relativeUrl As String, ByVal timeoutSeconds As Integer) As HttpWebRequest
        Dim request As HttpWebRequest = CType(WebRequest.Create(_baseUrl & relativeUrl), HttpWebRequest)
        request.Proxy = Nothing   ' never send local requests through the office proxy
        request.Timeout = timeoutSeconds * 1000
        request.ReadWriteTimeout = timeoutSeconds * 1000
        If _apiKey.Length > 0 Then request.Headers("X-API-Key") = _apiKey
        Try
            request.ServicePoint.Expect100Continue = False   ' avoids a delay on .NET Framework
        Catch ex As NotSupportedException
            ' .NET 6/8: not needed
        End Try
        Return request
    End Function

    ' The file name as sent to the server (plain ASCII, so the multipart header stays valid).
    ' Shown in the scan history; only the extension matters for reading.
    Private Shared Function SentName(ByVal index As Integer, ByVal filePath As String) As String
        Dim sb As New StringBuilder()
        For Each c As Char In Path.GetFileNameWithoutExtension(filePath)
            If AscW(c) >= 32 AndAlso AscW(c) < 127 AndAlso c <> """"c AndAlso c <> "\"c Then
                sb.Append(c)
            Else
                sb.Append("_"c)
            End If
        Next
        Dim stem As String = sb.ToString().Trim()
        If stem.Replace("_", "").Length = 0 Then stem = "page" & (index + 1).ToString(CultureInfo.InvariantCulture)
        Return stem & Path.GetExtension(filePath).ToLowerInvariant()
    End Function

    Private Shared Function ReadBody(ByVal response As HttpWebResponse) As String
        Using reader As New StreamReader(response.GetResponseStream(), Encoding.UTF8, True)
            Return reader.ReadToEnd()
        End Using
    End Function

    ' {"detail":"Cannot read image ..."} -> Cannot read image ...
    Private Shared Function ServerErrorText(ByVal body As String) As String
        Const prefix As String = "{""detail"":"""
        Dim text As String = body.Trim()
        If text.StartsWith(prefix, StringComparison.Ordinal) AndAlso text.EndsWith("""}", StringComparison.Ordinal) Then
            text = text.Substring(prefix.Length, text.Length - prefix.Length - 2).Replace("""", """").Replace("\", "")
        End If
        Return text
    End Function

    Private Shared Sub WriteAscii(ByVal stream As Stream, ByVal text As String)
        Dim bytes() As Byte = Encoding.ASCII.GetBytes(text)
        stream.Write(bytes, 0, bytes.Length)
    End Sub

    Private Shared Function LastLines(ByVal text As String, ByVal count As Integer) As String
        Dim lines() As String = text.Trim().Split(New Char() {ControlChars.Lf})
        Dim first As Integer = Math.Max(0, lines.Length - count)
        Return String.Join(" ", lines, first, lines.Length - first).Replace(ControlChars.Cr, " "c)
    End Function
End Class

''' <summary>A scanned invoice: header values and an item table, all as text exactly as in the CSV.</summary>
Public Class VbOcrInvoice

    Public Shared ReadOnly HeaderTitles() As String = New String() { _
        "Date", "Supplier Name", "Purchase Order Date", "Purchase Order Number", "L.R Booking Date", _
        "Stock Received Date", "Invoice Number", "Invoice Date", "GRN Number"}

    Public Shared ReadOnly ItemTitles() As String = New String() { _
        "Sl.No", "SKU No./Item ID.", "Article ID", "Brand Name", "Design Name", "Size", "Cup Size", _
        "Colour", "Quantity", "Cost Price", "M.R.P", "Amount"}

    ''' <summary>Header values keyed by title (see HeaderTitles). Not case-sensitive.</summary>
    Public ReadOnly Header As New Dictionary(Of String, String)(StringComparer.OrdinalIgnoreCase)

    ''' <summary>One row per item; columns as in ItemTitles, all String. No Total row.</summary>
    Public ReadOnly Items As New DataTable("Items")

    Public Sub New()
        For Each title As String In HeaderTitles
            Header(title) = ""
        Next
        For Each title As String In ItemTitles
            Items.Columns.Add(title, GetType(String))
        Next
    End Sub

    ''' <summary>Header value, or "" when missing.</summary>
    Public Function GetHeader(ByVal title As String) As String
        Dim value As String = Nothing
        If Header.TryGetValue(title, value) AndAlso value IsNot Nothing Then Return value
        Return ""
    End Function

    Public Shared Function Parse(ByVal csv As String) As VbOcrInvoice
        Dim invoice As New VbOcrInvoice()
        If csv Is Nothing Then Return invoice
        csv = csv.TrimStart(ChrW(&HFEFF))

        Dim rows As New List(Of String())
        Using parser As New TextFieldParser(New StringReader(csv))
            parser.TextFieldType = FieldType.Delimited
            parser.SetDelimiters(",")
            parser.HasFieldsEnclosedInQuotes = True
            parser.TrimWhiteSpace = False
            Do While Not parser.EndOfData
                Dim fields() As String = parser.ReadFields()
                If fields IsNot Nothing Then rows.Add(fields)
            Loop
        End Using
        If rows.Count < 2 Then Return invoice

        ' Rows 1-2: header titles and values. Column A is empty.
        For i As Integer = 1 To rows(0).Length - 1
            Dim value As String = ""
            If i < rows(1).Length Then value = rows(1)(i)
            invoice.Header(rows(0)(i)) = value
        Next

        ' Items start after the row that begins with "Sl.No".
        Dim inItems As Boolean = False
        For Each fields As String() In rows
            If fields.Length = 0 Then Continue For
            If Not inItems Then
                If fields(0) = "Sl.No" Then inItems = True
                Continue For
            End If
            If fields(0) = "Total" OrElse fields(0) = "" Then Continue For
            Dim values(invoice.Items.Columns.Count - 1) As Object
            For c As Integer = 0 To values.Length - 1
                If c < fields.Length Then values(c) = fields(c) Else values(c) = ""
            Next
            invoice.Items.Rows.Add(values)
        Next
        Return invoice
    End Function

    ''' <summary>Writes the invoice back to CSV in the same layout, for example after the
    ''' user corrected values or GRN Number was filled in. The Total row is recalculated.</summary>
    Public Function ToCsv() As String
        Dim sb As New StringBuilder()
        Dim line As New List(Of String)

        line.Add("")
        line.AddRange(HeaderTitles)
        AppendCsvLine(sb, line)
        line.Clear()
        line.Add("")
        For Each title As String In HeaderTitles
            line.Add(GetHeader(title))
        Next
        AppendCsvLine(sb, line)
        sb.Append(vbCrLf)
        line.Clear()
        line.AddRange(ItemTitles)
        AppendCsvLine(sb, line)

        Dim number As Integer = 0
        For Each row As DataRow In Items.Rows
            If row.RowState = DataRowState.Deleted Then Continue For
            number += 1
            line.Clear()
            line.Add(number.ToString(CultureInfo.InvariantCulture))
            For c As Integer = 1 To ItemTitles.Length - 1
                line.Add(CellText(row, ItemTitles(c)))
            Next
            AppendCsvLine(sb, line)
        Next

        line.Clear()
        line.Add("Total")
        For c As Integer = 1 To ItemTitles.Length - 1
            If ItemTitles(c) = "Quantity" OrElse ItemTitles(c) = "Amount" Then
                line.Add(ColumnTotal(ItemTitles(c)))
            Else
                line.Add("")
            End If
        Next
        AppendCsvLine(sb, line)
        Return sb.ToString()
    End Function

    ''' <summary>Converts a CSV number ("1335.32") to Decimal, independent of the PC's
    ''' regional settings. Empty or unreadable values give 0.</summary>
    Public Shared Function ToDecimal(ByVal value As Object) As Decimal
        Dim result As Decimal = 0D
        If value Is Nothing OrElse value Is DBNull.Value Then Return 0D
        Decimal.TryParse(Convert.ToString(value, CultureInfo.InvariantCulture), NumberStyles.Number, CultureInfo.InvariantCulture, result)
        Return result
    End Function

    ''' <summary>Converts a CSV date to Date. Returns False when empty or unreadable.
    ''' Accepts dd-MM-yyyy (default), dd/MM/yyyy and yyyy-MM-dd.</summary>
    Public Shared Function TryToDate(ByVal value As Object, ByRef result As DateTime) As Boolean
        Dim formats() As String = New String() {"dd-MM-yyyy", "dd/MM/yyyy", "yyyy-MM-dd", "d-M-yyyy", "d/M/yyyy"}
        If value Is Nothing OrElse value Is DBNull.Value Then Return False
        Return DateTime.TryParseExact(Convert.ToString(value, CultureInfo.InvariantCulture), formats, CultureInfo.InvariantCulture, DateTimeStyles.None, result)
    End Function

    Private Function ColumnTotal(ByVal title As String) As String
        Dim total As Decimal = 0D
        Dim hasDecimals As Boolean = False
        For Each row As DataRow In Items.Rows
            If row.RowState = DataRowState.Deleted Then Continue For
            Dim text As String = CellText(row, title)
            If text.IndexOf("."c) >= 0 Then hasDecimals = True
            total += ToDecimal(text)
        Next
        If hasDecimals Then Return total.ToString("0.00", CultureInfo.InvariantCulture)
        Return total.ToString("0", CultureInfo.InvariantCulture)
    End Function

    Private Shared Function CellText(ByVal row As DataRow, ByVal title As String) As String
        If Not row.Table.Columns.Contains(title) OrElse row(title) Is DBNull.Value Then Return ""
        Return Convert.ToString(row(title), CultureInfo.InvariantCulture)
    End Function

    Private Shared Sub AppendCsvLine(ByVal sb As StringBuilder, ByVal fields As List(Of String))
        For i As Integer = 0 To fields.Count - 1
            If i > 0 Then sb.Append(","c)
            Dim field As String = fields(i)
            If field Is Nothing Then field = ""
            If field.IndexOfAny(New Char() {","c, """"c, ControlChars.Cr, ControlChars.Lf}) >= 0 Then
                sb.Append(""""c).Append(field.Replace("""", """""")).Append(""""c)
            Else
                sb.Append(field)
            End If
        Next
        sb.Append(vbCrLf)
    End Sub
End Class

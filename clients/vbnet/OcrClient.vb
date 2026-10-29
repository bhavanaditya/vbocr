' VB OCR client for VB.NET
'
' Works with .NET Framework 4.7.2+ and .NET 6/8.
' On .NET Framework add a reference to System.Net.Http.
'
' Usage:
'     Using client As New OcrClient()
'         Dim result = Await client.ScanAsync("C:\Invoices\bill1.jpg")
'         Dim invoice = InvoiceCsv.Parse(result.Csv)
'         MessageBox.Show(invoice.Header("Invoice Number"))
'     End Using

Imports System.Collections.Generic
Imports System.Data
Imports System.Diagnostics
Imports System.IO
Imports System.Net.Http
Imports System.Net.Http.Headers
Imports System.Text
Imports System.Threading.Tasks
Imports Microsoft.VisualBasic.FileIO

Public Class OcrResult
    ''' <summary>CSV text in the purchase-entry layout.</summary>
    Public Property Csv As String
    ''' <summary>Number of item rows found.</summary>
    Public Property ItemCount As Integer
    ''' <summary>Problems found while reading, separated by " | ". Empty when all is well.</summary>
    Public Property Warnings As String = ""
End Class

Public Class OcrClient
    Implements IDisposable

    Private ReadOnly _http As HttpClient

    Public Sub New(Optional baseUrl As String = "http://127.0.0.1:5000")
        _http = New HttpClient() With {
            .BaseAddress = New Uri(baseUrl),
            .Timeout = TimeSpan.FromMinutes(5)
        }
    End Sub

    ''' <summary>True when the OCR server is running and ready.</summary>
    Public Async Function IsReadyAsync() As Task(Of Boolean)
        Try
            Dim body = Await _http.GetStringAsync("health")
            Return body.Contains("""ok""")
        Catch ex As HttpRequestException
            Return False
        Catch ex As TaskCanceledException
            Return False
        End Try
    End Function

    ''' <summary>
    ''' Scan one invoice. Pass several files when the invoice has several pages.
    ''' Supported: jpg, jpeg, png, bmp, tif, tiff, webp, pdf.
    ''' </summary>
    Public Async Function ScanAsync(ParamArray filePaths As String()) As Task(Of OcrResult)
        If filePaths Is Nothing OrElse filePaths.Length = 0 Then
            Throw New ArgumentException("At least one file is required.")
        End If

        Using form As New MultipartFormDataContent()
            For Each path In filePaths
                Dim content As New ByteArrayContent(File.ReadAllBytes(path))
                content.Headers.ContentType = New MediaTypeHeaderValue("application/octet-stream")
                form.Add(content, "files", IO.Path.GetFileName(path))
            Next

            Using response = Await _http.PostAsync("scan?format=csv", form)
                Dim body = Await response.Content.ReadAsStringAsync()
                If Not response.IsSuccessStatusCode Then
                    Throw New InvalidOperationException(
                        String.Format("OCR server error {0}: {1}", CInt(response.StatusCode), body))
                End If

                Dim result As New OcrResult With {.Csv = body.TrimStart(ChrW(&HFEFF))}
                Dim values As IEnumerable(Of String) = Nothing
                If response.Headers.TryGetValues("X-VBOCR-Item-Count", values) Then
                    Integer.TryParse(String.Join("", values), result.ItemCount)
                End If
                If response.Headers.TryGetValues("X-VBOCR-Warnings", values) Then
                    result.Warnings = String.Join(" | ", values)
                End If
                Return result
            End Using
        End Using
    End Function

    ''' <summary>Scan and save the CSV to a file (UTF-8 with BOM so Excel opens it correctly).</summary>
    Public Async Function ScanToFileAsync(outputCsvPath As String, ParamArray filePaths As String()) As Task(Of OcrResult)
        Dim result = Await ScanAsync(filePaths)
        File.WriteAllText(outputCsvPath, result.Csv, New UTF8Encoding(True))
        Return result
    End Function

    ''' <summary>
    ''' Start the OCR server if it is not running, then wait until it is ready.
    ''' installFolder is the folder where VB OCR was installed (it contains start-server.bat).
    ''' </summary>
    Public Async Function EnsureServerRunningAsync(installFolder As String,
                                                   Optional timeoutSeconds As Integer = 120) As Task(Of Boolean)
        If Await IsReadyAsync() Then Return True

        Dim pythonw = Path.Combine(installFolder, ".venv", "Scripts", "pythonw.exe")
        If Not File.Exists(pythonw) Then
            Throw New FileNotFoundException("VB OCR is not installed in " & installFolder, pythonw)
        End If
        Dim info As New ProcessStartInfo(pythonw, "-m vbocr serve") With {
            .WorkingDirectory = installFolder,
            .UseShellExecute = False,
            .CreateNoWindow = True
        }
        Process.Start(info)

        Dim waited = 0
        While waited < timeoutSeconds
            Await Task.Delay(2000)
            waited += 2
            If Await IsReadyAsync() Then Return True
        End While
        Return False
    End Function

    Public Sub Dispose() Implements IDisposable.Dispose
        _http.Dispose()
    End Sub
End Class

''' <summary>The CSV split into header values and an item table.</summary>
Public Class InvoiceData
    ''' <summary>Keys: Date, Supplier Name, Purchase Order Date, Purchase Order Number,
    ''' L.R Booking Date, Stock Received Date, Invoice Number, Invoice Date, GRN Number.</summary>
    Public Property Header As New Dictionary(Of String, String)(StringComparer.OrdinalIgnoreCase)
    ''' <summary>Columns: Sl.No, SKU No./Item ID., Article ID, Brand Name, Design Name, Size,
    ''' Cup Size, Colour, Quantity, Cost Price, M.R.P, Amount. The Total row is not included.</summary>
    Public Property Items As New DataTable("Items")
End Class

Public Module InvoiceCsv
    Public Function Parse(csv As String) As InvoiceData
        Dim rows As New List(Of String())
        Using parser As New TextFieldParser(New StringReader(csv))
            parser.SetDelimiters(",")
            parser.HasFieldsEnclosedInQuotes = True
            While Not parser.EndOfData
                rows.Add(parser.ReadFields())
            End While
        End Using

        Dim data As New InvoiceData()
        If rows.Count < 2 Then Return data

        ' Rows 1-2: header titles and values (first column is empty)
        For i = 1 To rows(0).Length - 1
            data.Header(rows(0)(i)) = If(i < rows(1).Length, rows(1)(i), "")
        Next

        ' Item title row starts with "Sl.No"
        Dim titleIndex = rows.FindIndex(Function(r) r.Length > 0 AndAlso r(0) = "Sl.No")
        If titleIndex < 0 Then Return data
        For Each title In rows(titleIndex)
            data.Items.Columns.Add(title, GetType(String))
        Next
        For i = titleIndex + 1 To rows.Count - 1
            Dim r = rows(i)
            If r.Length = 0 OrElse r(0) = "Total" Then Continue For
            Dim values(data.Items.Columns.Count - 1) As Object
            For c = 0 To values.Length - 1
                values(c) = If(c < r.Length, r(c), "")
            Next
            data.Items.Rows.Add(values)
        Next
        Return data
    End Function
End Module

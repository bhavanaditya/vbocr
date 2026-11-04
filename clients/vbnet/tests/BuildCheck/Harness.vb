' Uses the client and the dialog the way the documentation shows. Only compiled, never run.
Option Strict On
Option Explicit On
Imports System
Imports System.Data
Imports System.IO
Imports System.Windows.Forms

Public Class PurchaseForm
    Inherits Form

    Private Sub ScanInvoice()
        Using dlg As New VbOcrScanForm()
            dlg.AddFiles(New String() {"C:\Scans"})
            If dlg.ShowDialog(Me) = DialogResult.OK Then
                Dim invoice As VbOcrInvoice = dlg.Invoice
                Dim pages() As String = dlg.Files
                Console.WriteLine(invoice.GetHeader("Invoice Number") & pages.Length.ToString())
            End If
        End Using
    End Sub

    ' Doc snippet: scan a folder of separate invoices
    Private Sub ScanFolder(ByVal folder As String)
        Dim client As New VbOcrClient()
        client.EnsureServerRunning("C:\vbocr")
        Dim files() As String = VbOcrClient.GetInvoiceFiles(folder)
        For Each result As VbOcrResult In client.ScanEach(files)
            If result.ErrorMessage.Length > 0 Then
                Console.WriteLine(Path.GetFileName(result.SourceFile) & ": " & result.ErrorMessage)
                Continue For
            End If
            File.WriteAllText(Path.ChangeExtension(result.SourceFile, ".csv"), result.Csv, New System.Text.UTF8Encoding(True))
            For Each row As DataRow In result.Invoice.Items.Rows
                Dim qty As Decimal = VbOcrInvoice.ToDecimal(row("Quantity"))
            Next
        Next
    End Sub

    Private Sub Pick()
        Using dialog As New OpenFileDialog()
            dialog.Filter = VbOcrClient.FileDialogFilter
            dialog.Multiselect = True
        End Using
        Console.WriteLine(VbOcrClient.IsSupportedFile("a.PNG"))
    End Sub

    Public Shared Sub Main()
        Application.Run(New PurchaseForm())
    End Sub
End Class

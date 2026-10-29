' Example Windows Forms screen that uses OcrClient.
'
' Add to a form: Button "btnScan", DataGridView "gridItems", Label "lblStatus".
' Set OcrInstallFolder to the folder where VB OCR is installed.

Imports System.Windows.Forms

Public Class ExampleForm

    Private Const OcrInstallFolder As String = "C:\vbocr"

    Private Async Sub btnScan_Click(sender As Object, e As EventArgs) Handles btnScan.Click
        Using dialog As New OpenFileDialog() With {
            .Filter = "Invoices|*.jpg;*.jpeg;*.png;*.bmp;*.tif;*.tiff;*.webp;*.pdf",
            .Multiselect = True,
            .Title = "Select invoice (select several files for a multi-page invoice)"
        }
            If dialog.ShowDialog() <> DialogResult.OK Then Return

            btnScan.Enabled = False
            lblStatus.Text = "Reading invoice..."
            Try
                Using client As New OcrClient()
                    If Not Await client.EnsureServerRunningAsync(OcrInstallFolder) Then
                        lblStatus.Text = "OCR server did not start. Run start-server.bat to see the error."
                        Return
                    End If

                    Dim result = Await client.ScanAsync(dialog.FileNames)
                    Dim invoice = InvoiceCsv.Parse(result.Csv)

                    gridItems.DataSource = invoice.Items
                    lblStatus.Text = String.Format("{0} | Invoice {1} dated {2} | {3} items",
                        invoice.Header("Supplier Name"),
                        invoice.Header("Invoice Number"),
                        invoice.Header("Invoice Date"),
                        result.ItemCount)

                    If result.Warnings <> "" Then
                        MessageBox.Show("Please check: " & result.Warnings, "VB OCR",
                                        MessageBoxButtons.OK, MessageBoxIcon.Warning)
                    End If

                    ' Fill in values that are not printed on supplier invoices,
                    ' then save to your database:
                    '   invoice.Header("GRN Number") = txtGrn.Text
                    '   invoice.Header("Stock Received Date") = Date.Today.ToString("dd-MM-yyyy")
                End Using
            Catch ex As Exception
                lblStatus.Text = "Error: " & ex.Message
            Finally
                btnScan.Enabled = True
            End Try
        End Using
    End Sub

End Class

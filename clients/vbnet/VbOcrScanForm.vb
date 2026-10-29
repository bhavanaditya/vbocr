' Ready-made "Scan invoice" dialog for Windows Forms applications.
'
' The whole form is built in code (no .Designer.vb / .resx), so the file can be added to
' any existing WinForms project. Same compatibility as VbOcrClient.vb
' (Visual Studio 2005+, .NET Framework 2.0+ or .NET 6/8 Windows).
'
' Use:
'     Using dlg As New VbOcrScanForm()
'         If dlg.ShowDialog(Me) = DialogResult.OK Then
'             Dim invoice As VbOcrInvoice = dlg.Invoice     ' checked/corrected by the user
'             ' save invoice.Header(...) and invoice.Items to your database
'         End If
'     End Using

Option Strict On
Option Explicit On

Imports System
Imports System.ComponentModel
Imports System.Data
Imports System.Drawing
Imports System.Windows.Forms

Public Class VbOcrScanForm
    Inherits Form

    ''' <summary>Folder where VB OCR is installed (contains install.bat).</summary>
    Public InstallFolder As String = VbOcrClient.DefaultInstallFolder
    ''' <summary>Server address. Change it when VB OCR runs on another PC.</summary>
    Public ServerUrl As String = VbOcrClient.DefaultServerUrl
    ''' <summary>Optional: files to scan as soon as the dialog opens.</summary>
    Public FilesToScan() As String

    Private _invoice As VbOcrInvoice
    Private ReadOnly _worker As New BackgroundWorker()
    Private ReadOnly _btnSelect As New Button()
    Private ReadOnly _lblStatus As New Label()
    Private ReadOnly _gridHeader As New DataGridView()
    Private ReadOnly _gridItems As New DataGridView()
    Private ReadOnly _lblTotals As New Label()
    Private ReadOnly _btnOk As New Button()
    Private ReadOnly _btnCancel As New Button()

    Public Sub New()
        Text = "Scan invoice"
        Size = New Size(1100, 700)
        MinimumSize = New Size(700, 450)
        StartPosition = FormStartPosition.CenterParent
        Font = New Font("Segoe UI", 9.0F)

        Dim top As New Panel()
        top.Dock = DockStyle.Top
        top.Height = 44
        top.Width = ClientSize.Width
        _btnSelect.Text = "Select invoice..."
        _btnSelect.SetBounds(10, 8, 140, 28)
        _lblStatus.SetBounds(160, 13, top.Width - 170, 20)
        _lblStatus.Anchor = AnchorStyles.Left Or AnchorStyles.Top Or AnchorStyles.Right
        _lblStatus.Text = "Select the invoice image(s). Select several files for a multi-page invoice."
        top.Controls.Add(_btnSelect)
        top.Controls.Add(_lblStatus)

        ConfigureGrid(_gridHeader)
        _gridHeader.Dock = DockStyle.Top
        _gridHeader.Height = 120
        _gridHeader.AllowUserToAddRows = False
        _gridHeader.Columns.Add("Field", "Field")
        _gridHeader.Columns.Add("Value", "Value")
        _gridHeader.Columns(0).ReadOnly = True
        _gridHeader.Columns(0).Width = 180
        _gridHeader.Columns(1).AutoSizeMode = DataGridViewAutoSizeColumnMode.Fill

        ConfigureGrid(_gridItems)
        _gridItems.Dock = DockStyle.Fill
        _gridItems.AllowUserToAddRows = False

        Dim bottom As New Panel()
        bottom.Dock = DockStyle.Bottom
        bottom.Height = 46
        bottom.Width = ClientSize.Width
        _lblTotals.SetBounds(10, 14, 600, 20)
        _btnOk.Text = "Use these values"
        _btnOk.SetBounds(bottom.Width - 290, 9, 150, 28)
        _btnOk.Anchor = AnchorStyles.Right Or AnchorStyles.Top
        _btnOk.Enabled = False
        _btnCancel.Text = "Cancel"
        _btnCancel.SetBounds(bottom.Width - 130, 9, 120, 28)
        _btnCancel.Anchor = AnchorStyles.Right Or AnchorStyles.Top
        _btnCancel.DialogResult = DialogResult.Cancel
        bottom.Controls.Add(_lblTotals)
        bottom.Controls.Add(_btnOk)
        bottom.Controls.Add(_btnCancel)

        Controls.Add(_gridItems)
        Controls.Add(_gridHeader)
        Controls.Add(top)
        Controls.Add(bottom)
        CancelButton = _btnCancel

        AddHandler _btnSelect.Click, AddressOf SelectClicked
        AddHandler _btnOk.Click, AddressOf OkClicked
        AddHandler _gridItems.CellEndEdit, AddressOf ItemsEdited
        AddHandler _worker.DoWork, AddressOf WorkerDoWork
        AddHandler _worker.RunWorkerCompleted, AddressOf WorkerCompleted
    End Sub

    ''' <summary>The scanned invoice, including the user's corrections. Set after OK.</summary>
    Public ReadOnly Property Invoice() As VbOcrInvoice
        Get
            Return _invoice
        End Get
    End Property

    Protected Overrides Sub OnShown(ByVal e As EventArgs)
        MyBase.OnShown(e)
        If FilesToScan IsNot Nothing AndAlso FilesToScan.Length > 0 Then StartScan(FilesToScan)
    End Sub

    Protected Overrides Sub OnFormClosing(ByVal e As FormClosingEventArgs)
        If _worker.IsBusy Then
            e.Cancel = True   ' wait for the running scan to finish
            _lblStatus.Text = "Please wait, the scan is still running..."
        End If
        MyBase.OnFormClosing(e)
    End Sub

    Private Sub SelectClicked(ByVal sender As Object, ByVal e As EventArgs)
        Using dialog As New OpenFileDialog()
            dialog.Filter = "Invoices|*.jpg;*.jpeg;*.png;*.bmp;*.tif;*.tiff;*.webp;*.pdf|All files|*.*"
            dialog.Multiselect = True
            dialog.Title = "Select invoice (several files = pages of one invoice)"
            If dialog.ShowDialog(Me) = DialogResult.OK Then StartScan(dialog.FileNames)
        End Using
    End Sub

    Private Sub StartScan(ByVal files() As String)
        If _worker.IsBusy Then Return
        _btnSelect.Enabled = False
        _btnOk.Enabled = False
        _lblStatus.Text = "Reading invoice, please wait (this can take up to a minute)..."
        Cursor = Cursors.WaitCursor
        _worker.RunWorkerAsync(files)
    End Sub

    ' Runs on a background thread: no access to controls here.
    Private Sub WorkerDoWork(ByVal sender As Object, ByVal e As DoWorkEventArgs)
        Dim files() As String = CType(e.Argument, String())
        Dim client As New VbOcrClient(ServerUrl)
        If Not client.IsReady() Then
            If Not IsLocalServer() Then
                Throw New VbOcrException("The VB OCR server at " & ServerUrl & " is not running.")
            End If
            If Not client.EnsureServerRunning(InstallFolder) Then
                Throw New VbOcrException("The VB OCR server did not start. Run " & InstallFolder & "\start-server.bat to see the error.")
            End If
        End If
        e.Result = client.Scan(files)
    End Sub

    Private Sub WorkerCompleted(ByVal sender As Object, ByVal e As RunWorkerCompletedEventArgs)
        Cursor = Cursors.Default
        _btnSelect.Enabled = True
        If e.Error IsNot Nothing Then
            _lblStatus.Text = "Error: " & e.Error.Message
            MessageBox.Show(Me, e.Error.Message, "Scan invoice", MessageBoxButtons.OK, MessageBoxIcon.Error)
            Return
        End If

        Dim result As VbOcrResult = CType(e.Result, VbOcrResult)
        _invoice = result.Invoice

        _gridHeader.Rows.Clear()
        For Each title As String In VbOcrInvoice.HeaderTitles
            _gridHeader.Rows.Add(title, _invoice.GetHeader(title))
        Next
        _gridItems.DataSource = _invoice.Items
        UpdateTotals()

        _btnOk.Enabled = _invoice.Items.Rows.Count > 0
        If result.Warnings.Length > 0 Then
            _lblStatus.Text = "Please check: " & result.Warnings
        Else
            _lblStatus.Text = _invoice.Items.Rows.Count.ToString() & " items read. Check the values and correct them if needed."
        End If
    End Sub

    Private Sub ItemsEdited(ByVal sender As Object, ByVal e As DataGridViewCellEventArgs)
        UpdateTotals()
    End Sub

    Private Sub UpdateTotals()
        If _invoice Is Nothing Then Return
        Dim qty As Decimal = 0D
        Dim amount As Decimal = 0D
        For Each row As DataRow In _invoice.Items.Rows
            If row.RowState = DataRowState.Deleted Then Continue For
            qty += VbOcrInvoice.ToDecimal(row("Quantity"))
            amount += VbOcrInvoice.ToDecimal(row("Amount"))
        Next
        _lblTotals.Text = "Total quantity: " & qty.ToString("0.##") & "     Total amount: " & amount.ToString("0.00") & _
            "     (compare with the total printed on the invoice)"
    End Sub

    Private Sub OkClicked(ByVal sender As Object, ByVal e As EventArgs)
        _gridHeader.EndEdit()
        _gridItems.EndEdit()
        BindingContext(_invoice.Items).EndCurrentEdit()
        For Each row As DataGridViewRow In _gridHeader.Rows
            Dim value As String = ""
            If row.Cells(1).Value IsNot Nothing Then value = Convert.ToString(row.Cells(1).Value)
            _invoice.Header(Convert.ToString(row.Cells(0).Value)) = value
        Next
        DialogResult = DialogResult.OK
    End Sub

    Private Function IsLocalServer() As Boolean
        Dim url As String = ServerUrl.ToLowerInvariant()
        Return url.IndexOf("://127.0.0.1", StringComparison.Ordinal) >= 0 OrElse url.IndexOf("://localhost", StringComparison.Ordinal) >= 0
    End Function

    Private Shared Sub ConfigureGrid(ByVal grid As DataGridView)
        grid.AllowUserToResizeRows = False
        grid.RowHeadersWidth = 24
        grid.BackgroundColor = SystemColors.Window
        grid.ColumnHeadersHeightSizeMode = DataGridViewColumnHeadersHeightSizeMode.AutoSize
    End Sub
End Class

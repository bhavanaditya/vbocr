' Ready-made "Scan invoice" dialog for Windows Forms applications.
'
' The whole form is built in code (no .Designer.vb / .resx), so the file can be added to
' any existing WinForms project. Same compatibility as VbOcrClient.vb
' (Visual Studio 2008+, .NET Framework 2.0+ or .NET 6/8 Windows).
'
' Ways to add invoice pages (jpg, png, bmp, tif, webp, gif, pdf):
'   - "Add files..."   select one or more files
'   - "Add folder..."  every image / PDF in a folder
'   - "Paste"          Ctrl+V: an image copied to the clipboard (screenshot, WhatsApp, browser)
'                      or files copied in Explorer
'   - drag and drop    files or folders from Explorer onto the dialog
' All listed files are pages of ONE invoice, scanned in list order (use Up / Down).
' For a pile of separate invoices use VbOcrClient.ScanEach or scan-folder.bat.
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
Imports System.Collections.Generic
Imports System.Collections.Specialized
Imports System.ComponentModel
Imports System.Data
Imports System.Drawing
Imports System.Drawing.Imaging
Imports System.IO
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
    Private ReadOnly _tempFiles As New List(Of String)
    Private ReadOnly _worker As New BackgroundWorker()
    Private ReadOnly _lstFiles As New ListBox()
    Private ReadOnly _btnAddFiles As New Button()
    Private ReadOnly _btnAddFolder As New Button()
    Private ReadOnly _btnPaste As New Button()
    Private ReadOnly _btnUp As New Button()
    Private ReadOnly _btnDown As New Button()
    Private ReadOnly _btnRemove As New Button()
    Private ReadOnly _btnClear As New Button()
    Private ReadOnly _btnScan As New Button()
    Private ReadOnly _lblStatus As New Label()
    Private ReadOnly _gridHeader As New DataGridView()
    Private ReadOnly _gridItems As New DataGridView()
    Private ReadOnly _lblTotals As New Label()
    Private ReadOnly _btnOk As New Button()
    Private ReadOnly _btnCancel As New Button()

    Public Sub New()
        Text = "Scan invoice"
        Size = New Size(1200, 720)
        MinimumSize = New Size(800, 480)
        StartPosition = FormStartPosition.CenterParent
        Font = New Font("Segoe UI", 9.0F)
        KeyPreview = True
        AllowDrop = True

        ' Left: the list of pages and the ways to add them
        Dim left As New Panel()
        left.Dock = DockStyle.Left
        left.Width = 270
        left.Padding = New Padding(8)

        Dim lblPages As New Label()
        lblPages.Text = "Invoice pages (scanned in this order):"
        lblPages.Dock = DockStyle.Top
        lblPages.Height = 20

        Dim addButtons As New FlowLayoutPanel()
        addButtons.Dock = DockStyle.Top
        addButtons.Height = 66
        SetupButton(_btnAddFiles, "Add files...", 122, addButtons)
        SetupButton(_btnAddFolder, "Add folder...", 122, addButtons)
        SetupButton(_btnPaste, "Paste (Ctrl+V)", 122, addButtons)
        SetupButton(_btnClear, "Clear", 122, addButtons)

        _lstFiles.Dock = DockStyle.Fill
        _lstFiles.IntegralHeight = False
        _lstFiles.HorizontalScrollbar = True
        _lstFiles.SelectionMode = SelectionMode.MultiExtended
        _lstFiles.AllowDrop = True

        Dim listButtons As New FlowLayoutPanel()
        listButtons.Dock = DockStyle.Bottom
        listButtons.Height = 72
        SetupButton(_btnUp, "Up", 78, listButtons)
        SetupButton(_btnDown, "Down", 78, listButtons)
        SetupButton(_btnRemove, "Remove", 78, listButtons)
        SetupButton(_btnScan, "Scan", 250, listButtons)
        _btnScan.Font = New Font(Font, FontStyle.Bold)

        left.Controls.Add(_lstFiles)
        left.Controls.Add(listButtons)
        left.Controls.Add(addButtons)
        left.Controls.Add(lblPages)

        ' Right: status, results and totals
        Dim top As New Panel()
        top.Dock = DockStyle.Top
        top.Height = 34
        _lblStatus.Dock = DockStyle.Fill
        _lblStatus.TextAlign = ContentAlignment.MiddleLeft
        _lblStatus.Text = "Add the invoice page(s): Add files, Add folder, Paste, or drag files here. Then click Scan."
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

        Dim right As New Panel()
        right.Dock = DockStyle.Fill
        right.Controls.Add(_gridItems)
        right.Controls.Add(_gridHeader)
        right.Controls.Add(top)

        Controls.Add(right)
        Controls.Add(left)
        Controls.Add(bottom)
        CancelButton = _btnCancel

        AddHandler _btnAddFiles.Click, AddressOf AddFilesClicked
        AddHandler _btnAddFolder.Click, AddressOf AddFolderClicked
        AddHandler _btnPaste.Click, AddressOf PasteClicked
        AddHandler _btnClear.Click, AddressOf ClearClicked
        AddHandler _btnUp.Click, AddressOf UpClicked
        AddHandler _btnDown.Click, AddressOf DownClicked
        AddHandler _btnRemove.Click, AddressOf RemoveClicked
        AddHandler _btnScan.Click, AddressOf ScanClicked
        AddHandler _btnOk.Click, AddressOf OkClicked
        AddHandler _lstFiles.DragEnter, AddressOf FilesDragEnter
        AddHandler _lstFiles.DragDrop, AddressOf FilesDragDrop
        AddHandler _lstFiles.KeyDown, AddressOf ListKeyDown
        AddHandler _gridItems.CellEndEdit, AddressOf ItemsEdited
        AddHandler _worker.DoWork, AddressOf WorkerDoWork
        AddHandler _worker.RunWorkerCompleted, AddressOf WorkerCompleted
        UpdateButtons()
    End Sub

    ''' <summary>The scanned invoice, including the user's corrections. Set after OK.</summary>
    Public ReadOnly Property Invoice() As VbOcrInvoice
        Get
            Return _invoice
        End Get
    End Property

    ''' <summary>The files currently in the page list.</summary>
    Public ReadOnly Property Files() As String()
        Get
            Dim list As New List(Of String)
            For Each item As Object In _lstFiles.Items
                list.Add(CType(item, PageItem).FilePath)
            Next
            Return list.ToArray()
        End Get
    End Property

    ''' <summary>Adds files and/or folders to the page list. Unsupported files are skipped.</summary>
    Public Sub AddFiles(ByVal paths() As String)
        Dim skipped As Integer = 0
        Dim added As Integer = 0
        For Each p As String In paths
            If Directory.Exists(p) Then
                For Each f As String In VbOcrClient.GetInvoiceFiles(p)
                    If AddOne(f) Then added += 1
                Next
            ElseIf File.Exists(p) AndAlso VbOcrClient.IsSupportedFile(p) Then
                If AddOne(p) Then added += 1
            Else
                skipped += 1
            End If
        Next
        UpdateButtons()
        Dim message As String = added.ToString() & " page(s) added. Click Scan when all pages are in the list."
        If skipped > 0 Then message &= "  " & skipped.ToString() & " file(s) skipped: not an image or PDF."
        _lblStatus.Text = message
    End Sub

    Protected Overrides Sub OnShown(ByVal e As EventArgs)
        MyBase.OnShown(e)
        If FilesToScan IsNot Nothing AndAlso FilesToScan.Length > 0 Then
            AddFiles(FilesToScan)
            If _lstFiles.Items.Count > 0 Then StartScan()
        End If
    End Sub

    Protected Overrides Sub OnKeyDown(ByVal e As KeyEventArgs)
        If e.Control AndAlso e.KeyCode = Keys.V AndAlso Not _gridHeader.IsCurrentCellInEditMode _
                AndAlso Not _gridItems.IsCurrentCellInEditMode AndAlso Not _gridHeader.Focused AndAlso Not _gridItems.Focused Then
            PasteClicked(Me, EventArgs.Empty)
            e.Handled = True
        End If
        MyBase.OnKeyDown(e)
    End Sub

    Protected Overrides Sub OnDragEnter(ByVal e As DragEventArgs)
        MyBase.OnDragEnter(e)
        FilesDragEnter(Me, e)
    End Sub

    Protected Overrides Sub OnDragDrop(ByVal e As DragEventArgs)
        MyBase.OnDragDrop(e)
        FilesDragDrop(Me, e)
    End Sub

    Protected Overrides Sub OnFormClosing(ByVal e As FormClosingEventArgs)
        If _worker.IsBusy Then
            e.Cancel = True   ' wait for the running scan to finish
            _lblStatus.Text = "Please wait, the scan is still running..."
        End If
        MyBase.OnFormClosing(e)
    End Sub

    Protected Overrides Sub OnFormClosed(ByVal e As FormClosedEventArgs)
        For Each f As String In _tempFiles
            Try
                File.Delete(f)
            Catch ex As IOException
            Catch ex As UnauthorizedAccessException
            End Try
        Next
        _tempFiles.Clear()
        MyBase.OnFormClosed(e)
    End Sub

    Private Sub AddFilesClicked(ByVal sender As Object, ByVal e As EventArgs)
        Using dialog As New OpenFileDialog()
            dialog.Filter = VbOcrClient.FileDialogFilter
            dialog.Multiselect = True
            dialog.Title = "Select invoice page(s)"
            If dialog.ShowDialog(Me) = DialogResult.OK Then AddFiles(dialog.FileNames)
        End Using
    End Sub

    Private Sub AddFolderClicked(ByVal sender As Object, ByVal e As EventArgs)
        Using dialog As New FolderBrowserDialog()
            dialog.Description = "Select the folder with the invoice page images"
            If dialog.ShowDialog(Me) = DialogResult.OK Then AddFiles(New String() {dialog.SelectedPath})
        End Using
    End Sub

    Private Sub PasteClicked(ByVal sender As Object, ByVal e As EventArgs)
        If _worker.IsBusy Then Return
        Try
            If Clipboard.ContainsFileDropList() Then
                Dim list As StringCollection = Clipboard.GetFileDropList()
                Dim paths(list.Count - 1) As String
                list.CopyTo(paths, 0)
                AddFiles(paths)
            ElseIf Clipboard.ContainsImage() Then
                Using image As Image = Clipboard.GetImage()
                    Dim tempPath As String = Path.Combine(Path.GetTempPath(), _
                        "vbocr_pasted_" & DateTime.Now.ToString("yyyyMMdd_HHmmss_fff") & ".png")
                    image.Save(tempPath, ImageFormat.Png)
                    _tempFiles.Add(tempPath)
                    _lstFiles.Items.Add(New PageItem(tempPath, "Pasted image " & (_lstFiles.Items.Count + 1).ToString()))
                End Using
                UpdateButtons()
                _lblStatus.Text = "Pasted image added. Click Scan when all pages are in the list."
            Else
                _lblStatus.Text = "The clipboard has no image. Copy an invoice image (or files in Explorer) first."
            End If
        Catch ex As System.Runtime.InteropServices.ExternalException
            _lblStatus.Text = "Could not read the clipboard: " & ex.Message
        End Try
    End Sub

    Private Sub ClearClicked(ByVal sender As Object, ByVal e As EventArgs)
        _lstFiles.Items.Clear()
        UpdateButtons()
    End Sub

    Private Sub RemoveClicked(ByVal sender As Object, ByVal e As EventArgs)
        For i As Integer = _lstFiles.SelectedIndices.Count - 1 To 0 Step -1
            _lstFiles.Items.RemoveAt(_lstFiles.SelectedIndices(i))
        Next
        UpdateButtons()
    End Sub

    Private Sub UpClicked(ByVal sender As Object, ByVal e As EventArgs)
        MoveSelected(-1)
    End Sub

    Private Sub DownClicked(ByVal sender As Object, ByVal e As EventArgs)
        MoveSelected(1)
    End Sub

    Private Sub MoveSelected(ByVal offset As Integer)
        If _lstFiles.SelectedIndices.Count <> 1 Then Return
        Dim index As Integer = _lstFiles.SelectedIndex
        Dim target As Integer = index + offset
        If target < 0 OrElse target >= _lstFiles.Items.Count Then Return
        Dim item As Object = _lstFiles.Items(index)
        _lstFiles.Items.RemoveAt(index)
        _lstFiles.Items.Insert(target, item)
        _lstFiles.ClearSelected()
        _lstFiles.SelectedIndex = target
    End Sub

    Private Sub ListKeyDown(ByVal sender As Object, ByVal e As KeyEventArgs)
        If e.KeyCode = Keys.Delete Then
            RemoveClicked(sender, EventArgs.Empty)
            e.Handled = True
        End If
    End Sub

    Private Sub FilesDragEnter(ByVal sender As Object, ByVal e As DragEventArgs)
        If Not _worker.IsBusy AndAlso e.Data.GetDataPresent(DataFormats.FileDrop) Then
            e.Effect = DragDropEffects.Copy
        Else
            e.Effect = DragDropEffects.None
        End If
    End Sub

    Private Sub FilesDragDrop(ByVal sender As Object, ByVal e As DragEventArgs)
        Dim paths() As String = TryCast(e.Data.GetData(DataFormats.FileDrop), String())
        If paths IsNot Nothing AndAlso Not _worker.IsBusy Then AddFiles(paths)
    End Sub

    Private Sub ScanClicked(ByVal sender As Object, ByVal e As EventArgs)
        StartScan()
    End Sub

    Private Sub StartScan()
        If _worker.IsBusy OrElse _lstFiles.Items.Count = 0 Then Return
        _btnOk.Enabled = False
        SetListEnabled(False)
        _lblStatus.Text = "Reading " & _lstFiles.Items.Count.ToString() & " page(s), please wait (this can take up to a minute per page)..."
        Cursor = Cursors.WaitCursor
        _worker.RunWorkerAsync(Files)
    End Sub

    ' Runs on a background thread: no access to controls here.
    Private Sub WorkerDoWork(ByVal sender As Object, ByVal e As DoWorkEventArgs)
        Dim pages() As String = CType(e.Argument, String())
        Dim client As New VbOcrClient(ServerUrl)
        If Not client.IsReady() Then
            If Not IsLocalServer() Then
                Throw New VbOcrException("The VB OCR server at " & ServerUrl & " is not running.")
            End If
            If Not client.EnsureServerRunning(InstallFolder) Then
                Throw New VbOcrException("The VB OCR server did not start. Run " & InstallFolder & "\start-server.bat to see the error.")
            End If
        End If
        e.Result = client.Scan(pages)
    End Sub

    Private Sub WorkerCompleted(ByVal sender As Object, ByVal e As RunWorkerCompletedEventArgs)
        Cursor = Cursors.Default
        SetListEnabled(True)
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

    Private Function AddOne(ByVal filePath As String) As Boolean
        Dim full As String = Path.GetFullPath(filePath)
        For Each item As Object In _lstFiles.Items
            If String.Equals(CType(item, PageItem).FilePath, full, StringComparison.OrdinalIgnoreCase) Then Return False
        Next
        _lstFiles.Items.Add(New PageItem(full, Path.GetFileName(full)))
        Return True
    End Function

    Private Sub SetListEnabled(ByVal enabled As Boolean)
        _lstFiles.Enabled = enabled
        _btnAddFiles.Enabled = enabled
        _btnAddFolder.Enabled = enabled
        _btnPaste.Enabled = enabled
        If enabled Then
            UpdateButtons()
        Else
            _btnUp.Enabled = False
            _btnDown.Enabled = False
            _btnRemove.Enabled = False
            _btnClear.Enabled = False
            _btnScan.Enabled = False
        End If
    End Sub

    Private Sub UpdateButtons()
        Dim hasFiles As Boolean = _lstFiles.Items.Count > 0
        _btnScan.Enabled = hasFiles AndAlso Not _worker.IsBusy
        _btnClear.Enabled = hasFiles
        _btnRemove.Enabled = hasFiles
        _btnUp.Enabled = _lstFiles.Items.Count > 1
        _btnDown.Enabled = _lstFiles.Items.Count > 1
        If hasFiles Then
            _btnScan.Text = "Scan " & _lstFiles.Items.Count.ToString() & " page(s)"
        Else
            _btnScan.Text = "Scan"
        End If
    End Sub

    Private Function IsLocalServer() As Boolean
        Dim url As String = ServerUrl.ToLowerInvariant()
        Return url.IndexOf("://127.0.0.1", StringComparison.Ordinal) >= 0 OrElse url.IndexOf("://localhost", StringComparison.Ordinal) >= 0
    End Function

    Private Shared Sub SetupButton(ByVal button As Button, ByVal text As String, ByVal width As Integer, ByVal parent As Control)
        button.Text = text
        button.Width = width
        button.Height = 28
        parent.Controls.Add(button)
    End Sub

    Private Shared Sub ConfigureGrid(ByVal grid As DataGridView)
        grid.AllowUserToResizeRows = False
        grid.RowHeadersWidth = 24
        grid.BackgroundColor = SystemColors.Window
        grid.ColumnHeadersHeightSizeMode = DataGridViewColumnHeadersHeightSizeMode.AutoSize
    End Sub

    ' One entry in the page list: full path plus the name shown to the user.
    Private Class PageItem
        Public ReadOnly FilePath As String
        Private ReadOnly _display As String

        Public Sub New(ByVal filePath As String, ByVal display As String)
            Me.FilePath = filePath
            _display = display
        End Sub

        Public Overrides Function ToString() As String
            Return _display
        End Function
    End Class
End Class

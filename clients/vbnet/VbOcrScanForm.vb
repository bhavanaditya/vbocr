' Ready-made "Scan invoice" dialog for Windows Forms applications.
'
' The whole form is built in code (no .Designer.vb / .resx), so the file can be added to
' any existing WinForms project. Same compatibility as VbOcrClient.vb
' (Visual Studio 2008+, .NET Framework 2.0+ or .NET 6/8 Windows).
'
' Ways to add invoice pages (jpg, png, bmp, tif, webp, gif, pdf):
'   - "Files..."       select one or more files
'   - "Folder..."      every image / PDF in a folder
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
Imports System.Drawing.Drawing2D
Imports System.Drawing.Imaging
Imports System.Globalization
Imports System.IO
Imports System.Windows.Forms

Public Class VbOcrScanForm
    Inherits Form

    ''' <summary>Folder where VB OCR is installed (contains install.bat).</summary>
    Public InstallFolder As String = VbOcrClient.DefaultInstallFolder
    ''' <summary>Server address. Change it when VB OCR runs on another PC.</summary>
    Public ServerUrl As String = VbOcrClient.DefaultServerUrl
    ''' <summary>Access key, when the server has server.api_key set. Empty = no key.</summary>
    Public ApiKey As String = ""
    ''' <summary>Optional: files to scan as soon as the dialog opens.</summary>
    Public FilesToScan() As String

    ' Colour scheme (same as the browser page)
    Private Shared ReadOnly Primary As Color = Color.FromArgb(67, 56, 202)
    Private Shared ReadOnly PrimaryDark As Color = Color.FromArgb(55, 48, 163)
    Private Shared ReadOnly PrimarySoft As Color = Color.FromArgb(238, 242, 255)
    Private Shared ReadOnly PageBack As Color = Color.FromArgb(245, 246, 250)
    Private Shared ReadOnly Surface As Color = Color.White
    Private Shared ReadOnly Surface2 As Color = Color.FromArgb(249, 250, 251)
    Private Shared ReadOnly Border As Color = Color.FromArgb(229, 231, 235)
    Private Shared ReadOnly BorderStrong As Color = Color.FromArgb(209, 213, 219)
    Private Shared ReadOnly TextColor As Color = Color.FromArgb(17, 24, 39)
    Private Shared ReadOnly Text2 As Color = Color.FromArgb(75, 85, 99)
    Private Shared ReadOnly Muted As Color = Color.FromArgb(107, 114, 128)
    Private Shared ReadOnly Success As Color = Color.FromArgb(21, 128, 61)
    Private Shared ReadOnly SuccessSoft As Color = Color.FromArgb(220, 252, 231)
    Private Shared ReadOnly Warning As Color = Color.FromArgb(180, 83, 9)
    Private Shared ReadOnly WarningSoft As Color = Color.FromArgb(254, 243, 199)
    Private Shared ReadOnly Danger As Color = Color.FromArgb(185, 28, 28)
    Private Shared ReadOnly DangerSoft As Color = Color.FromArgb(254, 226, 226)

    Private Enum Tone
        Info
        Busy
        Good
        Warn
        Bad
    End Enum

    Private _invoice As VbOcrInvoice
    Private _printedTotal As Decimal = -1D
    ' Values the OCR was not sure about: item row -> column titles. Cleared when the user edits them.
    Private ReadOnly _unsureItems As New Dictionary(Of DataRow, List(Of String))
    Private _scanStarted As DateTime
    Private ReadOnly _tempFiles As New List(Of String)
    Private ReadOnly _worker As New BackgroundWorker()
    Private ReadOnly _timer As New Timer()

    Private ReadOnly _fontBase As New Font("Segoe UI", 9.0F)
    Private ReadOnly _fontBold As New Font("Segoe UI", 9.0F, FontStyle.Bold)
    Private ReadOnly _fontSmall As New Font("Segoe UI", 8.25F)
    Private ReadOnly _fontTitle As New Font("Segoe UI", 13.0F, FontStyle.Bold)
    Private ReadOnly _fontStat As New Font("Segoe UI", 14.0F, FontStyle.Bold)

    Private ReadOnly _drop As New Panel()
    Private ReadOnly _lstFiles As New ListBox()
    Private ReadOnly _lblCount As New Label()
    Private ReadOnly _preview As New PictureBox()
    Private ReadOnly _lblPreview As New Label()
    Private ReadOnly _btnAddFiles As New Button()
    Private ReadOnly _btnAddFolder As New Button()
    Private ReadOnly _btnPaste As New Button()
    Private ReadOnly _btnUp As New Button()
    Private ReadOnly _btnDown As New Button()
    Private ReadOnly _btnRemove As New Button()
    Private ReadOnly _btnClear As New Button()
    Private ReadOnly _btnScan As New Button()

    Private ReadOnly _banner As New Panel()
    Private ReadOnly _lblStatus As New Label()
    Private ReadOnly _progress As New ProgressBar()
    Private ReadOnly _statItems As New Label()
    Private ReadOnly _statQty As New Label()
    Private ReadOnly _statAmount As New Label()
    Private ReadOnly _statPrinted As New Label()
    Private ReadOnly _results As New Panel()
    Private ReadOnly _empty As New Label()
    Private ReadOnly _gridHeader As New DataGridView()
    Private ReadOnly _gridItems As New DataGridView()
    Private ReadOnly _btnOk As New Button()
    Private ReadOnly _btnCancel As New Button()

    Public Sub New()
        Text = "Scan invoice"
        Size = New Size(1280, 800)
        MinimumSize = New Size(960, 600)
        StartPosition = FormStartPosition.CenterParent
        Font = _fontBase
        BackColor = PageBack
        ForeColor = TextColor
        KeyPreview = True
        AllowDrop = True

        Controls.Add(BuildResults())
        Controls.Add(BuildPagesPanel())
        Controls.Add(BuildFooter())
        Controls.Add(BuildTitleBar())
        CancelButton = _btnCancel

        _timer.Interval = 500
        AddHandler _timer.Tick, AddressOf TimerTick
        AddHandler _worker.DoWork, AddressOf WorkerDoWork
        AddHandler _worker.RunWorkerCompleted, AddressOf WorkerCompleted
        SetStatus(Tone.Info, "Add the invoice page(s): Files, Folder, Paste (Ctrl+V) or drag them onto the list. Then click Scan.")
        UpdateButtons()
    End Sub

    ''' <summary>The scanned invoice, including the user's corrections. Set after OK.</summary>
    Public ReadOnly Property Invoice() As VbOcrInvoice
        Get
            Return _invoice
        End Get
    End Property

    ''' <summary>The files currently in the page list, in page order.</summary>
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
                    If AddOne(f, "") Then added += 1
                Next
            ElseIf File.Exists(p) AndAlso VbOcrClient.IsSupportedFile(p) Then
                If AddOne(p, "") Then added += 1
            Else
                skipped += 1
            End If
        Next
        UpdateButtons()
        If added > 0 AndAlso _lstFiles.SelectedIndex < 0 Then _lstFiles.SelectedIndex = _lstFiles.Items.Count - 1
        Dim message As String = added.ToString() & " page(s) added. Click Scan when all pages are in the list."
        If skipped > 0 Then
            SetStatus(Tone.Warn, message & "  " & skipped.ToString() & " file(s) skipped: not an image or PDF.")
        Else
            SetStatus(Tone.Info, message)
        End If
    End Sub

    ' ------------------------------------------------------------------ layout

    Private Function BuildTitleBar() As Control
        Dim bar As New Panel()
        bar.Dock = DockStyle.Top
        bar.Height = 60
        bar.BackColor = Surface
        AddHandler bar.Paint, AddressOf PaintBottomBorder

        Dim logo As New Label()
        logo.Text = "VB"
        logo.Font = _fontBold
        logo.ForeColor = Color.White
        logo.BackColor = Primary
        logo.TextAlign = ContentAlignment.MiddleCenter
        logo.SetBounds(18, 12, 36, 36)

        Dim title As New Label()
        title.Text = "Scan supplier invoice"
        title.Font = _fontTitle
        title.AutoSize = True
        title.Location = New Point(64, 9)

        Dim subtitle As New Label()
        subtitle.Text = "Add the pages, click Scan, check the values, then use them in the purchase entry."
        subtitle.ForeColor = Muted
        subtitle.AutoSize = True
        subtitle.Location = New Point(66, 34)

        bar.Controls.Add(logo)
        bar.Controls.Add(title)
        bar.Controls.Add(subtitle)
        Return bar
    End Function

    Private Function BuildPagesPanel() As Control
        Dim outer As New Panel()
        outer.Dock = DockStyle.Left
        outer.Width = 330
        outer.Padding = New Padding(14, 14, 7, 14)

        Dim card As New Panel()
        card.Dock = DockStyle.Fill
        card.BackColor = Surface
        card.Padding = New Padding(14)
        AddHandler card.Paint, AddressOf PaintCardBorder

        ' Step 1 + drop zone
        Dim step1 As Label = StepLabel("1", "Add invoice pages")

        _drop.Dock = DockStyle.Top
        _drop.Height = 112
        _drop.BackColor = Surface2
        _drop.AllowDrop = True
        AddHandler _drop.Paint, AddressOf PaintDropZone
        Dim dropTitle As New Label()
        dropTitle.Text = "Drop files or a folder here"
        dropTitle.Font = _fontBold
        dropTitle.TextAlign = ContentAlignment.MiddleCenter
        dropTitle.Dock = DockStyle.Top
        dropTitle.Height = 30
        dropTitle.BackColor = Color.Transparent
        Dim dropHint As New Label()
        dropHint.Text = "or paste a screenshot with Ctrl+V"
        dropHint.ForeColor = Muted
        dropHint.TextAlign = ContentAlignment.TopCenter
        dropHint.Dock = DockStyle.Top
        dropHint.Height = 22
        dropHint.BackColor = Color.Transparent
        Dim addRow As New FlowLayoutPanel()
        addRow.Dock = DockStyle.Top
        addRow.Height = 40
        addRow.Padding = New Padding(12, 2, 0, 0)
        addRow.BackColor = Color.Transparent
        SecondaryButton(_btnAddFiles, "Files...", 82, addRow)
        SecondaryButton(_btnAddFolder, "Folder...", 82, addRow)
        SecondaryButton(_btnPaste, "Paste", 82, addRow)
        _drop.Controls.Add(addRow)
        _drop.Controls.Add(dropHint)
        _drop.Controls.Add(dropTitle)
        _drop.Padding = New Padding(0, 6, 0, 0)

        ' Count row
        Dim countRow As New Panel()
        countRow.Dock = DockStyle.Top
        countRow.Height = 32
        _lblCount.Dock = DockStyle.Fill
        _lblCount.ForeColor = Muted
        _lblCount.TextAlign = ContentAlignment.BottomLeft
        countRow.Controls.Add(_lblCount)

        ' Page list
        _lstFiles.Dock = DockStyle.Fill
        _lstFiles.IntegralHeight = False
        _lstFiles.BorderStyle = BorderStyle.None
        _lstFiles.DrawMode = DrawMode.OwnerDrawFixed
        _lstFiles.ItemHeight = 42
        _lstFiles.SelectionMode = SelectionMode.MultiExtended
        _lstFiles.AllowDrop = True
        Dim listFrame As New Panel()
        listFrame.Dock = DockStyle.Fill
        listFrame.Padding = New Padding(1)
        listFrame.BackColor = Border
        listFrame.Controls.Add(_lstFiles)

        ' List buttons
        Dim listButtons As New FlowLayoutPanel()
        listButtons.Dock = DockStyle.Bottom
        listButtons.Height = 38
        listButtons.Padding = New Padding(0, 5, 0, 0)
        SecondaryButton(_btnUp, "Up", 56, listButtons)
        SecondaryButton(_btnDown, "Down", 60, listButtons)
        SecondaryButton(_btnRemove, "Remove", 70, listButtons)
        SecondaryButton(_btnClear, "Clear", 58, listButtons)

        ' Preview of the selected page
        Dim previewBox As New Panel()
        previewBox.Dock = DockStyle.Bottom
        previewBox.Height = 170
        previewBox.Padding = New Padding(0, 6, 0, 0)
        _preview.Dock = DockStyle.Fill
        _preview.SizeMode = PictureBoxSizeMode.Zoom
        _preview.BackColor = Surface2
        _lblPreview.Dock = DockStyle.Fill
        _lblPreview.TextAlign = ContentAlignment.MiddleCenter
        _lblPreview.ForeColor = Muted
        _lblPreview.BackColor = Surface2
        _lblPreview.Text = "Select a page to see it here"
        previewBox.Controls.Add(_preview)
        previewBox.Controls.Add(_lblPreview)

        ' Step 2: scan
        Dim scanRow As New Panel()
        scanRow.Dock = DockStyle.Bottom
        scanRow.Height = 58
        scanRow.Padding = New Padding(0, 12, 0, 0)
        PrimaryButton(_btnScan, "Scan")
        _btnScan.Dock = DockStyle.Fill
        _btnScan.Font = New Font("Segoe UI", 10.5F, FontStyle.Bold)
        scanRow.Controls.Add(_btnScan)

        card.Controls.Add(listFrame)
        card.Controls.Add(listButtons)
        card.Controls.Add(previewBox)
        card.Controls.Add(scanRow)
        card.Controls.Add(countRow)
        card.Controls.Add(_drop)
        card.Controls.Add(step1)
        outer.Controls.Add(card)

        AddHandler _btnAddFiles.Click, AddressOf AddFilesClicked
        AddHandler _btnAddFolder.Click, AddressOf AddFolderClicked
        AddHandler _btnPaste.Click, AddressOf PasteClicked
        AddHandler _btnClear.Click, AddressOf ClearClicked
        AddHandler _btnUp.Click, AddressOf UpClicked
        AddHandler _btnDown.Click, AddressOf DownClicked
        AddHandler _btnRemove.Click, AddressOf RemoveClicked
        AddHandler _btnScan.Click, AddressOf ScanClicked
        AddHandler _lstFiles.DrawItem, AddressOf DrawPageItem
        AddHandler _lstFiles.SelectedIndexChanged, AddressOf PageSelected
        AddHandler _lstFiles.KeyDown, AddressOf ListKeyDown
        For Each target As Control In New Control() {_lstFiles, _drop}
            AddHandler target.DragEnter, AddressOf FilesDragEnter
            AddHandler target.DragDrop, AddressOf FilesDragDrop
        Next
        Return outer
    End Function

    Private Function BuildResults() As Control
        Dim outer As New Panel()
        outer.Dock = DockStyle.Fill
        outer.Padding = New Padding(7, 14, 14, 14)

        ' Status banner
        _banner.Dock = DockStyle.Top
        _banner.Height = 44
        _banner.Padding = New Padding(14, 0, 14, 0)
        _lblStatus.Dock = DockStyle.Fill
        _lblStatus.TextAlign = ContentAlignment.MiddleLeft
        _lblStatus.AutoEllipsis = True
        _progress.Dock = DockStyle.Right
        _progress.Width = 160
        _progress.Style = ProgressBarStyle.Marquee
        _progress.MarqueeAnimationSpeed = 30
        _progress.Visible = False
        Dim progressHolder As New Panel()
        progressHolder.Dock = DockStyle.Right
        progressHolder.Width = 170
        progressHolder.Padding = New Padding(10, 15, 0, 15)
        progressHolder.BackColor = Color.Transparent
        progressHolder.Controls.Add(_progress)
        _banner.Controls.Add(_lblStatus)
        _banner.Controls.Add(progressHolder)

        ' Stat tiles
        Dim stats As New TableLayoutPanel()
        stats.Dock = DockStyle.Top
        stats.Height = 86
        stats.Padding = New Padding(0, 12, 0, 6)
        stats.ColumnCount = 4
        stats.RowCount = 1
        For i As Integer = 0 To 3
            stats.ColumnStyles.Add(New ColumnStyle(SizeType.Percent, 25.0F))
        Next
        stats.Controls.Add(StatTile("Items", _statItems), 0, 0)
        stats.Controls.Add(StatTile("Total quantity", _statQty), 1, 0)
        stats.Controls.Add(StatTile("Total amount", _statAmount), 2, 0)
        stats.Controls.Add(StatTile("Printed total", _statPrinted), 3, 0)

        ' Results card: header values (left) and items (below)
        _results.Dock = DockStyle.Fill
        _results.BackColor = Surface
        _results.Padding = New Padding(1)
        AddHandler _results.Paint, AddressOf PaintCardBorder

        StyleGrid(_gridHeader)
        _gridHeader.Dock = DockStyle.Left
        _gridHeader.Width = 400
        _gridHeader.AllowUserToAddRows = False
        _gridHeader.ColumnHeadersVisible = False
        _gridHeader.Columns.Add("Field", "Field")
        _gridHeader.Columns.Add("Value", "Value")
        _gridHeader.Columns(0).ReadOnly = True
        _gridHeader.Columns(0).Width = 165
        _gridHeader.Columns(0).DefaultCellStyle.ForeColor = Muted
        _gridHeader.Columns(0).DefaultCellStyle.SelectionForeColor = Muted
        _gridHeader.Columns(1).AutoSizeMode = DataGridViewAutoSizeColumnMode.Fill
        _gridHeader.Columns(1).DefaultCellStyle.Font = _fontBold
        Dim headerTitle As Label = SectionLabel("Invoice details  (click a value to correct it)")
        Dim headerBox As New Panel()
        headerBox.Dock = DockStyle.Top
        headerBox.Height = 300
        Dim headerSide As New Panel()
        headerSide.Dock = DockStyle.Fill
        headerSide.BackColor = Surface2
        Dim hint As New Label()
        hint.Dock = DockStyle.Fill
        hint.ForeColor = Text2
        hint.Padding = New Padding(16)
        hint.Text = "Before you click ""Use these values"":" & vbCrLf & vbCrLf & _
            "1.  Printed total shows a tick when the items add up to the invoice total." & vbCrLf & _
            "     A cross means a row is missing or misread." & vbCrLf & _
            "     Amber values: the OCR was not sure. Check them first." & vbCrLf & _
            "2.  Check the supplier, invoice number and date." & vbCrLf & _
            "3.  Correct any value by clicking on it. Totals update as you type." & vbCrLf & _
            "4.  Delete a wrong item row: select it and press Delete." & vbCrLf & vbCrLf & _
            "GRN Number, Stock Received Date and Date are not printed on invoices; fill them in your purchase entry."
        headerSide.Controls.Add(hint)
        Dim splitter As New Panel()
        splitter.Dock = DockStyle.Left
        splitter.Width = 1
        splitter.BackColor = Border
        headerBox.Controls.Add(headerSide)
        headerBox.Controls.Add(splitter)
        headerBox.Controls.Add(_gridHeader)

        StyleGrid(_gridItems)
        _gridItems.Dock = DockStyle.Fill
        _gridItems.AllowUserToAddRows = False
        _gridItems.AllowUserToDeleteRows = True
        Dim itemsTitle As Label = SectionLabel("Items")

        _empty.Dock = DockStyle.Fill
        _empty.TextAlign = ContentAlignment.MiddleCenter
        _empty.ForeColor = Muted
        _empty.BackColor = Surface
        _empty.Font = New Font("Segoe UI", 10.5F)
        _empty.Text = "Results appear here" & vbCrLf & vbCrLf & _
            "1.  Add the invoice photo(s), scan(s) or PDF on the left" & vbCrLf & _
            "2.  Click Scan" & vbCrLf & _
            "3.  Check the values and click ""Use these values"""

        _results.Controls.Add(_gridItems)
        _results.Controls.Add(itemsTitle)
        _results.Controls.Add(headerBox)
        _results.Controls.Add(headerTitle)
        _results.Controls.Add(_empty)
        _empty.BringToFront()

        outer.Controls.Add(_results)
        outer.Controls.Add(stats)
        outer.Controls.Add(_banner)

        AddHandler _gridItems.CellEndEdit, AddressOf ItemsEdited
        AddHandler _gridItems.CellFormatting, AddressOf ItemsCellFormatting
        AddHandler _gridHeader.CellEndEdit, AddressOf HeaderEdited
        AddHandler _gridItems.UserDeletedRow, AddressOf ItemsDeleted
        Return outer
    End Function

    Private Function BuildFooter() As Control
        Dim bar As New Panel()
        bar.Dock = DockStyle.Bottom
        bar.Height = 60
        bar.BackColor = Surface
        bar.Padding = New Padding(14, 12, 14, 12)
        AddHandler bar.Paint, AddressOf PaintTopBorder

        PrimaryButton(_btnOk, "Use these values")
        _btnOk.Dock = DockStyle.Right
        _btnOk.Width = 170
        _btnOk.Enabled = False
        Dim gap As New Panel()
        gap.Dock = DockStyle.Right
        gap.Width = 10
        SecondaryButton(_btnCancel, "Cancel", 110, Nothing)
        _btnCancel.Dock = DockStyle.Right
        _btnCancel.DialogResult = DialogResult.Cancel

        Dim note As New Label()
        note.Dock = DockStyle.Fill
        note.ForeColor = Muted
        note.TextAlign = ContentAlignment.MiddleLeft
        note.Text = "Nothing is saved until you click ""Use these values""."

        bar.Controls.Add(note)
        bar.Controls.Add(_btnCancel)
        bar.Controls.Add(gap)
        bar.Controls.Add(_btnOk)
        AddHandler _btnOk.Click, AddressOf OkClicked
        Return bar
    End Function

    Private Function StepLabel(ByVal number As String, ByVal text As String) As Label
        Dim label As New Label()
        label.Dock = DockStyle.Top
        label.Height = 30
        label.Font = _fontBold
        label.Padding = New Padding(28, 2, 0, 0)
        label.Text = text
        label.Tag = number
        label.TextAlign = ContentAlignment.TopLeft
        AddHandler label.Paint, AddressOf PaintStepNumber
        Return label
    End Function

    Private Function SectionLabel(ByVal text As String) As Label
        Dim label As New Label()
        label.Dock = DockStyle.Top
        label.Height = 32
        label.Padding = New Padding(12, 0, 0, 0)
        label.TextAlign = ContentAlignment.MiddleLeft
        label.Font = _fontBold
        label.ForeColor = Text2
        label.BackColor = Surface2
        label.Text = text
        Return label
    End Function

    Private Function StatTile(ByVal caption As String, ByVal value As Label) As Control
        Dim tile As New Panel()
        tile.Dock = DockStyle.Fill
        tile.Margin = New Padding(0, 0, 10, 0)
        tile.BackColor = Surface
        tile.Padding = New Padding(12, 8, 8, 6)
        AddHandler tile.Paint, AddressOf PaintCardBorder
        Dim title As New Label()
        title.Dock = DockStyle.Top
        title.Height = 18
        title.ForeColor = Muted
        title.Font = _fontSmall
        title.Text = caption
        value.Dock = DockStyle.Fill
        value.Font = _fontStat
        value.Text = "-"
        value.AutoEllipsis = True
        tile.Controls.Add(value)
        tile.Controls.Add(title)
        Return tile
    End Function

    Private Sub PrimaryButton(ByVal button As Button, ByVal text As String)
        button.Text = text
        button.FlatStyle = FlatStyle.Flat
        button.BackColor = Primary
        button.ForeColor = Color.White
        button.Font = _fontBold
        button.Cursor = Cursors.Hand
        button.FlatAppearance.BorderSize = 0
        button.FlatAppearance.MouseOverBackColor = PrimaryDark
        button.FlatAppearance.MouseDownBackColor = PrimaryDark
        AddHandler button.EnabledChanged, AddressOf PrimaryEnabledChanged
    End Sub

    Private Sub SecondaryButton(ByVal button As Button, ByVal text As String, ByVal width As Integer, ByVal parent As Control)
        button.Text = text
        button.Width = width
        button.Height = 30
        button.FlatStyle = FlatStyle.Flat
        button.BackColor = Surface
        button.ForeColor = TextColor
        button.Cursor = Cursors.Hand
        button.FlatAppearance.BorderColor = BorderStrong
        button.FlatAppearance.MouseOverBackColor = PrimarySoft
        button.FlatAppearance.MouseDownBackColor = PrimarySoft
        button.Margin = New Padding(0, 0, 6, 0)
        If parent IsNot Nothing Then parent.Controls.Add(button)
    End Sub

    Private Sub StyleGrid(ByVal grid As DataGridView)
        grid.BorderStyle = BorderStyle.None
        grid.BackgroundColor = Surface
        grid.GridColor = Border
        grid.CellBorderStyle = DataGridViewCellBorderStyle.SingleHorizontal
        grid.EnableHeadersVisualStyles = False
        grid.ColumnHeadersBorderStyle = DataGridViewHeaderBorderStyle.None
        grid.ColumnHeadersHeightSizeMode = DataGridViewColumnHeadersHeightSizeMode.DisableResizing
        grid.ColumnHeadersHeight = 34
        grid.ColumnHeadersDefaultCellStyle.BackColor = Surface2
        grid.ColumnHeadersDefaultCellStyle.ForeColor = Text2
        grid.ColumnHeadersDefaultCellStyle.SelectionBackColor = Surface2
        grid.ColumnHeadersDefaultCellStyle.Font = _fontBold
        grid.ColumnHeadersDefaultCellStyle.Padding = New Padding(4, 0, 4, 0)
        grid.RowHeadersVisible = False
        grid.AllowUserToResizeRows = False
        grid.RowTemplate.Height = 30
        grid.DefaultCellStyle.BackColor = Surface
        grid.DefaultCellStyle.ForeColor = TextColor
        grid.DefaultCellStyle.SelectionBackColor = PrimarySoft
        grid.DefaultCellStyle.SelectionForeColor = TextColor
        grid.DefaultCellStyle.Padding = New Padding(4, 0, 4, 0)
        grid.AlternatingRowsDefaultCellStyle.BackColor = Surface2
        grid.SelectionMode = DataGridViewSelectionMode.CellSelect
    End Sub

    ' ------------------------------------------------------------------ painting

    Private Sub PaintCardBorder(ByVal sender As Object, ByVal e As PaintEventArgs)
        Dim c As Control = CType(sender, Control)
        Using pen As New Pen(Border)
            e.Graphics.DrawRectangle(pen, 0, 0, c.Width - 1, c.Height - 1)
        End Using
    End Sub

    Private Sub PaintBottomBorder(ByVal sender As Object, ByVal e As PaintEventArgs)
        Dim c As Control = CType(sender, Control)
        Using pen As New Pen(Border)
            e.Graphics.DrawLine(pen, 0, c.Height - 1, c.Width, c.Height - 1)
        End Using
    End Sub

    Private Sub PaintTopBorder(ByVal sender As Object, ByVal e As PaintEventArgs)
        Dim c As Control = CType(sender, Control)
        Using pen As New Pen(Border)
            e.Graphics.DrawLine(pen, 0, 0, c.Width, 0)
        End Using
    End Sub

    Private Sub PaintDropZone(ByVal sender As Object, ByVal e As PaintEventArgs)
        Dim c As Control = CType(sender, Control)
        Using pen As New Pen(BorderStrong, 1.5F)
            pen.DashStyle = DashStyle.Dash
            e.Graphics.DrawRectangle(pen, 1, 1, c.Width - 3, c.Height - 3)
        End Using
    End Sub

    Private Sub PaintStepNumber(ByVal sender As Object, ByVal e As PaintEventArgs)
        Dim label As Label = CType(sender, Label)
        e.Graphics.SmoothingMode = SmoothingMode.AntiAlias
        Dim circle As New Rectangle(0, 0, 20, 20)
        Using brush As New SolidBrush(PrimarySoft)
            e.Graphics.FillEllipse(brush, circle)
        End Using
        TextRenderer.DrawText(e.Graphics, CStr(label.Tag), _fontBold, circle, Primary, _
            TextFormatFlags.HorizontalCenter Or TextFormatFlags.VerticalCenter)
    End Sub

    Private Sub DrawPageItem(ByVal sender As Object, ByVal e As DrawItemEventArgs)
        If e.Index < 0 Then Return
        Dim item As PageItem = CType(_lstFiles.Items(e.Index), PageItem)
        Dim selected As Boolean = (e.State And DrawItemState.Selected) = DrawItemState.Selected
        Dim g As Graphics = e.Graphics
        g.SmoothingMode = SmoothingMode.AntiAlias
        Using rowBrush As New SolidBrush(If(selected, PrimarySoft, Surface))
            g.FillRectangle(rowBrush, e.Bounds)
        End Using
        Using pen As New Pen(Border)
            g.DrawLine(pen, e.Bounds.Left, e.Bounds.Bottom - 1, e.Bounds.Right, e.Bounds.Bottom - 1)
        End Using

        Dim badge As New Rectangle(e.Bounds.Left + 8, e.Bounds.Top + 10, 22, 22)
        Using brush As New SolidBrush(If(selected, Primary, PrimarySoft))
            g.FillRectangle(brush, badge)
        End Using
        TextRenderer.DrawText(g, (e.Index + 1).ToString(), _fontBold, badge, If(selected, Color.White, Primary), _
            TextFormatFlags.HorizontalCenter Or TextFormatFlags.VerticalCenter)

        Dim textLeft As Integer = badge.Right + 10
        Dim nameRect As New Rectangle(textLeft, e.Bounds.Top + 4, e.Bounds.Width - textLeft - 6, 18)
        TextRenderer.DrawText(g, item.ToString(), _fontBold, nameRect, TextColor, TextFormatFlags.EndEllipsis Or TextFormatFlags.NoPrefix)
        Dim infoRect As New Rectangle(textLeft, e.Bounds.Top + 21, e.Bounds.Width - textLeft - 6, 16)
        TextRenderer.DrawText(g, item.Info, _fontSmall, infoRect, Muted, TextFormatFlags.EndEllipsis Or TextFormatFlags.NoPrefix)
    End Sub

    Private Sub PrimaryEnabledChanged(ByVal sender As Object, ByVal e As EventArgs)
        Dim button As Button = CType(sender, Button)
        If button.Enabled Then
            button.BackColor = Primary
        Else
            button.BackColor = Color.FromArgb(165, 160, 230)
        End If
    End Sub

    Private Sub SetStatus(ByVal kind As Tone, ByVal message As String)
        Dim fill As Color = PrimarySoft
        Dim fore As Color = Primary
        Select Case kind
            Case Tone.Good
                fill = SuccessSoft
                fore = Success
            Case Tone.Warn
                fill = WarningSoft
                fore = Warning
            Case Tone.Bad
                fill = DangerSoft
                fore = Danger
        End Select
        _banner.BackColor = fill
        _lblStatus.ForeColor = fore
        _lblStatus.Font = If(kind = Tone.Info, _fontBase, _fontBold)
        _lblStatus.Text = message
        _progress.Visible = (kind = Tone.Busy)
    End Sub

    ' ------------------------------------------------------------------ form events

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
            SetStatus(Tone.Busy, "Please wait, the scan is still running...")
        End If
        MyBase.OnFormClosing(e)
    End Sub

    Protected Overrides Sub OnFormClosed(ByVal e As FormClosedEventArgs)
        _timer.Stop()
        ShowPreview(Nothing)
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

    ' ------------------------------------------------------------------ page list

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
                Using pasted As Image = Clipboard.GetImage()
                    Dim tempPath As String = Path.Combine(Path.GetTempPath(), _
                        "vbocr_pasted_" & DateTime.Now.ToString("yyyyMMdd_HHmmss_fff", CultureInfo.InvariantCulture) & ".png")
                    pasted.Save(tempPath, ImageFormat.Png)
                    _tempFiles.Add(tempPath)
                    AddOne(tempPath, "Pasted image " & (_lstFiles.Items.Count + 1).ToString())
                End Using
                UpdateButtons()
                _lstFiles.SelectedIndex = _lstFiles.Items.Count - 1
                SetStatus(Tone.Info, "Pasted image added. Click Scan when all pages are in the list.")
            Else
                SetStatus(Tone.Warn, "The clipboard has no image. Copy an invoice image (or files in Explorer) first.")
            End If
        Catch ex As System.Runtime.InteropServices.ExternalException
            SetStatus(Tone.Bad, "Could not read the clipboard: " & ex.Message)
        End Try
    End Sub

    Private Sub ClearClicked(ByVal sender As Object, ByVal e As EventArgs)
        _lstFiles.Items.Clear()
        UpdateButtons()
        ShowPreview(Nothing)
    End Sub

    Private Sub RemoveClicked(ByVal sender As Object, ByVal e As EventArgs)
        For i As Integer = _lstFiles.SelectedIndices.Count - 1 To 0 Step -1
            _lstFiles.Items.RemoveAt(_lstFiles.SelectedIndices(i))
        Next
        UpdateButtons()
        If _lstFiles.Items.Count = 0 Then ShowPreview(Nothing)
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

    Private Sub PageSelected(ByVal sender As Object, ByVal e As EventArgs)
        If _lstFiles.SelectedIndex < 0 Then Return
        ShowPreview(CType(_lstFiles.Items(_lstFiles.SelectedIndex), PageItem).FilePath)
    End Sub

    ' Loads a small copy of the page, so the file is not kept open (locked).
    Private Sub ShowPreview(ByVal filePath As String)
        Dim old As Image = _preview.Image
        _preview.Image = Nothing
        If old IsNot Nothing Then old.Dispose()
        _preview.Visible = False
        _lblPreview.Visible = True
        If filePath Is Nothing Then
            _lblPreview.Text = "Select a page to see it here"
            Return
        End If
        Dim ext As String = Path.GetExtension(filePath).ToLowerInvariant()
        If ext = ".pdf" OrElse ext = ".webp" Then
            _lblPreview.Text = ext.TrimStart("."c).ToUpperInvariant() & " file - no preview" & vbCrLf & Path.GetFileName(filePath)
            Return
        End If
        Try
            Using stream As New FileStream(filePath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite)
                Using original As Image = Image.FromStream(stream)
                    Dim scale As Double = Math.Min(1.0, 600.0 / Math.Max(original.Width, original.Height))
                    Dim thumb As New Bitmap(Math.Max(1, CInt(original.Width * scale)), Math.Max(1, CInt(original.Height * scale)))
                    Using g As Graphics = Graphics.FromImage(thumb)
                        g.Clear(Color.White)
                        g.InterpolationMode = InterpolationMode.HighQualityBicubic
                        g.DrawImage(original, 0, 0, thumb.Width, thumb.Height)
                    End Using
                    _preview.Image = thumb
                End Using
            End Using
            _preview.Visible = True
            _lblPreview.Visible = False
        Catch ex As ArgumentException
            _lblPreview.Text = "Cannot show this file - it may be damaged" & vbCrLf & Path.GetFileName(filePath)
        Catch ex As OutOfMemoryException
            _lblPreview.Text = "Cannot show this file - it may be damaged" & vbCrLf & Path.GetFileName(filePath)
        Catch ex As IOException
            _lblPreview.Text = "Cannot open this file" & vbCrLf & ex.Message
        End Try
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

    Private Function AddOne(ByVal filePath As String, ByVal display As String) As Boolean
        Dim full As String = Path.GetFullPath(filePath)
        For Each item As Object In _lstFiles.Items
            If String.Equals(CType(item, PageItem).FilePath, full, StringComparison.OrdinalIgnoreCase) Then Return False
        Next
        If display.Length = 0 Then display = Path.GetFileName(full)
        Dim info As String = Path.GetExtension(full).TrimStart("."c).ToUpperInvariant()
        Try
            info &= "  ·  " & FormatSize(New FileInfo(full).Length)
        Catch ex As IOException
        End Try
        _lstFiles.Items.Add(New PageItem(full, display, info))
        Return True
    End Function

    ' ------------------------------------------------------------------ scanning

    Private Sub ScanClicked(ByVal sender As Object, ByVal e As EventArgs)
        StartScan()
    End Sub

    Private Sub StartScan()
        If _worker.IsBusy OrElse _lstFiles.Items.Count = 0 Then Return
        _btnOk.Enabled = False
        SetListEnabled(False)
        _scanStarted = DateTime.Now
        SetStatus(Tone.Busy, "Reading " & _lstFiles.Items.Count.ToString() & " page(s)... this takes about 10-60 seconds per page.")
        _btnScan.Text = "Reading..."
        _timer.Start()
        Cursor = Cursors.AppStarting
        _worker.RunWorkerAsync(Files)
    End Sub

    Private Sub TimerTick(ByVal sender As Object, ByVal e As EventArgs)
        _btnScan.Text = "Reading...  " & CInt(DateTime.Now.Subtract(_scanStarted).TotalSeconds).ToString() & " s"
    End Sub

    ' Runs on a background thread: no access to controls here.
    Private Sub WorkerDoWork(ByVal sender As Object, ByVal e As DoWorkEventArgs)
        Dim pages() As String = CType(e.Argument, String())
        Dim client As New VbOcrClient(ServerUrl)
        client.ApiKey = ApiKey
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
        _timer.Stop()
        Cursor = Cursors.Default
        SetListEnabled(True)
        Dim seconds As Integer = CInt(DateTime.Now.Subtract(_scanStarted).TotalSeconds)
        If e.Error IsNot Nothing Then
            SetStatus(Tone.Bad, "Error: " & e.Error.Message)
            MessageBox.Show(Me, e.Error.Message, "Scan invoice", MessageBoxButtons.OK, MessageBoxIcon.Error)
            Return
        End If

        Dim result As VbOcrResult = CType(e.Result, VbOcrResult)
        _invoice = result.Invoice

        _gridHeader.Rows.Clear()
        For Each title As String In VbOcrInvoice.HeaderTitles
            Dim index As Integer = _gridHeader.Rows.Add(title, _invoice.GetHeader(title))
            If result.IsUnsure(0, title) Then _gridHeader.Rows(index).Cells(1).Style.BackColor = WarningSoft
        Next
        _unsureItems.Clear()
        For Each cell As VbOcrCell In result.UnsureCells
            If cell.Row >= 1 AndAlso cell.Row <= _invoice.Items.Rows.Count Then
                Dim row As DataRow = _invoice.Items.Rows(cell.Row - 1)
                If Not _unsureItems.ContainsKey(row) Then _unsureItems.Add(row, New List(Of String))
                _unsureItems(row).Add(cell.Title)
            End If
        Next
        _printedTotal = -1D
        If result.PrintedTotal.Length > 0 Then _printedTotal = VbOcrInvoice.ToDecimal(result.PrintedTotal)
        _gridItems.DataSource = _invoice.Items
        FormatItemColumns()
        _empty.Visible = False
        UpdateTotals()

        Dim count As Integer = _invoice.Items.Rows.Count
        _btnOk.Enabled = count > 0
        If count = 0 Then
            SetStatus(Tone.Bad, "No items found. " & result.Warnings & "  Try a sharper, straighter photo of the whole page.")
        ElseIf result.Warnings.Length > 0 OrElse result.UnsureCells.Count > 0 Then
            Dim message As String = "Please check: "
            If result.UnsureCells.Count > 0 Then
                message &= result.UnsureCells.Count.ToString() & " value(s) the OCR was not sure about (amber). "
            End If
            SetStatus(Tone.Warn, message & result.Warnings)
        ElseIf result.Source = "pdf-text" Then
            SetStatus(Tone.Good, count.ToString() & " items read exactly from the PDF text. Check the values, then click ""Use these values"".")
        Else
            SetStatus(Tone.Good, count.ToString() & " items read in " & seconds.ToString() & " s. Compare the total amount with the invoice, then click ""Use these values"".")
        End If
    End Sub

    Private Sub FormatItemColumns()
        For Each column As DataGridViewColumn In _gridItems.Columns
            column.SortMode = DataGridViewColumnSortMode.NotSortable
            Select Case column.Name
                Case "Quantity", "Cost Price", "M.R.P", "Amount"
                    column.DefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleRight
                    column.HeaderCell.Style.Alignment = DataGridViewContentAlignment.MiddleRight
                    column.Width = 90
                Case "Sl.No"
                    column.Width = 52
                    column.ReadOnly = True
                    column.DefaultCellStyle.ForeColor = Muted
                Case "SKU No./Item ID.", "Design Name"
                    column.Width = 150
                Case Else
                    column.Width = 95
            End Select
        Next
    End Sub

    Private Sub ItemsEdited(ByVal sender As Object, ByVal e As DataGridViewCellEventArgs)
        ' A value the user corrected is no longer "not sure".
        Dim row As DataRow = BoundRow(e.RowIndex)
        If row IsNot Nothing AndAlso _unsureItems.ContainsKey(row) Then
            _unsureItems(row).Remove(_gridItems.Columns(e.ColumnIndex).Name)
            _gridItems.InvalidateRow(e.RowIndex)
        End If
        UpdateTotals()
    End Sub

    Private Sub HeaderEdited(ByVal sender As Object, ByVal e As DataGridViewCellEventArgs)
        _gridHeader.Rows(e.RowIndex).Cells(e.ColumnIndex).Style.BackColor = Color.Empty
    End Sub

    ' Amber background for item values the OCR was not sure about.
    Private Sub ItemsCellFormatting(ByVal sender As Object, ByVal e As DataGridViewCellFormattingEventArgs)
        If e.RowIndex < 0 OrElse e.ColumnIndex < 0 OrElse _unsureItems.Count = 0 Then Return
        Dim row As DataRow = BoundRow(e.RowIndex)
        If row Is Nothing OrElse Not _unsureItems.ContainsKey(row) Then Return
        If _unsureItems(row).Contains(_gridItems.Columns(e.ColumnIndex).Name) Then
            e.CellStyle.BackColor = WarningSoft
            e.CellStyle.SelectionBackColor = Color.FromArgb(253, 230, 138)
        End If
    End Sub

    Private Function BoundRow(ByVal rowIndex As Integer) As DataRow
        If rowIndex < 0 OrElse rowIndex >= _gridItems.Rows.Count Then Return Nothing
        Dim view As DataRowView = TryCast(_gridItems.Rows(rowIndex).DataBoundItem, DataRowView)
        If view Is Nothing Then Return Nothing
        Return view.Row
    End Function

    Private Sub ItemsDeleted(ByVal sender As Object, ByVal e As DataGridViewRowEventArgs)
        UpdateTotals()
    End Sub

    Private Sub UpdateTotals()
        If _invoice Is Nothing Then Return
        Dim qty As Decimal = 0D
        Dim amount As Decimal = 0D
        Dim count As Integer = 0
        For Each row As DataRow In _invoice.Items.Rows
            If row.RowState = DataRowState.Deleted Then Continue For
            count += 1
            qty += VbOcrInvoice.ToDecimal(row("Quantity"))
            amount += VbOcrInvoice.ToDecimal(row("Amount"))
        Next
        Dim india As New CultureInfo("en-IN")
        _statItems.Text = count.ToString()
        _statQty.Text = qty.ToString("#,##0.##", india)
        _statAmount.Text = ChrW(&H20B9) & " " & amount.ToString("#,##0.00", india)

        ' Printed total: tick when the items add up to it (also with 3/5/12/18/28 % GST added).
        If _printedTotal < 0D Then
            _statPrinted.Text = "not found"
            _statPrinted.ForeColor = Muted
        Else
            Dim matches As Boolean = False
            For Each factor As Decimal In New Decimal() {1D, 1.05D, 1.12D, 1.18D, 1.28D, 1.03D}
                If Math.Abs(amount * factor - _printedTotal) <= 1D Then matches = True
            Next
            _statPrinted.Text = ChrW(&H20B9) & " " & _printedTotal.ToString("#,##0.00", india) & "  " & If(matches, ChrW(&H2713), ChrW(&H2717))
            _statPrinted.ForeColor = If(matches, Success, Danger)
        End If
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

    ' ------------------------------------------------------------------ helpers

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
        Dim count As Integer = _lstFiles.Items.Count
        Dim hasFiles As Boolean = count > 0
        _btnScan.Enabled = hasFiles AndAlso Not _worker.IsBusy
        _btnClear.Enabled = hasFiles
        _btnRemove.Enabled = hasFiles
        _btnUp.Enabled = count > 1
        _btnDown.Enabled = count > 1
        If hasFiles Then
            _btnScan.Text = "Scan " & count.ToString() & " page" & If(count = 1, "", "s")
            Dim total As Long = 0
            For Each item As Object In _lstFiles.Items
                Try
                    total += New FileInfo(CType(item, PageItem).FilePath).Length
                Catch ex As IOException
                End Try
            Next
            _lblCount.Text = count.ToString() & " page" & If(count = 1, "", "s") & "  ·  " & FormatSize(total) & "  ·  Up / Down change the order"
        Else
            _btnScan.Text = "Scan"
            _lblCount.Text = "No pages yet"
        End If
        _lstFiles.Invalidate()
    End Sub

    Private Shared Function FormatSize(ByVal bytes As Long) As String
        If bytes >= 1048576 Then Return (bytes / 1048576.0).ToString("0.0", CultureInfo.InvariantCulture) & " MB"
        Return Math.Max(1L, bytes \ 1024).ToString(CultureInfo.InvariantCulture) & " KB"
    End Function

    Private Function IsLocalServer() As Boolean
        Dim url As String = ServerUrl.ToLowerInvariant()
        Return url.IndexOf("://127.0.0.1", StringComparison.Ordinal) >= 0 OrElse url.IndexOf("://localhost", StringComparison.Ordinal) >= 0
    End Function

    ' One entry in the page list: full path plus the name and details shown to the user.
    Private Class PageItem
        Public ReadOnly FilePath As String
        Public ReadOnly Info As String
        Private ReadOnly _display As String

        Public Sub New(ByVal filePath As String, ByVal display As String, ByVal info As String)
            Me.FilePath = filePath
            _display = display
            Me.Info = info
        End Sub

        Public Overrides Function ToString() As String
            Return _display
        End Function
    End Class
End Class

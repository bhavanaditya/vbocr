' Drives the real scan dialog: scan, check what is shown, open Recent scans, accept with OK.
' Usage: DialogTest <server url> <test-files folder> <api key> <screenshot folder>
Option Strict On
Option Explicit On

Imports System
Imports System.Collections.Generic
Imports System.Data
Imports System.Drawing
Imports System.Drawing.Imaging
Imports System.IO
Imports System.Reflection
Imports System.Threading
Imports System.Windows.Forms

Module DialogTest
    Private _failed As Integer
    Private _shots As String = "."
    Private Const Flags As BindingFlags = BindingFlags.NonPublic Or BindingFlags.Instance

    Private Sub Check(ByVal name As String, ByVal ok As Boolean, Optional ByVal detail As String = "")
        If ok Then
            Console.WriteLine("PASS " & name)
        Else
            _failed += 1
            Console.WriteLine("FAIL " & name & If(detail.Length > 0, "  (" & detail & ")", ""))
        End If
    End Sub

    Private Function Field(Of T)(ByVal target As Object, ByVal name As String) As T
        Return CType(target.GetType().GetField(name, Flags).GetValue(target), T)
    End Function

    Private Sub Pump(ByVal milliseconds As Integer)
        Dim until As DateTime = DateTime.Now.AddMilliseconds(milliseconds)
        While DateTime.Now < until
            Application.DoEvents()
            Thread.Sleep(20)
        End While
    End Sub

    Private Function WaitFor(ByVal condition As Func(Of Boolean), ByVal seconds As Integer) As Boolean
        Dim until As DateTime = DateTime.Now.AddSeconds(seconds)
        While DateTime.Now < until
            Application.DoEvents()
            If condition() Then Return True
            Thread.Sleep(50)
        End While
        Return condition()
    End Function

    Private Sub Shot(ByVal form As Form, ByVal name As String)
        Using bmp As New Bitmap(form.Width, form.Height)
            form.DrawToBitmap(bmp, New Rectangle(0, 0, form.Width, form.Height))
            bmp.Save(Path.Combine(_shots, name & ".png"), ImageFormat.Png)
        End Using
        Try   ' what is really on the screen, including the title bar
            Dim screen As Rectangle = System.Windows.Forms.Screen.PrimaryScreen.Bounds
            Using bmp As New Bitmap(screen.Width, screen.Height)
                Using g As Graphics = Graphics.FromImage(bmp)
                    g.CopyFromScreen(screen.Location, Point.Empty, screen.Size)
                End Using
                bmp.Save(Path.Combine(_shots, name & "-screen.png"), ImageFormat.Png)
            End Using
        Catch ex As Exception
            Console.WriteLine("  (no screen capture: " & ex.Message & ")")
        End Try
    End Sub

    <STAThread>
    Function Main(ByVal args() As String) As Integer
        If args.Length < 4 Then
            Console.WriteLine("Usage: DialogTest <server url> <test-files folder> <api key> <screenshot folder>")
            Return 2
        End If
        Dim url As String = args(0), dir As String = args(1), key As String = args(2)
        _shots = args(3)
        Directory.CreateDirectory(_shots)
        ' Never hang the build: give up after 5 minutes.
        Dim watchdog As New Thread(Sub()
                                       Thread.Sleep(300000)
                                       Console.WriteLine("FAIL timeout: the dialog test took more than 5 minutes")
                                       Environment.Exit(1)
                                   End Sub)
        watchdog.IsBackground = True
        watchdog.Start()

        Application.EnableVisualStyles()
        Dim dlg As New VbOcrScanForm()
        dlg.ServerUrl = url
        dlg.ApiKey = key
        dlg.InstallFolder = Path.GetFullPath(".")
        dlg.FilesToScan = New String() {Path.Combine(dir, "a_bill.jpg")}
        dlg.Show()

        Dim ok As Button = Field(Of Button)(dlg, "_btnOk")
        Dim status As Label = Field(Of Label)(dlg, "_lblStatus")
        Dim scanned As Boolean = WaitFor(Function() ok.Enabled OrElse status.Text.StartsWith("Error"), 240)
        Pump(500)
        Shot(dlg, "1-scan-result")
        Console.WriteLine("  status: " & status.Text)
        Check("scan finished and OK enabled", scanned AndAlso ok.Enabled, status.Text)
        If Not ok.Enabled Then Return 1

        Dim items As Label = Field(Of Label)(dlg, "_statItems")
        Dim printed As Label = Field(Of Label)(dlg, "_statPrinted")
        Dim amount As Label = Field(Of Label)(dlg, "_statAmount")
        Console.WriteLine("  tiles: items=" & items.Text & " amount=" & amount.Text & " printed=" & printed.Text)
        Check("item count tile", items.Text.Trim() = dlg.Invoice.Items.Rows.Count.ToString() AndAlso dlg.Invoice.Items.Rows.Count >= 3, items.Text)
        Check("supplier GSTIN shown", dlg.SupplierGstin = "29AAGCS1234K1Z7" AndAlso status.Text.Contains("29AAGCS1234K1Z7"), dlg.SupplierGstin)
        Check("scan id", dlg.ScanId.Length > 15)
        Dim earlier As Button = Field(Of Button)(dlg, "_btnEarlier")
        Check("'Earlier scans' button shown (invoice scanned before by ClientTest)", earlier.Visible)
        Dim recent As Button = Field(Of Button)(dlg, "_btnRecent")
        Check("'Recent scans' button visible", recent.Visible AndAlso recent.Width > 0 AndAlso recent.Parent IsNot Nothing)
        CheckInside(dlg, recent, "'Recent scans' button")
        CheckInside(dlg, earlier, "'Earlier scans' button")
        CheckInside(dlg, ok, "OK button")
        Dim area As Rectangle = System.Windows.Forms.Screen.FromControl(dlg).WorkingArea
        Check("dialog fits on the screen, above the taskbar", area.Contains(dlg.Bounds), dlg.Bounds.ToString() & " in " & area.ToString())
        Check("OK button on the screen", area.Contains(ok.RectangleToScreen(ok.ClientRectangle)))
        Dim needed As Size = TextRenderer.MeasureText(status.Text, status.Font, New Size(status.Width, 0), TextFormatFlags.WordBreak Or TextFormatFlags.TextBoxControl)
        Check("status message fully visible", needed.Height <= status.Height OrElse status.Height >= 4 * status.Font.Height, needed.Height.ToString() & " > " & status.Height.ToString())

        ' Recent scans window (normally modal; shown non-modal here so the test can look at it).
        Dim listType As Type = GetType(VbOcrScanForm).GetNestedType("RecentScansForm", BindingFlags.NonPublic)
        Dim client As New VbOcrClient(url)
        client.ApiKey = key
        Dim listForm As Form = CType(Activator.CreateInstance(listType, Flags Or BindingFlags.Public, Nothing,
            New Object() {client, "", dlg.Font}, Nothing), Form)
        listForm.StartPosition = FormStartPosition.Manual
        listForm.Location = New Point(40, 40)
        listForm.Show(dlg)
        Pump(1500)
        Dim grid As DataGridView = Field(Of DataGridView)(listForm, "_grid")
        Shot(listForm, "2-recent-scans")
        Check("Recent scans lists scans", grid.Rows.Count > 0, grid.Rows.Count.ToString())
        If grid.Rows.Count > 0 Then
            Check("Recent scans: first row is the scan just made", Convert.ToString(grid.Rows(0).Tag) = dlg.ScanId)
        End If
        listForm.Close()

        ' Open a saved scan into the dialog.
        Dim showResult As MethodInfo = GetType(VbOcrScanForm).GetMethod("ShowResult", Flags)
        Dim scanId As String = dlg.ScanId
        showResult.Invoke(dlg, New Object() {client.OpenScan(scanId), 0, True})
        Pump(300)
        Check("opened scan shown", status.Text.Contains("opened from the history") AndAlso ok.Enabled, status.Text)

        ' The user corrects a value and clicks OK: the correction reaches the server.
        Dim newSize As String = If(Convert.ToString(dlg.Invoice.Items.Rows(0)("Size")) = "M", "L", "M")
        dlg.Invoice.Items.Rows(0)("Size") = newSize
        Pump(200)
        Shot(dlg, "3-corrected")
        ok.PerformClick()
        Check("OK closes with DialogResult.OK", dlg.DialogResult = DialogResult.OK)
        Dim saved As Boolean = WaitFor(Function() Convert.ToString(client.OpenScan(scanId).Invoice.Items.Rows(0)("Size")) = newSize, 20)
        Check("correction saved on OK", saved)
        dlg.Close()
        dlg.Dispose()

        Console.WriteLine(If(_failed = 0, "All dialog checks passed.", _failed.ToString() & " FAILED"))
        Return If(_failed = 0, 0, 1)
    End Function

    ' A control must lie fully inside the dialog's client area (not cut off).
    Private Sub CheckInside(ByVal dlg As Form, ByVal control As Control, ByVal name As String)
        If Not control.Visible Then Return
        Dim r As Rectangle = dlg.RectangleToClient(control.RectangleToScreen(control.ClientRectangle))
        Dim inside As Boolean = dlg.ClientRectangle.Contains(r) AndAlso r.Width > 20 AndAlso r.Height > 10
        Dim size As Size = TextRenderer.MeasureText(control.Text, control.Font)
        Check(name & " fully visible and text fits", inside AndAlso size.Width <= control.Width + 2, r.ToString() & " text " & size.Width.ToString())
    End Sub
End Module

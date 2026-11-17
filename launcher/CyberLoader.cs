// CyberLoader.exe: owns the app window (Microsoft WebView2) and starts the engine of the active installed version.
// Layout it expects next to itself:
//   runtime\python.exe           private Python
//   current.txt                  the active version, e.g. 0.3.0
//   versions\<version>\engine\run.py
//   Microsoft.Web.WebView2.Core.dll, Microsoft.Web.WebView2.WinForms.dll, WebView2Loader.dll
// Build: tools/setup-cyberloader.py (the C# 5 compiler that ships with Windows; keep this file C# 5 compatible).
// Window contract with the UI: docs/HOST-API.md. Environment overrides for development:
//   CYBERLOADER_APP=<path to engine\run.py>   CYBERLOADER_UI=<ui folder>   CYBERLOADER_DEBUG=1 (dev tools + host.log)
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

[assembly: AssemblyTitle("CyberLoader")]
[assembly: AssemblyProduct("CyberLoader")]
[assembly: AssemblyDescription("CyberLoader: Cyberpunk 2077 mod manager")]
[assembly: AssemblyVersion("1.0.0.0")]

static class Program
{
    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    static extern int SetCurrentProcessExplicitAppUserModelID([MarshalAs(UnmanagedType.LPWStr)] string appId);

    [STAThread]
    static int Main(string[] args)
    {
        // Explorer remembers a taskbar button's icon per application identity (AppUserModelID) and keeps showing the
        // first one it saw, even after the exe's icon changes. An explicit identity of its own ("v2" = after the icon
        // change) gives it a fresh button that takes the window's current icon. Must run before any window exists.
        try { SetCurrentProcessExplicitAppUserModelID("CyberLoader.App.v2" + MainForm.Instance); } catch (Exception) { }
        bool created;
        // CYBERLOADER_INSTANCE (development only) lets a test copy run next to the real app: it gets its own
        // single-instance lock, WebView2 profile and remembered window position.
        string inst = MainForm.Instance;
        Mutex mutex = new Mutex(true, "CyberLoader.SingleInstance" + inst, out created);
        if (!created)
        {
            try { EventWaitHandle.OpenExisting("CyberLoader.Activate" + inst).Set(); } catch (Exception) { }
            return 0;
        }
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        try
        {
            Application.Run(new MainForm());
        }
        catch (Exception ex)
        {
            MessageBox.Show("CyberLoader stopped unexpectedly.\n\n" + ex.Message, "CyberLoader", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
        finally
        {
            GC.KeepAlive(mutex);
        }
        return 0;
    }
}

class MainForm : Form
{
    const int WM_NCCALCSIZE = 0x0083, WM_NCLBUTTONDOWN = 0x00A1, WM_SYSCOMMAND = 0x0112;
    const int SC_MAXIMIZE = 0xF030, SC_RESTORE = 0xF120;
    const int SWP_NOSIZE = 0x1, SWP_NOMOVE = 0x2, SWP_NOZORDER = 0x4, SWP_NOACTIVATE = 0x10, SWP_FRAMECHANGED = 0x20;
    const int SM_CXSIZEFRAME = 32, SM_CXPADDEDBORDER = 92;
    const int PreferredPort = 47213;

    [StructLayout(LayoutKind.Sequential)]
    struct RECT { public int Left, Top, Right, Bottom; }

    [DllImport("user32.dll")] static extern bool ReleaseCapture();
    [DllImport("user32.dll")] static extern IntPtr SendMessage(IntPtr hWnd, int msg, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr hWnd, IntPtr after, int x, int y, int cx, int cy, int flags);
    [DllImport("user32.dll")] static extern int GetSystemMetrics(int index);
    [DllImport("user32.dll")] static extern bool IsZoomed(IntPtr hWnd);
    [DllImport("user32.dll")] static extern int SetWindowRgn(IntPtr hWnd, IntPtr hRgn, bool redraw);
    [DllImport("gdi32.dll")] static extern IntPtr CreateRoundRectRgn(int l, int t, int r, int b, int w, int h);

    const int WindowRadius = 18; // corner radius (px) of the frameless window when it is not maximized; host.js mirrors it into CSS

    // Frameless + not maximized: clip the window to a rounded rectangle (Windows' own rounding is fixed at about 8 px).
    // The page draws a 1 px inner border with the same radius, which smooths the clipped edge.
    void UpdateRegion()
    {
        if (!IsHandleCreated) return;
        if (frameless && WindowState == FormWindowState.Normal)
            SetWindowRgn(Handle, CreateRoundRectRgn(0, 0, Width + 1, Height + 1, WindowRadius * 2, WindowRadius * 2), true);
        else
            SetWindowRgn(Handle, IntPtr.Zero, true);
    }

    public static string Instance { get { return Environment.GetEnvironmentVariable("CYBERLOADER_INSTANCE") ?? ""; } }
    string root = AppDomain.CurrentDomain.BaseDirectory;
    string appData = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "CyberLoader");
    bool debug = Environment.GetEnvironmentVariable("CYBERLOADER_DEBUG") == "1";
    Process engine;
    StringBuilder engineErr = new StringBuilder();
    int port;
    WebView2 web;
    bool frameless;
    EventWaitHandle activate;
    JavaScriptSerializer json = new JavaScriptSerializer();
    Color bg = Color.FromArgb(12, 14, 20);

    public MainForm()
    {
        Directory.CreateDirectory(appData);
        Text = "CyberLoader";
        // The window (and so the taskbar button) uses the icon embedded in this exe as a resource. Reading it from the
        // file's shell icon (ExtractAssociatedIcon) can return a stale picture from Windows' icon cache after an update.
        try
        {
            using (Stream s = Assembly.GetExecutingAssembly().GetManifestResourceStream("cyberloader.ico")) Icon = new Icon(s);
        }
        catch (Exception)
        {
            try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch (Exception) { }
        }
        MinimumSize = new Size(700, 480);
        Size = new Size(1100, 740);
        StartPosition = FormStartPosition.CenterScreen;
        BackColor = bg;
        DoubleBuffered = true;
        RestoreBounds_();
        activate = new EventWaitHandle(false, EventResetMode.AutoReset, "CyberLoader.Activate" + Instance);
        Thread t = new Thread(delegate ()
        {
            while (activate.WaitOne())
            {
                try
                {
                    BeginInvoke((MethodInvoker)delegate
                    {
                        if (WindowState == FormWindowState.Minimized) WindowState = FormWindowState.Normal;
                        Activate();
                    });
                }
                catch (Exception) { return; }
            }
        });
        t.IsBackground = true;
        t.Start();
        Load += delegate { StartAsync(); };
        FormClosing += OnClosing;
        FormClosed += delegate { SaveBounds_(); StopEngine(); };
        Activated += delegate { SendState(); };
        Deactivate += delegate { SendState(); };
        SizeChanged += delegate { UpdateRegion(); SendState(); };
    }

    void Log(string m)
    {
        if (!debug) return;
        try { File.AppendAllText(Path.Combine(appData, "host.log"), DateTime.Now.ToString("HH:mm:ss.fff") + " " + m + "\r\n"); } catch (Exception) { }
    }

    // ------------------------------------------------------------ window frame
    protected override void WndProc(ref Message m)
    {
        if (m.Msg == WM_NCCALCSIZE && frameless && m.WParam != IntPtr.Zero)
        {
            // client area = whole window; when maximized, pull the edges in by the invisible sizing border
            if (IsZoomed(Handle)) // not Form.WindowState: WinForms updates that only after this message
            {
                RECT r = (RECT)Marshal.PtrToStructure(m.LParam, typeof(RECT));
                int f = GetSystemMetrics(SM_CXSIZEFRAME) + GetSystemMetrics(SM_CXPADDEDBORDER);
                r.Left += f; r.Top += f; r.Right -= f; r.Bottom -= f;
                Marshal.StructureToPtr(r, m.LParam, false);
            }
            m.Result = IntPtr.Zero;
            return;
        }
        base.WndProc(ref m);
    }

    [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int value, int size);

    protected override void OnHandleCreated(EventArgs e)
    {
        base.OnHandleCreated(e);
        // Windows 11: ask for rounded corners explicitly (frameless windows are not rounded by default). Maximized windows are square automatically.
        int round = 2; // DWMWCP_ROUND
        try { DwmSetWindowAttribute(Handle, 33, ref round, 4); } catch (Exception) { }
        ApplyCaptionColors();
    }

    // While the page has not gone frameless, the normal Windows title bar is shown: make it match the app (Windows 11).
    void ApplyCaptionColors()
    {
        try
        {
            int dark = 1; // DWMWA_USE_IMMERSIVE_DARK_MODE
            DwmSetWindowAttribute(Handle, 20, ref dark, 4);
            int caption = bg.R | (bg.G << 8) | (bg.B << 16); // DWMWA_CAPTION_COLOR, COLORREF 0x00BBGGRR
            DwmSetWindowAttribute(Handle, 35, ref caption, 4);
            int text = 0xE8 | (0xEA << 8) | (0xF0 << 16); // DWMWA_TEXT_COLOR
            DwmSetWindowAttribute(Handle, 36, ref text, 4);
        }
        catch (Exception) { }
    }

    void SetFrameless(bool on)
    {
        if (frameless == on) return;
        frameless = on;
        SetWindowPos(Handle, IntPtr.Zero, 0, 0, 0, 0, SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE);
        int pref = on ? 1 : 2; // DWMWCP_DONOTROUND while our own rounded region is in use, DWMWCP_ROUND with the normal frame
        try { DwmSetWindowAttribute(Handle, 33, ref pref, 4); } catch (Exception) { }
        UpdateRegion();
        SendState();
        Log("frameless " + on);
    }

    // ------------------------------------------------------------ engine
    void StartAsync()
    {
        try
        {
            StartEngine();
        }
        catch (Exception ex)
        {
            Fail(ex.Message);
            return;
        }
        InitWebAsync();
    }

    static int FreePort()
    {
        TcpListener l = new TcpListener(IPAddress.Loopback, 0);
        l.Start();
        int p = ((IPEndPoint)l.LocalEndpoint).Port;
        l.Stop();
        return p;
    }

    static bool PortFree(int p)
    {
        try { TcpListener l = new TcpListener(IPAddress.Loopback, p); l.Start(); l.Stop(); return true; }
        catch (Exception) { return false; }
    }

    void StartEngine()
    {
        string python = Path.Combine(root, "runtime", "python.exe");
        string script = Environment.GetEnvironmentVariable("CYBERLOADER_APP");
        if (string.IsNullOrEmpty(script))
        {
            string current = Path.Combine(root, "current.txt");
            if (!File.Exists(current)) throw new FileNotFoundException("No version is installed (current.txt is missing).");
            string version = File.ReadAllText(current).Trim();
            if (version.Length == 0 || version.IndexOfAny(new char[] { '\\', '/', ':' }) >= 0) throw new InvalidDataException("current.txt does not hold a valid version.");
            script = Path.Combine(root, "versions", version, "engine", "run.py");
        }
        if (!File.Exists(python)) throw new FileNotFoundException("The runtime is missing: " + python);
        if (!File.Exists(script)) throw new FileNotFoundException("The app files are missing: " + script);
        port = PortFree(PreferredPort) ? PreferredPort : FreePort();
        string ui = Environment.GetEnvironmentVariable("CYBERLOADER_UI");
        string args = "-I \"" + script + "\"" + (string.IsNullOrEmpty(ui) ? "" : " --ui \"" + ui + "\"")
            + " serve --no-open --host-managed --parent-pid " + Process.GetCurrentProcess().Id + " --port " + port;
        ProcessStartInfo psi = new ProcessStartInfo(python, args);
        psi.WorkingDirectory = Path.GetDirectoryName(script);
        psi.UseShellExecute = false;
        psi.CreateNoWindow = true;
        psi.RedirectStandardOutput = true;
        psi.RedirectStandardError = true;
        engine = Process.Start(psi);
        engine.OutputDataReceived += delegate { };
        engine.ErrorDataReceived += delegate (object s, DataReceivedEventArgs e) { if (e.Data != null && engineErr.Length < 4000) engineErr.AppendLine(e.Data); };
        engine.BeginOutputReadLine();
        engine.BeginErrorReadLine();
        Log("engine started on port " + port);
    }

    void StopEngine()
    {
        try { if (engine != null && !engine.HasExited) engine.Kill(); } catch (Exception) { }
    }

    string HttpGet(string path)
    {
        HttpWebRequest rq = (HttpWebRequest)WebRequest.Create("http://127.0.0.1:" + port + path);
        rq.Timeout = 2000;
        using (WebResponse rs = rq.GetResponse())
        using (StreamReader sr = new StreamReader(rs.GetResponseStream()))
            return sr.ReadToEnd();
    }

    bool EngineAnswers()
    {
        try { HttpGet("/api/settings"); return true; } catch (Exception) { return false; }
    }

    void Fail(string message)
    {
        MessageBox.Show("CyberLoader could not start.\n\n" + message + (engineErr.Length > 0 ? "\n\n" + engineErr.ToString() : ""),
            "CyberLoader", MessageBoxButtons.OK, MessageBoxIcon.Error);
        Close();
    }

    // ------------------------------------------------------------ web view
    async void InitWebAsync()
    {
        try
        {
            web = new WebView2();
            web.Dock = DockStyle.Fill;
            web.DefaultBackgroundColor = bg;
            Controls.Add(web);
            CoreWebView2Environment env = await CoreWebView2Environment.CreateAsync(null, Path.Combine(appData, "webview2" + Instance), null);
            await web.EnsureCoreWebView2Async(env);
            CoreWebView2Settings s = web.CoreWebView2.Settings;
            s.AreDevToolsEnabled = debug;
            s.AreDefaultContextMenusEnabled = debug;
            s.AreBrowserAcceleratorKeysEnabled = debug;
            s.IsStatusBarEnabled = false;
            s.IsZoomControlEnabled = false;
            s.IsPasswordAutosaveEnabled = false;
            s.IsGeneralAutofillEnabled = false;
            await web.CoreWebView2.AddScriptToExecuteOnDocumentCreatedAsync(ReadResource("host.js"));
            web.CoreWebView2.WebMessageReceived += OnMessage;
            web.CoreWebView2.NavigationCompleted += delegate { SendState(); };
            web.CoreWebView2.NavigationStarting += delegate (object o, CoreWebView2NavigationStartingEventArgs e)
            {
                if (!e.Uri.StartsWith("http://127.0.0.1:" + port + "/")) { e.Cancel = true; OpenExternal(e.Uri); }
            };
            web.CoreWebView2.NewWindowRequested += delegate (object o, CoreWebView2NewWindowRequestedEventArgs e) { e.Handled = true; OpenExternal(e.Uri); };
            DateTime until = DateTime.Now.AddSeconds(25);
            bool up = false;
            while (DateTime.Now < until)
            {
                if (engine != null && engine.HasExited) break;
                bool ok = await Task.Run(() => EngineAnswers());
                if (ok) { up = true; break; }
                await Task.Delay(250);
            }
            if (!up) { Fail("The engine did not start."); return; }
            web.CoreWebView2.Navigate("http://127.0.0.1:" + port + "/");
        }
        catch (Exception ex)
        {
            Fail(ex.Message + "\n\nCyberLoader needs the Microsoft WebView2 Runtime (it comes with Windows 11 and Edge).");
        }
    }

    static string ReadResource(string name)
    {
        using (Stream s = Assembly.GetExecutingAssembly().GetManifestResourceStream(name))
        using (StreamReader r = new StreamReader(s, Encoding.UTF8))
            return r.ReadToEnd();
    }

    static void OpenExternal(string uri)
    {
        if (uri.StartsWith("http://") || uri.StartsWith("https://"))
        {
            try { Process.Start(uri); } catch (Exception) { }
        }
    }

    void SendState()
    {
        if (web == null || web.CoreWebView2 == null) return;
        try
        {
            int radius = (frameless && WindowState == FormWindowState.Normal) ? WindowRadius : 0;
            web.CoreWebView2.PostWebMessageAsJson("{\"type\":\"window\",\"maximized\":" + (WindowState == FormWindowState.Maximized ? "true" : "false")
                + ",\"focused\":" + (Form.ActiveForm == this ? "true" : "false") + ",\"radius\":" + radius + "}");
        }
        catch (Exception) { }
    }

    void OnMessage(object sender, CoreWebView2WebMessageReceivedEventArgs e)
    {
        Dictionary<string, object> msg;
        try { msg = json.Deserialize<Dictionary<string, object>>(e.WebMessageAsJson); } catch (Exception) { return; }
        object cmdObj;
        if (msg == null || !msg.TryGetValue("cmd", out cmdObj)) return;
        string cmd = Convert.ToString(cmdObj);
        Log("cmd " + cmd);
        switch (cmd)
        {
            case "frameless":
                object on;
                if (msg.TryGetValue("on", out on)) SetFrameless(Convert.ToBoolean(on));
                break;
            case "minimize":
                WindowState = FormWindowState.Minimized;
                break;
            case "toggleMaximize":
                SendMessage(Handle, WM_SYSCOMMAND, (IntPtr)(WindowState == FormWindowState.Maximized ? SC_RESTORE : SC_MAXIMIZE), IntPtr.Zero);
                break;
            case "close":
                Close();
                break;
            case "startDrag":
                ReleaseCapture();
                SendMessage(Handle, WM_NCLBUTTONDOWN, (IntPtr)2, IntPtr.Zero); // HTCAPTION
                break;
            case "startResize":
                object edge;
                if (msg.TryGetValue("edge", out edge) && WindowState == FormWindowState.Normal)
                {
                    int ht = HitTestCode(Convert.ToString(edge));
                    if (ht != 0) { ReleaseCapture(); SendMessage(Handle, WM_NCLBUTTONDOWN, (IntPtr)ht, IntPtr.Zero); }
                }
                break;
            case "pickFolder":
                object pid, pstart;
                msg.TryGetValue("id", out pid);
                msg.TryGetValue("start", out pstart);
                PickFolder(Convert.ToString(pid), Convert.ToString(pstart));
                break;
            case "log": // development aid: only written when CYBERLOADER_DEBUG=1
                object txt;
                if (msg.TryGetValue("text", out txt)) Log("page: " + Convert.ToString(txt));
                break;
            case "background":
                object col;
                if (msg.TryGetValue("color", out col) && Regex.IsMatch(Convert.ToString(col), "^#[0-9a-fA-F]{6}$"))
                {
                    string c = Convert.ToString(col);
                    bg = Color.FromArgb(Convert.ToInt32(c.Substring(1, 2), 16), Convert.ToInt32(c.Substring(3, 2), 16), Convert.ToInt32(c.Substring(5, 2), 16));
                    BackColor = bg;
                    web.DefaultBackgroundColor = bg;
                    ApplyCaptionColors();
                }
                break;
        }
    }

    bool picking;

    // Folder dialog for cyberHost.pickFolder(): answers the page with {type:"pickFolder", id, path} (path null = cancelled or failed).
    // It only returns the path the user chose; nothing is read from or written to that folder.
    void PickFolder(string id, string start)
    {
        string result = null;
        if (!picking)
        {
            picking = true;
            try
            {
                using (FolderBrowserDialog d = new FolderBrowserDialog())
                {
                    d.Description = "Choose the Cyberpunk 2077 folder (the one that contains the bin folder)";
                    d.ShowNewFolderButton = false;
                    try { if (!string.IsNullOrEmpty(start) && Directory.Exists(start)) d.SelectedPath = start; } catch (Exception) { }
                    if (d.ShowDialog(this) == DialogResult.OK) result = d.SelectedPath;
                }
            }
            catch (Exception ex) { Log("pickFolder failed: " + ex.Message); }
            finally { picking = false; }
        }
        if (web == null || web.CoreWebView2 == null) return;
        try
        {
            Dictionary<string, object> reply = new Dictionary<string, object>();
            reply["type"] = "pickFolder";
            reply["id"] = id;
            reply["path"] = result;
            web.CoreWebView2.PostWebMessageAsJson(json.Serialize(reply));
        }
        catch (Exception) { }
    }

    static int HitTestCode(string edge)
    {
        switch (edge)
        {
            case "l": return 10; case "r": return 11; case "t": return 12; case "tl": return 13;
            case "tr": return 14; case "b": return 15; case "bl": return 16; case "br": return 17;
        }
        return 0;
    }

    // ------------------------------------------------------------ closing and remembering the window
    void OnClosing(object sender, FormClosingEventArgs e)
    {
        if (e.CloseReason != CloseReason.UserClosing || engine == null || engine.HasExited || port == 0) return;
        try
        {
            if (HttpGet("/api/progress").Contains("\"running\""))
            {
                if (MessageBox.Show("Mods are still being applied. Closing now could leave the game folder half changed.\n\nClose anyway?",
                    "CyberLoader", MessageBoxButtons.YesNo, MessageBoxIcon.Warning, MessageBoxDefaultButton.Button2) != DialogResult.Yes)
                    e.Cancel = true;
            }
        }
        catch (Exception) { }
    }

    string BoundsFile { get { return Path.Combine(appData, "window" + Instance + ".txt"); } }

    void SaveBounds_()
    {
        try
        {
            Rectangle b = WindowState == FormWindowState.Normal ? Bounds : RestoreBounds;
            File.WriteAllText(BoundsFile, b.X + " " + b.Y + " " + b.Width + " " + b.Height + " " + (WindowState == FormWindowState.Maximized ? "1" : "0"));
        }
        catch (Exception) { }
    }

    void RestoreBounds_()
    {
        try
        {
            if (!File.Exists(BoundsFile)) return;
            string[] p = File.ReadAllText(BoundsFile).Trim().Split(' ');
            Rectangle b = new Rectangle(int.Parse(p[0]), int.Parse(p[1]), int.Parse(p[2]), int.Parse(p[3]));
            if (b.Width < 700 || b.Height < 480) return;
            foreach (Screen sc in Screen.AllScreens)
            {
                Rectangle inter = Rectangle.Intersect(sc.WorkingArea, b);
                if (inter.Width > 200 && inter.Height > 100)
                {
                    StartPosition = FormStartPosition.Manual;
                    Bounds = b;
                    if (p.Length > 4 && p[4] == "1") WindowState = FormWindowState.Maximized;
                    return;
                }
            }
        }
        catch (Exception) { }
    }
}

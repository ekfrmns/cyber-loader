// CyberLoader Setup: the installer wizard (also the uninstaller when run as Uninstall.exe or with /UNINSTALL).
// Built by tools/package.py with the C# 5 compiler that ships with Windows: keep this file C# 5 compatible.
// The app files travel inside this exe as resources: payload.zip (required) and sevenzip.zip (optional component).
//
// Silent install:   Setup.exe /S /D=<install dir> /GAME=<Cyberpunk 2077 folder> /DATA=<data folder> [/7ZIP=0|1] [/NODESKTOP] [/NOSTART] [/LAUNCH]
// Silent uninstall: Uninstall.exe /S [/DELETEDATA]
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32;

[assembly: AssemblyTitle("CyberLoader Setup")]
[assembly: AssemblyProduct("CyberLoader")]
[assembly: AssemblyDescription("CyberLoader installer")]
[assembly: AssemblyVersion("1.0.0.0")]

class Options
{
    public string InstallDir, Game, Data, Version = "";
    public bool Seven = true, Desktop = true, StartMenu = true, Launch, Silent, Uninstall, DeleteData;

    public static Options Parse(string[] args)
    {
        Options o = new Options();
        foreach (string a in args)
        {
            string u = a.ToUpperInvariant();
            if (u == "/S") o.Silent = true;
            else if (u == "/UNINSTALL") o.Uninstall = true;
            else if (u == "/NODESKTOP") o.Desktop = false;
            else if (u == "/NOSTART") o.StartMenu = false;
            else if (u == "/LAUNCH") o.Launch = true;
            else if (u == "/DELETEDATA") o.DeleteData = true;
            else if (u.StartsWith("/7ZIP=")) o.Seven = a.Substring(6) != "0";
            else if (u.StartsWith("/D=")) o.InstallDir = a.Substring(3).Trim('"');
            else if (u.StartsWith("/GAME=")) o.Game = a.Substring(6).Trim('"');
            else if (u.StartsWith("/DATA=")) o.Data = a.Substring(6).Trim('"');
        }
        return o;
    }
}

class SetupException : Exception
{
    public bool Retryable;
    public SetupException(string m, bool retryable) : base(m) { Retryable = retryable; }
}

static class Program
{
    [STAThread]
    static int Main(string[] args)
    {
        Options o = Options.Parse(args);
        string self = Path.GetFileNameWithoutExtension(Application.ExecutablePath);
        bool uninstaller = o.Uninstall || self.Equals("Uninstall", StringComparison.OrdinalIgnoreCase);
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        if (o.Silent)
        {
            try
            {
                if (uninstaller) Installer.Uninstall(o, null);
                else
                {
                    Installer.FillDefaults(o);
                    Installer.Install(o, null);
                    if (o.Launch) Installer.Launch(o);
                }
                return 0;
            }
            catch (Exception ex)
            {
                try { File.WriteAllText(Path.Combine(Path.GetTempPath(), "CyberLoader-Setup.log"), ex.ToString()); } catch (Exception) { }
                return 1;
            }
        }
        if (uninstaller) Application.Run(new UninstallForm(o));
        else Application.Run(new Wizard(o));
        return 0;
    }
}

static class Detect
{
    const string ExeRel = @"bin\x64\Cyberpunk2077.exe";

    public static bool IsGame(string dir)
    {
        try { return !string.IsNullOrEmpty(dir) && File.Exists(Path.Combine(dir, ExeRel)); } catch (Exception) { return false; }
    }

    // Steam, GOG, Epic and the usual folders on every fixed drive.
    public static List<string> FindGames()
    {
        List<string> found = new List<string>();
        Action<string> add = delegate (string p)
        {
            if (string.IsNullOrEmpty(p)) return;
            try { p = Path.GetFullPath(p.TrimEnd('\\')); } catch (Exception) { return; }
            if (IsGame(p) && !found.Contains(p, StringComparer.OrdinalIgnoreCase)) found.Add(p);
        };
        try
        {
            // Steam: install folder + every library listed in libraryfolders.vdf
            string steam = Registry.GetValue(@"HKEY_CURRENT_USER\Software\Valve\Steam", "SteamPath", null) as string;
            List<string> libs = new List<string>();
            if (!string.IsNullOrEmpty(steam))
            {
                libs.Add(steam);
                string vdf = Path.Combine(steam, @"steamapps\libraryfolders.vdf");
                if (File.Exists(vdf))
                    foreach (Match m in Regex.Matches(File.ReadAllText(vdf), "\"path\"\\s+\"([^\"]+)\""))
                        libs.Add(m.Groups[1].Value.Replace(@"\\", @"\"));
            }
            foreach (string l in libs) add(Path.Combine(l, @"steamapps\common\Cyberpunk 2077"));
        }
        catch (Exception) { }
        try
        {
            // GOG
            foreach (string id in new string[] { "1423049311", "2093619782" })
                add(Registry.GetValue(@"HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\GOG.com\Games\" + id, "path", null) as string);
        }
        catch (Exception) { }
        try
        {
            // Epic
            string man = @"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests";
            if (Directory.Exists(man))
                foreach (string f in Directory.GetFiles(man, "*.item"))
                {
                    string t = File.ReadAllText(f);
                    if (t.IndexOf("Cyberpunk", StringComparison.OrdinalIgnoreCase) < 0) continue;
                    Match m = Regex.Match(t, "\"InstallLocation\"\\s*:\\s*\"([^\"]+)\"");
                    if (m.Success) add(m.Groups[1].Value.Replace(@"\\", @"\"));
                }
        }
        catch (Exception) { }
        try
        {
            foreach (DriveInfo d in DriveInfo.GetDrives())
            {
                if (d.DriveType != DriveType.Fixed) continue;
                string r = d.RootDirectory.FullName;
                foreach (string rel in new string[] { @"Games\Cyberpunk 2077", @"Cyberpunk 2077", @"GOG Games\Cyberpunk 2077", @"Epic Games\Cyberpunk2077",
                    @"SteamLibrary\steamapps\common\Cyberpunk 2077", @"Program Files (x86)\Steam\steamapps\common\Cyberpunk 2077",
                    @"Program Files\Steam\steamapps\common\Cyberpunk 2077", @"Program Files (x86)\GOG Galaxy\Games\Cyberpunk 2077" })
                    add(Path.Combine(r, rel));
            }
        }
        catch (Exception) { }
        return found;
    }
}

static class Installer
{
    public static Stream Resource(string name)
    {
        return Assembly.GetExecutingAssembly().GetManifestResourceStream(name);
    }

    // The .ico stores PNG pictures; .NET's Icon class cannot read those at arbitrary sizes, so read the PNG directly.
    public static Image IconImage(int size)
    {
        using (Stream s = Resource("cyberloader.ico"))
        {
            byte[] b = new byte[s.Length];
            int got = 0;
            while (got < b.Length) { int n = s.Read(b, got, b.Length - got); if (n <= 0) break; got += n; }
            int count = BitConverter.ToUInt16(b, 4);
            int bestOff = -1, bestLen = 0, bestW = -1;
            for (int i = 0; i < count; i++)
            {
                int e = 6 + 16 * i;
                int w = b[e] == 0 ? 256 : b[e];
                if (bestW < 0 || Math.Abs(w - size) < Math.Abs(bestW - size)) { bestW = w; bestLen = BitConverter.ToInt32(b, e + 8); bestOff = BitConverter.ToInt32(b, e + 12); }
            }
            return Image.FromStream(new MemoryStream(b, bestOff, bestLen));
        }
    }

    public static string PayloadVersion()
    {
        using (Stream s = Resource("payload.zip"))
        using (ZipArchive z = new ZipArchive(s, ZipArchiveMode.Read))
        {
            ZipArchiveEntry e = z.GetEntry("version.txt");
            if (e == null) return "";
            using (StreamReader r = new StreamReader(e.Open())) return r.ReadToEnd().Trim();
        }
    }

    public static string DefaultInstallDir()
    {
        return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), @"Programs\CyberLoader");
    }

    // Where the mod library should live: next to the app when that is the game's drive, otherwise on the game's drive.
    // (Mods are hardlinked into the game, which only works within one drive.)
    public static string DefaultData(string installDir, string game)
    {
        string gd = DriveOf(game), id = DriveOf(installDir);
        if (gd == null || gd == id) return Path.Combine(installDir, "data");
        return gd + @":\CyberLoader\data";
    }

    public static string DriveOf(string path)
    {
        try { return Path.GetPathRoot(Path.GetFullPath(path)).Substring(0, 1).ToUpperInvariant(); } catch (Exception) { return null; }
    }

    public static void FillDefaults(Options o)
    {
        if (string.IsNullOrEmpty(o.InstallDir)) o.InstallDir = DefaultInstallDir();
        if (string.IsNullOrEmpty(o.Game))
        {
            List<string> g = Detect.FindGames();
            if (g.Count > 0) o.Game = g[0];
        }
        if (string.IsNullOrEmpty(o.Data)) o.Data = DefaultData(o.InstallDir, o.Game);
        o.Version = PayloadVersion();
    }

    static string JsonEsc(string s) { return s.Replace("\\", "\\\\").Replace("\"", "\\\""); }

    public static string ReadConfigValue(string installDir, string key)
    {
        try
        {
            string f = Path.Combine(installDir, "cyberloader.json");
            if (!File.Exists(f)) return null;
            Match m = Regex.Match(File.ReadAllText(f), "\"" + key + "\"\\s*:\\s*\"((?:\\\\.|[^\"\\\\])*)\"");
            return m.Success ? m.Groups[1].Value.Replace("\\\\", "\\").Replace("\\\"", "\"") : null;
        }
        catch (Exception) { return null; }
    }

    static void Extract(string resource, string root, Action<int, string> progress, int from, int to, string label)
    {
        using (Stream s = Resource(resource))
        using (ZipArchive z = new ZipArchive(s, ZipArchiveMode.Read))
        {
            string full = Path.GetFullPath(root).TrimEnd('\\') + "\\";
            int n = 0, total = z.Entries.Count;
            foreach (ZipArchiveEntry e in z.Entries)
            {
                n++;
                if (e.FullName.EndsWith("/") || e.Name.Length == 0) continue;
                string dest = Path.GetFullPath(Path.Combine(root, e.FullName.Replace('/', '\\')));
                if (!dest.StartsWith(full, StringComparison.OrdinalIgnoreCase)) throw new SetupException("The installer package is damaged (unsafe path).", false);
                Directory.CreateDirectory(Path.GetDirectoryName(dest));
                try
                {
                    using (Stream src = e.Open())
                    using (FileStream dst = new FileStream(dest, FileMode.Create, FileAccess.Write, FileShare.None))
                        src.CopyTo(dst);
                }
                catch (IOException)
                {
                    throw new SetupException("A file is in use: " + Path.GetFileName(dest) + "\n\nClose CyberLoader (and anything using its folder) and try again.", true);
                }
                if (progress != null && (n % 25 == 0 || n == total)) progress(from + (to - from) * n / total, label);
            }
        }
    }

    public static void Install(Options o, Action<int, string> progress)
    {
        if (progress == null) progress = delegate (int p, string t) { };
        if (!Detect.IsGame(o.Game)) throw new SetupException("The Cyberpunk 2077 folder was not found: " + o.Game, false);
        progress(1, "Preparing...");
        Directory.CreateDirectory(o.InstallDir);
        string exe = Path.Combine(o.InstallDir, "CyberLoader.exe");
        if (File.Exists(exe))
        {
            try { using (new FileStream(exe, FileMode.Open, FileAccess.ReadWrite, FileShare.None)) { } }
            catch (IOException) { throw new SetupException("CyberLoader is running. Close it and try again.", true); }
        }
        Extract("payload.zip", o.InstallDir, progress, 3, o.Seven ? 88 : 94, "Copying CyberLoader...");
        if (o.Seven) Extract("sevenzip.zip", o.InstallDir, progress, 88, 94, "Adding 7-Zip...");
        progress(95, "Writing settings...");
        string version = PayloadVersion();
        File.WriteAllText(Path.Combine(o.InstallDir, "current.txt"), version);
        File.WriteAllText(Path.Combine(o.InstallDir, "cyberloader.json"),
            "{\n \"game\": \"" + JsonEsc(o.Game) + "\",\n \"data\": \"" + JsonEsc(o.Data) + "\",\n \"version\": \"" + JsonEsc(version) + "\"\n}\n");
        Directory.CreateDirectory(o.Data);
        progress(97, "Creating shortcuts...");
        MakeShortcuts(o, exe);
        try { File.Copy(Application.ExecutablePath, Path.Combine(o.InstallDir, "Uninstall.exe"), true); } catch (Exception) { }
        Register(o, version);
        progress(100, "Done");
    }

    // Shortcut labels read "Cyber Loader" (with a space); the product, exe and install folder stay "CyberLoader".
    const string LinkName = "Cyber Loader.lnk";
    const string OldLinkName = "CyberLoader.lnk";   // used before 1.0.0: removed when it points at this install
    static string DesktopDir() { return Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory); }
    static string StartDir() { return Environment.GetFolderPath(Environment.SpecialFolder.Programs); }
    static string DesktopLink() { return Path.Combine(DesktopDir(), LinkName); }
    static string StartLink() { return Path.Combine(StartDir(), LinkName); }
    // (If a link with the new name already exists it is simply rewritten; an install elsewhere would lose its link
    // by design: one Desktop/Start entry per name.)

    // Remove shortcuts with the given names from the Desktop and Start menu, but ONLY ones that point at this
    // install's exe: a shortcut with the same name that belongs to another install (or anything else) is never touched.
    static void RemoveLinks(string exe, params string[] names)
    {
        Type t = Type.GetTypeFromProgID("WScript.Shell");
        if (t == null) return;
        object sh = Activator.CreateInstance(t);
        foreach (string dir in new string[] { DesktopDir(), StartDir() })
            foreach (string name in names)
            {
                string f = Path.Combine(dir, name);
                try
                {
                    if (!File.Exists(f)) continue;
                    object lnk = t.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, sh, new object[] { f });
                    string target = (string)lnk.GetType().InvokeMember("TargetPath", BindingFlags.GetProperty, null, lnk, null);
                    if (string.Equals(target, exe, StringComparison.OrdinalIgnoreCase)) File.Delete(f);
                }
                catch (Exception) { }
            }
    }

    static void MakeShortcuts(Options o, string exe)
    {
        Type t = Type.GetTypeFromProgID("WScript.Shell");
        if (t == null) return;
        object sh = Activator.CreateInstance(t);
        Action<string> make = delegate (string path)
        {
            object lnk = t.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, sh, new object[] { path });
            Type lt = lnk.GetType();
            lt.InvokeMember("TargetPath", BindingFlags.SetProperty, null, lnk, new object[] { exe });
            lt.InvokeMember("WorkingDirectory", BindingFlags.SetProperty, null, lnk, new object[] { o.InstallDir });
            lt.InvokeMember("IconLocation", BindingFlags.SetProperty, null, lnk, new object[] { exe + ",0" });
            lt.InvokeMember("Description", BindingFlags.SetProperty, null, lnk, new object[] { "CyberLoader: Cyberpunk 2077 mod manager" });
            lt.InvokeMember("Save", BindingFlags.InvokeMethod, null, lnk, null);
        };
        RemoveLinks(exe, OldLinkName);
        if (o.Desktop) make(DesktopLink());
        if (o.StartMenu) make(StartLink());
    }

    const string UninstallKey = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\CyberLoader";

    static void Register(Options o, string version)
    {
        try
        {
            using (RegistryKey k = Registry.CurrentUser.CreateSubKey(UninstallKey))
            {
                k.SetValue("DisplayName", "CyberLoader");
                k.SetValue("DisplayVersion", version);
                k.SetValue("Publisher", "CyberLoader");
                k.SetValue("InstallLocation", o.InstallDir);
                k.SetValue("DisplayIcon", Path.Combine(o.InstallDir, "CyberLoader.exe") + ",0");
                k.SetValue("UninstallString", "\"" + Path.Combine(o.InstallDir, "Uninstall.exe") + "\"");
                k.SetValue("NoModify", 1, RegistryValueKind.DWord);
                k.SetValue("NoRepair", 1, RegistryValueKind.DWord);
            }
        }
        catch (Exception) { }
    }

    public static void Launch(Options o)
    {
        try { Process.Start(new ProcessStartInfo(Path.Combine(o.InstallDir, "CyberLoader.exe")) { WorkingDirectory = o.InstallDir }); } catch (Exception) { }
    }

    static void DeleteDir(string dir)
    {
        if (!Directory.Exists(dir)) return;
        foreach (string f in Directory.GetFiles(dir, "*", SearchOption.AllDirectories))
        {
            try { File.SetAttributes(f, FileAttributes.Normal); } catch (Exception) { }
        }
        Directory.Delete(dir, true);
    }

    public static void Uninstall(Options o, Action<int, string> progress)
    {
        if (progress == null) progress = delegate (int p, string t) { };
        string dir = Path.GetDirectoryName(Application.ExecutablePath);
        string exe = Path.Combine(dir, "CyberLoader.exe");
        if (File.Exists(exe))
        {
            try { using (new FileStream(exe, FileMode.Open, FileAccess.ReadWrite, FileShare.None)) { } }
            catch (IOException) { throw new SetupException("CyberLoader is running. Close it and try again.", true); }
        }
        string data = ReadConfigValue(dir, "data");
        progress(10, "Removing shortcuts...");
        RemoveLinks(exe, LinkName, OldLinkName);
        progress(30, "Removing program files...");
        foreach (string sub in new string[] { "runtime", "versions", "tools", "LICENSES" }) DeleteDir(Path.Combine(dir, sub));
        foreach (string f in new string[] { "CyberLoader.exe", "Microsoft.Web.WebView2.Core.dll", "Microsoft.Web.WebView2.WinForms.dll",
            "WebView2Loader.dll", "current.txt", "cyberloader.json", "README.txt", "releases.log" })
            try { File.Delete(Path.Combine(dir, f)); } catch (Exception) { }
        progress(70, o.DeleteData ? "Deleting your library and profiles..." : "Keeping your library and profiles...");
        if (o.DeleteData && !string.IsNullOrEmpty(data)) DeleteDir(data);
        try { Registry.CurrentUser.DeleteSubKeyTree(UninstallKey, false); } catch (Exception) { }
        progress(95, "Finishing...");
        // this exe is running from the folder: let a helper remove it (and the folder, if nothing of yours is left in it)
        try
        {
            string cmd = "/c ping 127.0.0.1 -n 3 > nul & del /f /q \"" + Application.ExecutablePath + "\" & rmdir \"" + dir + "\"";
            ProcessStartInfo psi = new ProcessStartInfo("cmd.exe", cmd);
            psi.CreateNoWindow = true;
            psi.UseShellExecute = false;
            Process.Start(psi);
        }
        catch (Exception) { }
        progress(100, "Done");
    }
}

class UninstallForm : Form
{
    Options o;
    CheckBox chkData;
    Label status;
    Button go, close;
    ProgressBar bar;

    public UninstallForm(Options opts)
    {
        o = opts;
        Text = "Uninstall CyberLoader";
        Font = new Font("Segoe UI", 9f);
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        ClientSize = new Size(480, 250);
        try { using (Stream s = Installer.Resource("cyberloader.ico")) Icon = new Icon(s); } catch (Exception) { }
        Label t = new Label { Text = "Remove CyberLoader from this computer?", Font = new Font("Segoe UI", 13f), AutoSize = true, Location = new Point(20, 18) };
        Label d = new Label { Text = "The app is removed. Your mod library, profiles and trash are kept unless you tick the box below.\nYour game folder is never touched.", Location = new Point(22, 58), Size = new Size(440, 40) };
        chkData = new CheckBox { Text = "Also delete my mod library, profiles and trash", Location = new Point(24, 108), AutoSize = true };
        bar = new ProgressBar { Location = new Point(24, 150), Size = new Size(432, 16), Visible = false };
        status = new Label { Location = new Point(24, 172), Size = new Size(432, 20), ForeColor = Color.DimGray };
        go = new Button { Text = "Uninstall", Location = new Point(280, 205), Size = new Size(88, 30) };
        close = new Button { Text = "Cancel", Location = new Point(376, 205), Size = new Size(88, 30) };
        go.Click += delegate { Run(); };
        close.Click += delegate { Close(); };
        Controls.AddRange(new Control[] { t, d, chkData, bar, status, go, close });
    }

    void Run()
    {
        o.DeleteData = chkData.Checked;
        go.Enabled = false; close.Enabled = false; chkData.Enabled = false; bar.Visible = true;
        Thread th = new Thread(delegate ()
        {
            try
            {
                Installer.Uninstall(o, delegate (int p, string s) { BeginInvoke((MethodInvoker)delegate { bar.Value = p; status.Text = s; }); });
                BeginInvoke((MethodInvoker)delegate { status.Text = "CyberLoader was removed."; close.Text = "Close"; close.Enabled = true; });
            }
            catch (Exception ex)
            {
                BeginInvoke((MethodInvoker)delegate { MessageBox.Show(ex.Message, "Uninstall", MessageBoxButtons.OK, MessageBoxIcon.Warning); go.Enabled = true; close.Enabled = true; chkData.Enabled = true; });
            }
        });
        th.IsBackground = true;
        th.Start();
    }
}

class Wizard : Form
{
    Options o;
    Panel body;
    Label title, sub;
    Button back, next, cancel;
    List<Panel> pages = new List<Panel>();
    int page;
    TextBox txtDir, txtData;
    ComboBox cbGame;
    Label gameStatus, dataNote, summary, installStatus;
    CheckBox chk7z, chkDesktop, chkStart, chkLaunch;
    ProgressBar bar;
    bool dataEdited, installing, done;
    Color ink = Color.FromArgb(32, 33, 38);
    string[] titles = { "Welcome", "Where to install", "Your game", "Where your mods live", "Options", "Ready to install", "Installing", "All set" };
    string[] subs = { "", "Choose the folder for the CyberLoader program.", "CyberLoader needs to know where Cyberpunk 2077 is installed.",
        "Your mod library can grow to tens of GB. Choose where CyberLoader keeps it.", "Pick what to include.", "Check your choices, then install.",
        "Please wait while CyberLoader is installed.", "" };

    public Wizard(Options opts)
    {
        o = opts;
        Installer.FillDefaults(o);
        // an existing install: start from its settings
        string old = Installer.ReadConfigValue(o.InstallDir, "game");
        if (old != null && Detect.IsGame(old)) o.Game = old;
        string oldData = Installer.ReadConfigValue(o.InstallDir, "data");
        if (oldData != null) { o.Data = oldData; dataEdited = true; }
        Text = "CyberLoader Setup";
        Font = new Font("Segoe UI", 9f);
        BackColor = Color.White;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        ClientSize = new Size(640, 440);
        try { using (Stream s = Installer.Resource("cyberloader.ico")) Icon = new Icon(s); } catch (Exception) { }

        title = new Label { Font = new Font("Segoe UI", 16f), Location = new Point(28, 18), Size = new Size(580, 34), ForeColor = ink };
        sub = new Label { Location = new Point(30, 54), Size = new Size(580, 36), ForeColor = Color.DimGray };
        body = new Panel { Location = new Point(0, 96), Size = new Size(640, 276) };
        Panel bottom = new Panel { Location = new Point(0, 384), Size = new Size(640, 56), BackColor = Color.FromArgb(244, 244, 246) };
        back = Btn("Back", 330);
        next = Btn("Next", 428);
        cancel = Btn("Cancel", 526);
        next.BackColor = ink; next.ForeColor = Color.White; next.FlatStyle = FlatStyle.Flat; next.FlatAppearance.BorderSize = 0;
        back.Click += delegate { if (page > 0 && !installing) Show(page - 1); };
        next.Click += delegate { OnNext(); };
        cancel.Click += delegate { Close(); };
        bottom.Controls.AddRange(new Control[] { back, next, cancel });
        Controls.AddRange(new Control[] { title, sub, body, bottom });

        pages.Add(PageWelcome());
        pages.Add(PageLocation());
        pages.Add(PageGame());
        pages.Add(PageData());
        pages.Add(PageOptions());
        pages.Add(PageReady());
        pages.Add(PageInstalling());
        pages.Add(PageFinish());
        foreach (Panel p in pages) { p.Dock = DockStyle.Fill; p.Visible = false; body.Controls.Add(p); }
        FormClosing += delegate (object s, FormClosingEventArgs e)
        {
            if (installing) { e.Cancel = true; return; }
            if (!done && e.CloseReason == CloseReason.UserClosing &&
                MessageBox.Show("Cancel the installation?", "CyberLoader Setup", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) e.Cancel = true;
        };
        Show(0);
    }

    Button Btn(string text, int x)
    {
        return new Button { Text = text, Location = new Point(x, 13), Size = new Size(90, 30), FlatStyle = FlatStyle.System };
    }

    Label Note(string text, int x, int y, int w, int h, bool dim)
    {
        return new Label { Text = text, Location = new Point(x, y), Size = new Size(w, h), ForeColor = dim ? Color.DimGray : ink };
    }

    Panel PageWelcome()
    {
        Panel p = new Panel();
        PictureBox pic = new PictureBox { Location = new Point(30, 12), Size = new Size(72, 72), SizeMode = PictureBoxSizeMode.Zoom };
        try { pic.Image = Installer.IconImage(64); } catch (Exception) { }
        Label t = new Label { Text = "Welcome to CyberLoader " + o.Version, Font = new Font("Segoe UI", 12f), Location = new Point(118, 14), Size = new Size(490, 28), ForeColor = ink };
        Label d = Note("CyberLoader switches sets of Cyberpunk 2077 mods (profiles) on and off safely.\n\nIt keeps your mods in its own library and links them into the game, so turning a profile off leaves no stray files behind, and it never overwrites a file it doesn't own.\n\nThis installs CyberLoader for your Windows account only. No administrator rights are needed.",
            118, 48, 490, 160, false);
        p.Controls.AddRange(new Control[] { pic, t, d });
        return p;
    }

    Panel PageLocation()
    {
        Panel p = new Panel();
        p.Controls.Add(Note("CyberLoader will be installed in this folder:", 30, 8, 570, 20, false));
        txtDir = new TextBox { Text = o.InstallDir, Location = new Point(30, 32), Size = new Size(470, 24) };
        Button br = new Button { Text = "Browse...", Location = new Point(510, 30), Size = new Size(90, 28), FlatStyle = FlatStyle.System };
        br.Click += delegate { string s = Pick(txtDir.Text); if (s != null) txtDir.Text = s; };
        p.Controls.AddRange(new Control[] { txtDir, br });
        p.Controls.Add(Note("About 100 MB. This holds the program only; your mods go in the data folder chosen later. Installing over an older CyberLoader updates it and keeps your library.", 30, 72, 570, 60, true));
        return p;
    }

    Panel PageGame()
    {
        Panel p = new Panel();
        p.Controls.Add(Note("Cyberpunk 2077 folder (the one that contains bin\\x64\\Cyberpunk2077.exe):", 30, 8, 570, 20, false));
        cbGame = new ComboBox { Location = new Point(30, 32), Size = new Size(470, 24), DropDownStyle = ComboBoxStyle.DropDown };
        foreach (string g in Detect.FindGames()) cbGame.Items.Add(g);
        cbGame.Text = o.Game ?? "";
        cbGame.TextChanged += delegate { CheckGame(); };
        cbGame.SelectedIndexChanged += delegate { CheckGame(); };
        Button br = new Button { Text = "Browse...", Location = new Point(510, 30), Size = new Size(90, 28), FlatStyle = FlatStyle.System };
        br.Click += delegate
        {
            string s = Pick(cbGame.Text);
            if (s == null) return;
            if (!Detect.IsGame(s) && Detect.IsGame(Path.Combine(s, "Cyberpunk 2077"))) s = Path.Combine(s, "Cyberpunk 2077");
            cbGame.Text = s;
        };
        gameStatus = new Label { Location = new Point(30, 66), Size = new Size(570, 40) };
        int n = cbGame.Items.Count;
        p.Controls.AddRange(new Control[] { cbGame, br, gameStatus });
        p.Controls.Add(Note(n > 0 ? "Found " + n + " installation" + (n == 1 ? "" : "s") + " automatically (Steam, GOG, Epic or a common folder). Pick one from the list, or browse." :
            "No installation was found automatically. Click Browse and choose the game folder.", 30, 118, 570, 40, true));
        return p;
    }

    void CheckGame()
    {
        bool ok = Detect.IsGame(cbGame.Text.Trim());
        gameStatus.ForeColor = ok ? Color.FromArgb(30, 130, 60) : Color.FromArgb(190, 50, 50);
        gameStatus.Text = ok ? "Found Cyberpunk 2077." : "That folder doesn't contain bin\\x64\\Cyberpunk2077.exe.";
        if (page == 2) next.Enabled = ok;
    }

    Panel PageData()
    {
        Panel p = new Panel();
        p.Controls.Add(Note("Mod library, profiles and trash will be kept in this folder:", 30, 8, 570, 20, false));
        txtData = new TextBox { Text = o.Data, Location = new Point(30, 32), Size = new Size(470, 24) };
        txtData.TextChanged += delegate { dataEdited = true; UpdateDataNote(); };
        Button br = new Button { Text = "Browse...", Location = new Point(510, 30), Size = new Size(90, 28), FlatStyle = FlatStyle.System };
        br.Click += delegate { string s = Pick(txtData.Text); if (s != null) txtData.Text = s; };
        Button rec = new Button { Text = "Use the recommended folder", Location = new Point(30, 66), Size = new Size(190, 28), FlatStyle = FlatStyle.System };
        rec.Click += delegate { txtData.Text = Installer.DefaultData(txtDir.Text.Trim(), cbGame.Text.Trim()); dataEdited = false; UpdateDataNote(); };
        dataNote = new Label { Location = new Point(30, 108), Size = new Size(570, 120) };
        p.Controls.AddRange(new Control[] { txtData, br, rec, dataNote });
        return p;
    }

    void UpdateDataNote()
    {
        string gd = Installer.DriveOf(cbGame.Text.Trim()), dd = Installer.DriveOf(txtData.Text.Trim());
        string free = "";
        try { if (dd != null) free = "  Free space on " + dd + ": " + (new DriveInfo(dd).AvailableFreeSpace / 1073741824L) + " GB."; } catch (Exception) { }
        if (gd != null && dd != null && gd != dd)
        {
            dataNote.ForeColor = Color.FromArgb(190, 110, 0);
            dataNote.Text = "This is on a different drive than the game (" + gd + ": vs " + dd + ":). Windows can't link files between drives, so every mod you turn on would be copied. That is slower and uses twice the space. Choose a folder on drive " + gd + ": if you can." + free;
        }
        else
        {
            dataNote.ForeColor = Color.DimGray;
            dataNote.Text = "Same drive as the game: turning a mod on links its files instead of copying them, which is instant and uses no extra space. Keep this folder where you have room for your mods." + free;
        }
    }

    Panel PageOptions()
    {
        Panel p = new Panel();
        chk7z = new CheckBox { Text = "Install 7-Zip", Checked = o.Seven, Location = new Point(30, 10), AutoSize = true, Font = new Font("Segoe UI", 10f) };
        Label rec = new Label { Text = "recommended", ForeColor = Color.FromArgb(30, 130, 60), Location = new Point(138, 13), AutoSize = true };
        Label d = Note("Needed to import .rar and .7z mods (plain .zip works without it). A private copy goes next to CyberLoader; nothing is installed on your system and your own 7-Zip is left alone.", 50, 36, 550, 50, true);
        chkDesktop = new CheckBox { Text = "Create a Desktop shortcut", Checked = o.Desktop, Location = new Point(30, 104), AutoSize = true };
        chkStart = new CheckBox { Text = "Create a Start menu shortcut", Checked = o.StartMenu, Location = new Point(30, 132), AutoSize = true };
        p.Controls.AddRange(new Control[] { chk7z, rec, d, chkDesktop, chkStart });
        return p;
    }

    Panel PageReady()
    {
        Panel p = new Panel();
        summary = new Label { Location = new Point(30, 8), Size = new Size(570, 240) };
        p.Controls.Add(summary);
        return p;
    }

    Panel PageInstalling()
    {
        Panel p = new Panel();
        bar = new ProgressBar { Location = new Point(30, 30), Size = new Size(570, 20) };
        installStatus = new Label { Location = new Point(30, 60), Size = new Size(570, 24), ForeColor = Color.DimGray };
        p.Controls.AddRange(new Control[] { bar, installStatus });
        return p;
    }

    Panel PageFinish()
    {
        Panel p = new Panel();
        Label t = new Label { Text = "CyberLoader " + o.Version + " is installed.", Font = new Font("Segoe UI", 12f), Location = new Point(30, 12), Size = new Size(570, 28), ForeColor = ink };
        Label d = Note("Open it from the desktop shortcut or the Start menu. Add your mods by dragging a mod archive or folder onto the window.\n\nTo remove CyberLoader later, use Windows Settings > Apps, or run Uninstall.exe in the install folder.", 30, 50, 570, 100, false);
        chkLaunch = new CheckBox { Text = "Start CyberLoader now", Checked = true, Location = new Point(30, 160), AutoSize = true };
        p.Controls.AddRange(new Control[] { t, d, chkLaunch });
        return p;
    }

    string Pick(string start)
    {
        using (FolderBrowserDialog f = new FolderBrowserDialog())
        {
            f.ShowNewFolderButton = true;
            try { if (Directory.Exists(start)) f.SelectedPath = start; } catch (Exception) { }
            return f.ShowDialog(this) == DialogResult.OK ? f.SelectedPath : null;
        }
    }

    void Show(int i)
    {
        page = i;
        for (int k = 0; k < pages.Count; k++) pages[k].Visible = k == i;
        title.Text = i == 0 ? "" : titles[i];
        sub.Text = subs[i];
        back.Visible = i > 0 && i < 6;
        cancel.Visible = i < 7;
        next.Enabled = true;
        next.Text = i == 5 ? "Install" : i == 7 ? "Finish" : "Next";
        if (i == 0) next.Text = "Next";
        if (i == 2) CheckGame();
        if (i == 3)
        {
            if (!dataEdited) txtData.Text = Installer.DefaultData(txtDir.Text.Trim(), cbGame.Text.Trim());
            UpdateDataNote();
        }
        if (i == 5) summary.Text = Summary();
        if (i == 6) { next.Enabled = false; back.Visible = false; cancel.Enabled = false; }
    }

    string Summary()
    {
        StringBuilder sb = new StringBuilder();
        sb.AppendLine("Install CyberLoader " + o.Version + " to:");
        sb.AppendLine("    " + txtDir.Text.Trim());
        sb.AppendLine();
        sb.AppendLine("Cyberpunk 2077 folder:");
        sb.AppendLine("    " + cbGame.Text.Trim());
        sb.AppendLine();
        sb.AppendLine("Mod library, profiles and trash:");
        sb.AppendLine("    " + txtData.Text.Trim());
        sb.AppendLine();
        sb.AppendLine("7-Zip: " + (chk7z.Checked ? "included" : "not included") + "     Desktop shortcut: " + (chkDesktop.Checked ? "yes" : "no") + "     Start menu: " + (chkStart.Checked ? "yes" : "no"));
        return sb.ToString();
    }

    void OnNext()
    {
        if (installing) return;
        if (page == 1)
        {
            string d = txtDir.Text.Trim();
            if (d.Length < 4 || !Path.IsPathRooted(d)) { MessageBox.Show("Please enter a full folder path, like C:\\Programs\\CyberLoader.", "CyberLoader Setup"); return; }
            o.InstallDir = d;
        }
        if (page == 2) { if (!Detect.IsGame(cbGame.Text.Trim())) return; o.Game = cbGame.Text.Trim(); }
        if (page == 3)
        {
            string d = txtData.Text.Trim();
            if (d.Length < 4 || !Path.IsPathRooted(d)) { MessageBox.Show("Please enter a full folder path for your mod library.", "CyberLoader Setup"); return; }
            o.Data = d;
        }
        if (page == 4) { o.Seven = chk7z.Checked; o.Desktop = chkDesktop.Checked; o.StartMenu = chkStart.Checked; }
        if (page == 5) { StartInstall(); return; }
        if (page == 7)
        {
            o.Launch = chkLaunch.Checked;
            if (o.Launch) Installer.Launch(o);
            done = true;
            Close();
            return;
        }
        Show(page + 1);
    }

    void StartInstall()
    {
        installing = true;
        Show(6);
        Thread th = new Thread(delegate ()
        {
            while (true)
            {
                try
                {
                    Installer.Install(o, delegate (int p, string s) { BeginInvoke((MethodInvoker)delegate { bar.Value = Math.Min(100, p); installStatus.Text = s; }); });
                    BeginInvoke((MethodInvoker)delegate { installing = false; done = true; cancel.Enabled = true; Show(7); });
                    return;
                }
                catch (SetupException ex)
                {
                    bool retry = false;
                    Invoke((MethodInvoker)delegate
                    {
                        retry = ex.Retryable && MessageBox.Show(ex.Message, "CyberLoader Setup", MessageBoxButtons.RetryCancel, MessageBoxIcon.Warning) == DialogResult.Retry;
                        if (!retry && !ex.Retryable) MessageBox.Show(ex.Message, "CyberLoader Setup", MessageBoxButtons.OK, MessageBoxIcon.Error);
                    });
                    if (retry) continue;
                    BeginInvoke((MethodInvoker)delegate { installing = false; cancel.Enabled = true; Show(5); });
                    return;
                }
                catch (Exception ex)
                {
                    Invoke((MethodInvoker)delegate { MessageBox.Show("Setup could not finish:\n\n" + ex.Message, "CyberLoader Setup", MessageBoxButtons.OK, MessageBoxIcon.Error); });
                    BeginInvoke((MethodInvoker)delegate { installing = false; cancel.Enabled = true; Show(5); });
                    return;
                }
            }
        });
        th.IsBackground = true;
        th.Start();
    }
}

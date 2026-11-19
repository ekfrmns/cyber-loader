"""Setup must not put a Desktop shortcut on a PC unless the person asks for it (a Setup run, silent or not, used to
recreate one every time). This reads the installer source, because the exe itself is only built when packaging."""
import re
import unittest
from pathlib import Path

SETUP = Path(__file__).resolve().parents[2] / "installer" / "Setup.cs"


class DesktopShortcutDefault(unittest.TestCase):
    def setUp(self):
        self.src = SETUP.read_text(encoding="utf-8")

    def test_desktop_shortcut_is_off_by_default(self):
        m = re.search(r"public bool [^;]*\bDesktop = (true|false)", self.src)
        self.assertIsNotNone(m, "could not find the Desktop default in Setup.cs")
        self.assertEqual(m.group(1), "false")

    def test_only_an_explicit_flag_turns_it_on(self):
        self.assertIn('u == "/DESKTOP") o.Desktop = true', self.src)
        self.assertIn('u == "/NODESKTOP") o.Desktop = false', self.src)  # old command lines keep working

    def test_the_wizard_checkbox_follows_the_default(self):
        self.assertIn("Checked = o.Desktop", self.src)


if __name__ == "__main__":
    unittest.main()

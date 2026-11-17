"""Version and upload date on every mod, imports that keep the original name, and two versions of one mod being on."""
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modman.app import App
from modman.config import Config
from modman.library import clean_name, variant_key
from modman.snapshots import parse_origin, pretty_version

V1 = "Input Loader v0.2.6 for 2.50 4575 0.2.6 2026-10-26T08-38Z Q6xF6llYP"
V2 = "Input Loader v0.2.7 for 2.50 4575 0.2.7 2026-11-02T10-10Z AbCdEfGhI"
BODY = "VTK Vanilla HD - Body 7054 3-4 2024-11-12T01-00Z aaaaaaaaa"
HEAD = "VTK Vanilla HD - Head 7054 3-1 2024-11-12T01-00Z bbbbbbbbb"
OLDSTYLE = "Dog Tags - Main File (AiO)-16403-1-02-1700000000"
PLAIN = "Gamma Plain"


def write(p: Path, text="x"):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


class NamesTest(unittest.TestCase):
    def test_squashed_versions_are_shown_with_dots(self):
        self.assertEqual(pretty_version(parse_origin(OLDSTYLE)), "1.02")
        self.assertEqual(pretty_version(parse_origin(BODY)), "3-4")          # clear style is shown as written
        self.assertEqual(pretty_version(parse_origin(PLAIN)), None)

    def test_a_copy_suffix_does_not_hide_the_origin(self):
        self.assertEqual(parse_origin(V1 + " (2)")["nexusId"], 4575)
        self.assertEqual(parse_origin(OLDSTYLE + " (restored)")["version"], "1-02")
        self.assertEqual(clean_name(V1 + " (2)"), "Input Loader v0.2.6 for 2.50 (2)")
        self.assertEqual(clean_name("Foo-1234-1-0-1700000000"), "Foo")

    def test_same_mod_different_version_share_a_key_but_two_files_of_one_page_do_not(self):
        self.assertEqual(variant_key(V1, "Input Loader v0.2.6 for 2.50"), variant_key(V2, "Input Loader v0.2.7 for 2.50"))
        self.assertNotEqual(variant_key(BODY, "VTK Vanilla HD - Body"), variant_key(HEAD, "VTK Vanilla HD - Head"))
        self.assertIsNone(variant_key(PLAIN, PLAIN))


class AppTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="modman-ver-"))
        game, data, ui = self.tmp / "game", self.tmp / "data", self.tmp / "ui"
        write(game / "bin" / "x64" / "Cyberpunk2077.exe")
        write(ui / "index.html", "<html>ok</html>")
        self.cfg = Config(game=game, data=data, ui=ui)
        self.cfg.ensure()
        for mid in (V1, V2, BODY, HEAD, OLDSTYLE, PLAIN):
            write(self.cfg.library / mid / "archive" / "pc" / "mod" / "a.archive", mid)
        self.app = App(self.cfg)
        self.app.profiles.save("Empty", [])
        self.app.select_profile("Empty")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def mods(self):
        return {m["id"]: m for m in self.app.state_view()["mods"]}

    def test_the_mod_view_has_version_date_and_nexus_number(self):
        m = self.mods()
        self.assertEqual((m[V1]["nexusId"], m[V1]["version"], m[V1]["uploaded"]), (4575, "0.2.6", "2026-10-26"))
        self.assertEqual((m[OLDSTYLE]["nexusId"], m[OLDSTYLE]["version"], m[OLDSTYLE]["uploaded"]), (16403, "1.02", "2023-11-14"))
        self.assertEqual((m[PLAIN]["nexusId"], m[PLAIN]["version"], m[PLAIN]["uploaded"]), (None, None, None))

    def test_other_versions_are_listed_for_both_sides_and_only_for_real_versions(self):
        m = self.mods()
        self.assertEqual((m[V1]["otherVersions"], m[V2]["otherVersions"]), ([V2], [V1]))
        self.assertEqual((m[BODY]["otherVersions"], m[HEAD]["otherVersions"], m[PLAIN]["otherVersions"]), ([], [], []))

    def test_turning_on_two_versions_warns_and_one_is_fine(self):
        self.assertEqual(self.app.toggle(V1, True)["warnings"], [])
        r = self.app.toggle(V2, True)
        self.assertEqual(len(r["warnings"]), 1)
        self.assertIn("two versions of the same mod", r["warnings"][0])
        self.assertEqual(len(self.app.preview()["warnings"]), 1)            # listed once, not once per side
        self.assertEqual(self.app.toggle(V1, False)["warnings"], [])          # turning one off clears it
        self.assertEqual(self.app.preview()["warnings"], [])

    def test_body_and_head_of_one_nexus_page_never_warn(self):
        self.app.toggle(BODY, True)
        self.assertEqual(self.app.toggle(HEAD, True)["warnings"], [])

    def test_state_has_the_games_version_and_update_date(self):
        g = self.app.state_view()["game"]
        self.assertTrue(g["found"])
        self.assertRegex(g["updated"], r"^\d{4}-\d\d-\d\d$")                  # the test game exe has no version resource
        self.assertNotIn("version", g)

    def test_import_keeps_the_file_name_and_a_clash_adds_a_number(self):
        z = self.tmp / "Cool Mod-3333-2-1-1700000000.zip"
        with zipfile.ZipFile(z, "w") as f:
            f.writestr("archive/pc/mod/c.archive", "cc")
        a = self.app.import_path(str(z))
        b = self.app.import_path(str(z))
        self.assertEqual((a["id"], b["id"]), ("Cool Mod-3333-2-1-1700000000", "Cool Mod-3333-2-1-1700000000 (2)"))
        m = self.mods()
        self.assertEqual((m[a["id"]]["name"], m[a["id"]]["version"], m[a["id"]]["nexusId"]), ("Cool Mod", "2.1", 3333))
        self.assertEqual((m[b["id"]]["name"], m[b["id"]]["version"]), ("Cool Mod (2)", "2.1"))
        self.assertEqual(m[a["id"]]["otherVersions"], [b["id"]])             # the same file twice reads as two copies


if __name__ == "__main__":
    unittest.main()

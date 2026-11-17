"""Frameworks a mod needs, guessed from the files it ships (a .reds script needs Redscript, an .xl file ArchiveXL, ...)."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modman.app import App
from modman.config import Config
from modman.library import detect_frameworks
from modman.util import key


def write(p: Path, text="x"):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def keys(*paths):
    return [key(p) for p in paths]


class DetectTest(unittest.TestCase):
    def test_each_file_kind_maps_to_its_framework(self):
        cases = {
            "RED4ext": r"red4ext\plugins\Thing\thing.dll",
            "Redscript": r"r6\scripts\Thing\thing.reds",
            "ArchiveXL": r"archive\pc\mod\thing.xl",
            "TweakXL": r"r6\tweaks\Thing\thing.yaml",
            "Cyber Engine Tweaks": r"bin\x64\plugins\cyber_engine_tweaks\mods\thing\init.lua",
            "Input Loader": r"r6\input\thing.xml",
            "Audioware": r"r6\audioware\thing\audioware.yml",
        }
        for fw, path in cases.items():
            needs, provides = detect_frameworks(keys(path))
            self.assertIn(fw, needs, path)
            self.assertEqual(provides, [])

    def test_plain_archive_mod_needs_nothing(self):
        self.assertEqual(detect_frameworks(keys(r"archive\pc\mod\plain.archive")), ([], []))

    def test_other_file_types_in_those_folders_do_not_count(self):
        # a .txt next to scripts, a .archive next to .xl-free mods, an .xml outside r6\input
        self.assertEqual(detect_frameworks(keys(r"r6\scripts\readme.txt", r"bin\x64\other.xml")), ([], []))

    def test_framework_files_make_it_a_provider_and_not_a_need_of_itself(self):
        needs, provides = detect_frameworks(keys(r"red4ext\plugins\ArchiveXL\ArchiveXL.dll", r"archive\pc\mod\x.xl"))
        self.assertEqual(provides, ["ArchiveXL"])
        self.assertNotIn("ArchiveXL", needs)
        self.assertIn("RED4ext", needs)            # ArchiveXL is itself a RED4ext plugin

    def test_red4ext_itself(self):
        needs, provides = detect_frameworks(keys(r"red4ext\RED4ext.dll", r"bin\x64\winmm.dll"))
        self.assertEqual((needs, provides), ([], ["RED4ext"]))

    def test_input_loader_provider_folder_has_an_underscore(self):
        # found by checking the real library: the shipped plugin folder is red4ext\plugins\input_loader
        self.assertEqual(detect_frameworks(keys(r"red4ext\plugins\input_loader\input_loader.dll"))[1], ["Input Loader"])

    def test_cet_provider(self):
        self.assertEqual(detect_frameworks(keys(r"bin\x64\plugins\cyber_engine_tweaks.asi"))[1], ["Cyber Engine Tweaks"])


class AppTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="modman-fw-"))
        game, data, ui = self.tmp / "game", self.tmp / "data", self.tmp / "ui"
        write(game / "bin" / "x64" / "Cyberpunk2077.exe")
        write(ui / "index.html", "<html>ok</html>")
        cfg = Config(game=game, data=data, ui=ui)
        cfg.ensure()
        lib = cfg.library
        write(lib / "Scripty" / "r6" / "scripts" / "scripty" / "a.reds")
        write(lib / "Styled" / "archive" / "pc" / "mod" / "styled.xl")
        write(lib / "Styled" / "archive" / "pc" / "mod" / "styled.archive")
        write(lib / "Plain" / "archive" / "pc" / "mod" / "plain.archive")
        write(lib / "Red4ext Core" / "red4ext" / "RED4ext.dll")
        write(lib / "Redscript" / "red4ext" / "plugins" / "redscript" / "redscript.dll")
        write(lib / "ArchiveXL" / "red4ext" / "plugins" / "ArchiveXL" / "ArchiveXL.dll")
        write(lib / "ArchiveXL (old)" / "red4ext" / "plugins" / "ArchiveXL" / "ArchiveXL.dll")
        self.app = App(cfg)
        self.app.profiles.save("Empty", [])
        self.app.select_profile("Empty")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def mod(self, mid):
        return {m["id"]: m for m in self.app.state_view()["mods"]}[mid]

    def test_view_lists_guesses_and_suppliers(self):
        self.assertEqual(self.mod("Plain")["autoRequires"], [])
        self.assertEqual(self.mod("Scripty")["autoRequires"], [{"name": "Redscript", "ids": ["Redscript"]}])
        styled = self.mod("Styled")["autoRequires"]
        self.assertEqual(styled, [{"name": "ArchiveXL", "ids": ["ArchiveXL", "ArchiveXL (old)"]}])
        # a framework needs RED4ext, but not itself
        self.assertEqual([n["name"] for n in self.mod("ArchiveXL")["autoRequires"]], ["RED4ext"])

    def test_missing_framework_warns_not_in_library(self):
        self.app.library.mods.pop("Redscript")        # nothing in the library supplies Redscript any more
        r = self.app.toggle("Scripty", True)
        self.assertEqual(r["warnings"], ["Scripty needs Redscript, which is not in your library"])
        self.assertEqual(self.mod("Scripty")["autoRequires"], [{"name": "Redscript", "ids": []}])

    def test_off_supplier_warns_and_any_supplier_satisfies(self):
        self.assertEqual(self.app.toggle("Styled", True)["warnings"], ["Styled needs ArchiveXL, which is off"])
        self.app.toggle("ArchiveXL (old)", True)      # the second supplier is enough
        self.assertEqual(self.app._warnings(), ["ArchiveXL (old) needs RED4ext, which is off"])
        self.app.toggle("Red4ext Core", True)
        self.assertEqual(self.app._warnings(), [])

    def test_turning_off_a_supplier_warns_about_the_mod_that_needs_it(self):
        for m in ("Red4ext Core", "ArchiveXL", "Styled"):
            self.app.toggle(m, True)
        self.assertEqual(self.app._warnings(), [])
        r = self.app.toggle("ArchiveXL", False)
        self.assertEqual(r["warnings"], ["Styled needs ArchiveXL, which is off"])

    def test_plain_mod_never_warns(self):
        self.assertEqual(self.app.toggle("Plain", True)["warnings"], [])

    def test_manual_requires_still_works_and_is_not_doubled(self):
        write(self.app.library.root / "Styled" / ".mod.json", '{"requires": ["ArchiveXL"]}')
        self.app.library.scan()
        self.assertEqual(self.mod("Styled")["requires"], ["ArchiveXL"])
        self.assertEqual(self.mod("Styled")["autoRequires"], [])   # the manual entry already covers it
        r = self.app.toggle("Styled", True)
        self.assertEqual(r["warnings"], ["Styled needs ArchiveXL, which is off"])


class SetRequiresTest(unittest.TestCase):
    """The manual "needs" list (the picker in the UI). Same sandbox library as AppTest, own test cases."""
    setUp, tearDown, mod = AppTest.setUp, AppTest.tearDown, AppTest.mod

    def test_saves_to_the_mods_meta_file_and_survives_a_rescan(self):
        r = self.app.set_requires("Plain", ["Redscript", "Redscript", "Red4ext Core"])
        self.assertEqual(r["mod"]["requires"], ["Redscript", "Red4ext Core"])      # duplicate dropped, order kept
        import json
        meta = json.loads((self.app.library.root / "Plain" / ".mod.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["requires"], ["Redscript", "Red4ext Core"])
        self.app.library.scan()
        self.assertEqual(self.mod("Plain")["requires"], ["Redscript", "Red4ext Core"])

    def test_never_touches_the_mods_files_or_the_game(self):
        before = sorted(str(p.relative_to(self.app.library.root / "Plain")) for p in (self.app.library.root / "Plain").rglob("*") if p.is_file())
        self.app.set_requires("Plain", ["Redscript"])
        self.assertEqual(self.mod("Plain")["files"], 1)       # .mod.json is not a mod file
        self.assertEqual(before, [r"archive\pc\mod\plain.archive"])
        self.assertEqual(list((self.tmp / "game").rglob("*.archive")), [])

    def test_warns_when_the_chosen_mod_is_off_and_clears_when_on(self):
        self.app.toggle("Plain", True)
        r = self.app.set_requires("Plain", ["Redscript"])
        self.assertEqual(r["warnings"], ["Plain needs Redscript, which is off"])
        self.app.toggle("Redscript", True)
        self.assertEqual(self.app.set_requires("Plain", ["Redscript"])["warnings"], [])

    def test_empty_list_clears_it(self):
        self.app.set_requires("Plain", ["Redscript"])
        self.assertEqual(self.app.set_requires("Plain", [])["mod"]["requires"], [])

    def test_rejects_bad_input(self):
        from modman.app import ApiError
        for mid, req, code in [("Nope", [], 404), ("Plain", ["Plain"], 400), ("Plain", ["Nope"], 400),
                               ("Plain", "Redscript", 400), ("Plain", [1], 400)]:
            with self.assertRaises(ApiError) as cm:
                self.app.set_requires(mid, req)
            self.assertEqual(cm.exception.code, code, (mid, req))
        self.assertEqual(self.mod("Plain")["requires"], [])    # nothing was saved


if __name__ == "__main__":
    unittest.main()

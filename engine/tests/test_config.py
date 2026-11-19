import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modman import config, library, util
from modman.app import ApiError, App
from modman.config import Config


class InstallConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="modman-cfg-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.saved = {k: os.environ.pop(k, None) for k in ("MODMAN_DATA", "MODMAN_GAME", "CYBERLOADER_CONFIG")}
        self.addCleanup(lambda: [os.environ.__setitem__(k, v) for k, v in self.saved.items() if v is not None])

    def write_cfg(self, **kw):
        f = self.tmp / "root" / "cyberloader.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(kw))
        os.environ["CYBERLOADER_CONFIG"] = str(f)
        return f

    def test_game_and_data_come_from_the_install_config(self):
        self.write_cfg(game=str(self.tmp / "g"), data=str(self.tmp / "d"))
        c = Config()
        self.assertEqual((c.game, c.data), (self.tmp / "g", self.tmp / "d"))

    def test_data_defaults_to_a_data_folder_next_to_the_config(self):
        f = self.write_cfg(game=str(self.tmp / "g"))
        self.assertEqual(Config().data, f.parent / "data")

    def test_arguments_and_environment_beat_the_config(self):
        self.write_cfg(game=str(self.tmp / "g"), data=str(self.tmp / "d"))
        os.environ["MODMAN_GAME"] = str(self.tmp / "env-game")
        c = Config(data=self.tmp / "arg-data")
        self.assertEqual((c.game, c.data), (self.tmp / "env-game", self.tmp / "arg-data"))

    def test_nothing_configured_means_no_game_and_a_local_data_folder(self):
        os.environ["CYBERLOADER_CONFIG"] = str(self.tmp / "missing.json")
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": str(self.tmp / "local")}):
            c = Config()
        self.assertEqual(c.game, config.NOT_SET)
        self.assertFalse(c.game_found)
        self.assertEqual(c.data, self.tmp / "local" / "CyberLoader" / "data")

    def test_game_found_needs_the_exe(self):
        game = self.tmp / "game"
        self.assertFalse(Config(game=game, data=self.tmp / "d").game_found)
        (game / "bin" / "x64").mkdir(parents=True)
        (game / "bin" / "x64" / "Cyberpunk2077.exe").write_text("x")
        self.assertTrue(Config(game=game, data=self.tmp / "d").game_found)

    def test_private_7zip_next_to_the_app_is_preferred(self):
        root = self.write_cfg(game="x").parent
        (root / "tools" / "7z").mkdir(parents=True)
        (root / "tools" / "7z" / "7z.exe").write_text("fake")
        self.assertEqual(Path(util.find_7z()), root / "tools" / "7z" / "7z.exe")


class FirstRunAndGuards(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="modman-first-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_first_run_creates_an_empty_profile(self):
        app = App(Config(game=self.tmp / "g", data=self.tmp / "d"))
        self.assertEqual(app.profiles.names(), ["Empty"])
        self.assertEqual((app.current, app.working), ("Empty", []))
        self.assertEqual(App(Config(game=self.tmp / "g", data=self.tmp / "d")).profiles.names(), ["Empty"])  # not duplicated

    def test_apply_explains_a_missing_game(self):
        app = App(Config(game=self.tmp / "nowhere", data=self.tmp / "d"))
        with self.assertRaises(ApiError) as cm:
            app.start_apply()
        self.assertEqual(cm.exception.code, 409)
        self.assertIn("Run CyberLoader Setup again", cm.exception.message)
        self.assertFalse(app.state_view()["game"]["found"])


class ZipImport(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="modman-zip-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.lib = library.Library(self.tmp / "lib")
        p = mock.patch.object(library, "find_7z", return_value=None)   # prove zips need no 7-Zip
        p.start()
        self.addCleanup(p.stop)

    def make_zip(self, name, entries):
        z = self.tmp / name
        with zipfile.ZipFile(z, "w") as f:
            for n, data in entries.items():
                f.writestr(n, data)
        return z

    def test_plain_zip_imports_without_7zip(self):
        z = self.make_zip("My Mod.zip", {"Wrapper/archive/pc/mod/x.archive": "xx", "Wrapper/r6/scripts/M/m.reds": "m"})
        mid, warns = self.lib.import_sources([z], "My Mod", self.tmp / "work")
        self.assertEqual(sorted(self.lib.mods[mid].files.values()), ["archive\\pc\\mod\\x.archive", "r6\\scripts\\M\\m.reds"])
        self.assertEqual(warns, [])

    def test_zip_slip_is_refused(self):
        z = self.make_zip("evil.zip", {"../../escape.txt": "boom", "archive/pc/mod/ok.archive": "ok"})
        with self.assertRaises(RuntimeError) as cm:
            self.lib.import_sources([z], "Evil", self.tmp / "work")
        self.assertIn("unsafe path", str(cm.exception))
        self.assertFalse((self.tmp / "escape.txt").exists())
        self.assertFalse((self.tmp / "lib" / "Evil").exists())

    def test_rar_and_7z_say_they_need_7zip(self):
        rar = self.tmp / "m.rar"
        rar.write_bytes(b"Rar!\x1a\x07\x00")
        with self.assertRaises(RuntimeError) as cm:
            self.lib.import_sources([rar], "Rar Mod", self.tmp / "work")
        self.assertIn("need 7-Zip", str(cm.exception))


if __name__ == "__main__":
    unittest.main()


class DefaultLook(unittest.TestCase):
    """A fresh install starts dark with the pink-red accent; whatever is saved still wins."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="modman-look-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.saved = {k: os.environ.pop(k, None) for k in ("MODMAN_DATA", "MODMAN_GAME", "CYBERLOADER_CONFIG")}
        self.addCleanup(lambda: [os.environ.__setitem__(k, v) for k, v in self.saved.items() if v is not None])

    def cfg(self):
        c = Config(game=self.tmp / "game", data=self.tmp / "data", ui=self.tmp / "ui")
        c.ensure()
        return c

    def test_fresh_install_is_dark_and_red(self):
        self.assertEqual(self.cfg().settings(), {"theme": "dark", "accent": "#ff375f"})

    def test_saved_choices_still_win(self):
        c = self.cfg()
        c.update_settings(theme="light", accent="#0a84ff")
        self.assertEqual(self.cfg().settings(), {"theme": "light", "accent": "#0a84ff"})

    def test_only_what_was_changed_is_saved(self):
        c = self.cfg()
        c.update_settings(theme="system")
        self.assertEqual(self.cfg().settings(), {"theme": "system", "accent": "#ff375f"})

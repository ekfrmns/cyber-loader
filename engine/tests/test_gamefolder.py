"""Changing the game folder after install: checking a path, saving it, and every refusal. All in a throwaway sandbox
(temp install folder with its cyberloader.json, two temp game folders, temp data); nothing real is touched."""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modman import config
from modman.app import ApiError, App
from modman.config import Config, check_game_folder
from modman.server import make_handler, route

IDLE = {"game_running": False, "vortex_running": False}


def write(p: Path, text="x"):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def tree(root: Path) -> dict:
    """Every file and folder under root with a hash of its content: used to prove a folder was not touched."""
    out = {}
    for p in sorted(root.rglob("*")):
        out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "<dir>"
    return out


class GameFolderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="modman-gf-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.saved = {k: os.environ.pop(k, None) for k in ("MODMAN_DATA", "MODMAN_GAME", "CYBERLOADER_CONFIG")}
        self.addCleanup(lambda: [os.environ.__setitem__(k, v) if v is not None else os.environ.pop(k, None) for k, v in self.saved.items()])
        self.old, self.new = self.tmp / "Old Game", self.tmp / "New Game"
        for g in (self.old, self.new):
            write(g / "bin" / "x64" / "Cyberpunk2077.exe", g.name)
            write(g / "r6" / "keep.txt", "the game's own file")
        self.cfg_file = self.tmp / "root" / "cyberloader.json"
        write(self.cfg_file, json.dumps({"game": str(self.old), "data": str(self.tmp / "data"), "other": {"keep": 1}}))
        os.environ["CYBERLOADER_CONFIG"] = str(self.cfg_file)
        self.cfg = Config(ui=self.tmp / "ui")
        self.cfg.ensure()
        write(self.cfg.library / "Core" / "red4ext" / "core.dll", "core")
        self.app = App(self.cfg)
        for name in ("preflight",):
            p = mock.patch(f"modman.app.{name}", return_value=dict(IDLE))
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch("modman.app.game_running", return_value=False)
        p.start()
        self.addCleanup(p.stop)

    def saved_cfg(self):
        return json.loads(self.cfg_file.read_text(encoding="utf-8"))

    def deploy_core(self):
        self.app.toggle("Core", True)
        self.app.apply_blocking()
        self.assertEqual(len(self.app.state.files), 1)

    # ---- looking at a path
    def test_check_explains_each_kind_of_wrong_path(self):
        self.assertIn("Paste the full path", check_game_folder("  ")["message"])
        self.assertIn("full path", check_game_folder("Games\\Cyberpunk")["message"])
        self.assertIn("doesn’t exist", check_game_folder(str(self.tmp / "nope"))["message"])
        f = self.tmp / "a file.txt"
        write(f)
        self.assertIn("file, not a folder", check_game_folder(str(f))["message"])
        r = check_game_folder(str(self.tmp))
        self.assertEqual((r["isFolder"], r["found"]), (True, False))
        self.assertIn("bin\\x64\\Cyberpunk2077.exe", r["message"])

    def test_check_accepts_the_game_folder_and_cleans_up_what_was_pasted(self):
        want = str(self.new)
        for pasted in (str(self.new), f'  "{self.new}"  ', str(self.new / "bin"), str(self.new / "bin" / "x64"),
                       str(self.new / "bin" / "x64" / "Cyberpunk2077.exe")):
            r = check_game_folder(pasted)
            self.assertEqual((r["path"], r["found"], r["isFolder"]), (want, True, True), pasted)
        self.assertRegex(r["updated"], r"^\d{4}-\d\d-\d\d$")
        self.assertNotIn("version", r)                      # the fake exe has no version resource

    def test_check_flags_the_folder_already_in_use_and_changes_nothing(self):
        before = tree(self.tmp)
        self.assertTrue(self.app.check_game_folder(str(self.old))["same"])
        self.assertFalse(self.app.check_game_folder(str(self.new))["same"])
        self.assertEqual(tree(self.tmp), before)

    # ---- the current folder
    def test_game_folder_reports_the_current_one(self):
        g = self.app.game_folder()
        self.assertEqual((g["path"], g["found"], g["canChange"], g["reason"], g["deployedCount"]), (str(self.old), True, True, None, 0))
        self.assertIn("updated", g)

    def test_a_missing_game_is_reported_not_hidden(self):
        write(self.cfg_file, json.dumps({"game": str(self.tmp / "gone"), "data": str(self.tmp / "data")}))
        g = App(Config(ui=self.tmp / "ui")).game_folder()
        self.assertEqual((g["path"], g["found"], g["canChange"]), (str(self.tmp / "gone"), False, True))
        write(self.cfg_file, json.dumps({"data": str(self.tmp / "data")}))
        g = App(Config(ui=self.tmp / "ui")).game_folder()
        self.assertEqual((g["path"], g["found"], g["canChange"]), (None, False, True))

    # ---- the happy path
    def test_changing_the_folder_saves_it_keeps_other_keys_and_applies_at_once(self):
        old_tree, new_tree = tree(self.old), tree(self.new)
        r = self.app.set_game_folder(str(self.new))
        self.assertEqual((r["ok"], r["changed"], r["path"], r["found"]), (True, True, str(self.new), True))
        self.assertEqual(self.saved_cfg(), {"game": str(self.new), "data": str(self.tmp / "data"), "other": {"keep": 1}})
        self.assertEqual(self.cfg.game, self.new)                           # in use now, no restart
        self.assertEqual(self.app.state_view()["game"]["found"], True)
        self.assertEqual(Config(ui=self.tmp / "ui").game, self.new)         # and after a restart
        self.assertEqual((tree(self.old), tree(self.new)), (old_tree, new_tree))   # nothing copied, moved or deleted
        self.assertEqual([p.name for p in self.cfg_file.parent.iterdir()], ["cyberloader.json"])   # no temp file left

    def test_the_new_folder_is_used_for_the_next_apply(self):
        self.app.set_game_folder(str(self.new))
        self.deploy_core()
        self.assertTrue((self.new / "red4ext" / "core.dll").is_file())
        self.assertFalse((self.old / "red4ext" / "core.dll").exists())

    def test_a_pasted_exe_path_is_enough(self):
        self.app.set_game_folder(str(self.new / "bin" / "x64" / "Cyberpunk2077.exe"))
        self.assertEqual(self.cfg.game, self.new)

    def test_choosing_the_same_folder_changes_nothing(self):
        before = self.cfg_file.read_bytes()
        r = self.app.set_game_folder(str(self.old))
        self.assertEqual((r["ok"], r["changed"]), (True, False))
        self.assertEqual(self.cfg_file.read_bytes(), before)

    def test_old_records_of_dirs_and_left_files_are_dropped_with_nothing_touched(self):
        self.deploy_core()
        self.app.toggle("Core", False)
        self.app.apply_blocking()
        self.assertEqual(len(self.app.state.files), 0)
        self.app.state.dirs, self.app.state.left = ["red4ext"], {"red4ext\\x.dll"}
        self.app.state.save()
        old_tree = tree(self.old)
        self.app.set_game_folder(str(self.new))
        self.assertEqual((self.app.state.dirs, self.app.state.left), ([], set()))
        self.assertEqual(config.read_json(self.cfg.state_dir / "deployed.json")["dirs"], [])
        self.assertEqual(tree(self.old), old_tree)

    # ---- refusals (each leaves the settings file and both folders exactly as they were)
    def refused(self, code, text, path=None):
        before_cfg, before = self.cfg_file.read_bytes(), (tree(self.old), tree(self.new))
        with self.assertRaises(ApiError) as cm:
            self.app.set_game_folder(str(self.new) if path is None else path)
        self.assertEqual(cm.exception.code, code)
        self.assertIn(text, cm.exception.message)
        self.assertEqual(self.cfg_file.read_bytes(), before_cfg)
        self.assertEqual(self.cfg.game, self.old)
        self.assertEqual((tree(self.old), tree(self.new)), before)

    def test_refused_while_mods_are_placed_and_fine_after_turning_them_off(self):
        self.deploy_core()
        self.assertFalse(self.app.game_folder()["canChange"])
        self.assertIn("Turn everything off and apply first", self.app.game_folder()["reason"])
        self.refused(409, "Turn everything off and apply first")
        self.app.toggle("Core", False)
        self.app.apply_blocking()
        self.assertTrue(self.app.game_folder()["canChange"])
        self.assertTrue(self.app.set_game_folder(str(self.new))["changed"])

    def test_refused_while_the_game_is_running(self):
        with mock.patch("modman.app.preflight", return_value={"game_running": True, "vortex_running": False}):
            self.refused(409, "The game is running")
        with mock.patch("modman.app.game_running", return_value=True):
            self.assertIn("The game is running", self.app.game_folder()["reason"])

    def test_refused_while_an_apply_is_running(self):
        self.app.job = {"state": "running", "percent": 10, "text": "Linking"}
        self.refused(423, "An apply is running")
        self.assertFalse(self.app.game_folder()["canChange"])

    def test_refused_for_a_folder_that_is_not_the_game(self):
        self.refused(400, "doesn’t look like Cyberpunk 2077", str(self.tmp))
        self.refused(400, "doesn’t exist", str(self.tmp / "nope"))
        self.refused(400, "Paste the full path", "")

    def test_refused_when_the_folder_was_given_on_the_command_line(self):
        app = App(Config(game=self.old, ui=self.tmp / "ui"))
        g = app.game_folder()
        self.assertEqual((g["canChange"], g["found"]), (False, True))
        with self.assertRaises(ApiError) as cm:
            app.set_game_folder(str(self.new))
        self.assertEqual(cm.exception.code, 409)
        self.assertEqual(json.loads(self.cfg_file.read_text())["game"], str(self.old))

    def test_refused_when_the_data_folder_was_given_on_the_command_line(self):
        app = App(Config(data=self.tmp / "other-data", ui=self.tmp / "ui"))      # game still comes from the install's file
        self.assertFalse(app.game_folder()["canChange"])
        before = self.cfg_file.read_bytes()
        with self.assertRaises(ApiError) as cm:
            app.set_game_folder(str(self.new))
        self.assertEqual(cm.exception.code, 409)
        self.assertEqual(self.cfg_file.read_bytes(), before)                     # the real install's file is never rewritten

    def test_a_path_with_accents_is_saved_as_plain_text_for_setup_to_read(self):
        odd = self.tmp / "José Games"
        write(odd / "bin" / "x64" / "Cyberpunk2077.exe")
        self.app.set_game_folder(str(odd))
        text = self.cfg_file.read_text(encoding="utf-8")
        self.assertIn("José", text)
        self.assertNotIn("\\u00e9", text)
        self.assertEqual(Config(ui=self.tmp / "ui").game, odd)

    def test_refused_without_a_settings_file(self):
        os.environ["CYBERLOADER_CONFIG"] = str(self.tmp / "missing.json")
        app = App(Config(game=None, data=self.tmp / "d2", ui=self.tmp / "ui"))
        self.assertIn("nowhere to save", app.game_folder()["reason"])
        with self.assertRaises(ApiError) as cm:
            app.set_game_folder(str(self.new))
        self.assertEqual(cm.exception.code, 409)

    def test_a_damaged_settings_file_is_never_overwritten(self):
        self.cfg_file.write_text("{ not json", encoding="utf-8")
        with self.assertRaises(ApiError) as cm:
            self.app.set_game_folder(str(self.new))
        self.assertEqual(cm.exception.code, 500)
        self.assertIn("nothing changed", cm.exception.message)
        self.assertEqual(self.cfg_file.read_text(encoding="utf-8"), "{ not json")
        self.assertEqual(self.cfg.game, self.old)

    def test_a_failed_write_keeps_the_old_folder(self):
        with mock.patch("modman.config.write_json", side_effect=PermissionError("denied")):
            with self.assertRaises(ApiError) as cm:
                self.app.set_game_folder(str(self.new))
        self.assertEqual(cm.exception.code, 500)
        self.assertEqual((self.cfg.game, self.saved_cfg()["game"]), (self.old, str(self.old)))

    # ---- over the wire
    def test_routes(self):
        self.assertEqual(route(self.app, "GET", "/api/game-folder", {})["path"], str(self.old))
        r = route(self.app, "POST", "/api/game-folder/check", {"path": str(self.new)})
        self.assertEqual((r["found"], r["same"]), (True, False))
        r = route(self.app, "POST", "/api/game-folder", {"path": str(self.new)})
        self.assertEqual((r["ok"], r["path"]), (True, str(self.new)))

    def test_http_status_codes(self):
        box = {"port": 0}
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), None)
        box["port"] = httpd.server_address[1]
        httpd.RequestHandlerClass = make_handler(self.app, box)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)

        def post(path, body):
            req = urllib.request.Request(f"http://127.0.0.1:{box['port']}{path}", method="POST", data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read())

        self.assertEqual(post("/api/game-folder", {"path": str(self.tmp)})[0], 400)
        self.deploy_core()
        code, body = post("/api/game-folder", {"path": str(self.new)})
        self.assertEqual(code, 409)
        self.assertIn("Turn everything off", body["error"])


if __name__ == "__main__":
    unittest.main()

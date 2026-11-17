"""Categories: the name-based guess (new keywords) and moving a mod to another category by hand."""
import json
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modman.app import ApiError, App
from modman.config import Config
from modman.library import GROUPS, guess_group
from modman.server import make_handler


def write(p: Path, text="x"):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


class GuessTest(unittest.TestCase):
    def test_new_keywords(self):
        for name, group in [("flower tattoo KSUV (female)", "Body"), ("Snake Tattoo (VTK)", "Body"), ("Sedth_Teeth_and_Braces_CCXL", "Body"),
                            ("Grillz pack", "Body"), ("Skin tone pack", "Body"), ("1. UV Framework 4.1", "Framework"), ("UV Framework", "Framework")]:
            self.assertEqual(guess_group(name), group, name)

    def test_old_guesses_still_hold(self):
        for name, group in [("RED4ext", "Framework"), ("Chic Dress - Archive XL", "Clothing"), ("Valentino Holsters - Main File", "Clothing"),
                            ("Better Vehicle Handling", "Gameplay"), ("Some Totally Unknown Mod", "Other"), ("Skinwalker Quest", "Content")]:
            self.assertEqual(guess_group(name), group, name)

    def test_the_group_list_matches_the_api(self):
        self.assertEqual(GROUPS, ("Framework", "Body", "Characters", "Clothing", "Gameplay", "Content", "Other"))


class MoveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="modman-cat-"))
        game, data, ui = self.tmp / "game", self.tmp / "data", self.tmp / "ui"
        write(game / "bin" / "x64" / "Cyberpunk2077.exe")
        write(ui / "index.html", "<html>ok</html>")
        cfg = Config(game=game, data=data, ui=ui)
        cfg.ensure()
        write(cfg.library / "Mystery Thing" / "archive" / "pc" / "mod" / "a.archive")
        write(cfg.library / "RED4ext" / "red4ext" / "RED4ext.dll")
        self.app = App(cfg)
        self.cfg = cfg

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def mod(self, mid):
        return {m["id"]: m for m in self.app.state_view()["mods"]}[mid]

    def test_move_is_saved_and_survives_a_rescan(self):
        self.assertEqual(self.mod("Mystery Thing")["group"], "Other")
        r = self.app.set_group("Mystery Thing", "Body")
        self.assertEqual((r["ok"], r["mod"]["group"]), (True, "Body"))
        meta = json.loads((self.cfg.library / "Mystery Thing" / ".mod.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["group"], "Body")
        self.app.library.scan()
        self.assertEqual(self.mod("Mystery Thing")["group"], "Body")

    def test_it_beats_the_name_guess_and_every_category_works(self):
        for g in GROUPS:
            self.assertEqual(self.app.set_group("RED4ext", g)["mod"]["group"], g)
            self.app.library.scan()
            self.assertEqual(self.mod("RED4ext")["group"], g)

    def test_the_core_flag_follows_the_framework_category(self):
        self.assertTrue(self.mod("RED4ext")["framework"])
        self.assertFalse(self.app.set_group("RED4ext", "Gameplay")["mod"]["framework"])
        self.assertTrue(self.app.set_group("RED4ext", "Framework")["mod"]["framework"])
        self.assertTrue(self.app.set_group("Mystery Thing", "Framework")["mod"]["framework"])

    def test_it_only_touches_the_mods_own_info_file(self):
        before = sorted(str(p.relative_to(self.cfg.library)) for p in self.cfg.library.rglob("*") if p.is_file() and p.name != ".mod.json")
        self.app.set_group("Mystery Thing", "Clothing")
        after = sorted(str(p.relative_to(self.cfg.library)) for p in self.cfg.library.rglob("*") if p.is_file() and p.name != ".mod.json")
        self.assertEqual(before, after)
        self.assertEqual(self.mod("Mystery Thing")["files"], 1)
        self.assertEqual(list((self.tmp / "game").rglob("*.archive")), [])

    def test_bad_input_changes_nothing(self):
        for mid, g, code in [("Nope", "Body", 404), ("Mystery Thing", "Banana", 400), ("Mystery Thing", "", 400), ("Mystery Thing", "body", 400)]:
            with self.assertRaises(ApiError) as cm:
                self.app.set_group(mid, g)
            self.assertEqual(cm.exception.code, code, (mid, g))
        self.assertEqual(self.mod("Mystery Thing")["group"], "Other")
        self.assertFalse((self.cfg.library / "Mystery Thing" / ".mod.json").exists())

    def test_http_route(self):
        box = {"port": 0}
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), None)
        box["port"] = httpd.server_address[1]
        httpd.RequestHandlerClass = make_handler(self.app, box)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            def post(body):
                req = urllib.request.Request(f"http://127.0.0.1:{box['port']}/api/mod/group", method="POST", data=json.dumps(body).encode(),
                                             headers={"Content-Type": "application/json"})
                try:
                    with urllib.request.urlopen(req) as r:
                        return r.status, json.loads(r.read())
                except urllib.error.HTTPError as e:
                    return e.code, json.loads(e.read())
            self.assertEqual(post({"id": "Mystery Thing", "group": "Body"})[1]["mod"]["group"], "Body")
            self.assertEqual(post({"id": "Mystery Thing", "group": "Nope"})[0], 400)
            self.assertEqual(post({"id": "Gone", "group": "Body"})[0], 404)
        finally:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()

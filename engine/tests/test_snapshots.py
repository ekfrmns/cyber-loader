"""Setup history: automatic snapshots after Apply, restoring an older setup, and naming the old version of a mod."""
import json
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modman import snapshots as snapmod
from modman.app import ApiError, App
from modman.config import Config
from modman.server import make_handler
from modman.snapshots import parse_origin

A_OLD = "Alpha Mod 1111 1.0.0 2026-01-02T03-04Z abcd1234"
A_NEW = "Alpha Mod 1111 1.1.0 2026-02-03T03-04Z efgh5678"
B = "Beta-2222-2-0-1-1698765432"
C = "Gamma Plain"


def write(p: Path, text="x"):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


class ParseTest(unittest.TestCase):
    def test_clear_style(self):
        self.assertEqual(parse_origin("Sample Loader v0.2.6 for 2.50 1234 0.2.6 2026-10-26T08-38Z Q6xF6llYP"),
                         {"nexusId": 1234, "version": "0.2.6", "date": "2026-10-26", "style": "clear"})

    def test_v_prefix_is_dropped(self):
        self.assertEqual(parse_origin("Thing 1234 v1.2 2026-01-01T00-00Z abc")["version"], "1.2")

    def test_older_style_keeps_the_version_as_written_and_dates_the_upload(self):
        self.assertEqual(parse_origin(B), {"nexusId": 2222, "version": "2-0-1", "date": "2023-10-31", "style": "squashed"})

    def test_plain_folder_has_nothing(self):
        self.assertEqual(parse_origin(C), {})
        self.assertEqual(parse_origin("My Mod 2.0"), {})


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="modman-snap-"))
        game, data, ui = self.tmp / "game", self.tmp / "data", self.tmp / "ui"
        write(game / "bin" / "x64" / "Cyberpunk2077.exe")
        write(ui / "index.html", "<html>ok</html>")
        self.cfg = Config(game=game, data=data, ui=ui)
        self.cfg.ensure()
        lib = self.cfg.library
        write(lib / A_OLD / "archive" / "pc" / "mod" / "alpha.archive", "alpha-old")
        write(lib / B / "archive" / "pc" / "mod" / "beta.archive", "beta")
        write(lib / C / "archive" / "pc" / "mod" / "gamma.archive", "gamma")
        self.app = App(self.cfg)
        self.app.profiles.save("Main", [])
        self.app.select_profile("Main")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def apply(self, *ids):
        for m in list(self.app.working):
            self.app.toggle(m, False)
        for m in ids:
            self.app.toggle(m, True)
        return self.app.apply_blocking()

    def deployed_files(self):
        return sorted(p.name for p in (self.tmp / "game").rglob("*.archive"))


class AutoSnapshotTest(Base):
    def test_a_good_apply_saves_one_snapshot_with_order_and_versions(self):
        self.apply(B, A_OLD, C)
        items = self.app.list_snapshots()["items"]
        self.assertEqual(len(items), 1)
        it = items[0]
        self.assertEqual((it["auto"], it["pinned"], it["name"], it["profile"], it["count"]), (True, False, None, "Main", 3))
        s = self.app.get_snapshot(it["id"])
        self.assertEqual([m["id"] for m in s["mods"]], [B, A_OLD, C])           # order is kept (later wins)
        alpha = s["mods"][1]
        self.assertEqual((alpha["name"], alpha["version"], alpha["date"], alpha["nexusId"]), ("Alpha Mod", "1.0.0", "2026-01-02", 1111))
        self.assertEqual(s["mods"][2]["version"], None)                         # plain folder: nothing to say

    def test_snapshot_file_holds_no_mod_files(self):
        self.apply(A_OLD)
        f = next(self.cfg.snapshots_dir.glob("*.json"))
        self.assertLess(f.stat().st_size, 2000)
        self.assertEqual(set(json.loads(f.read_text())["mods"][0]), {"id", "name", "files", "size", "nexusId", "version", "date"})

    def test_same_setup_twice_is_one_snapshot_a_change_is_a_new_one(self):
        self.apply(A_OLD)
        self.apply(A_OLD)
        self.assertEqual(len(self.app.list_snapshots()["items"]), 1)
        time.sleep(1.1)                       # ids are stamped to the second
        self.apply(A_OLD, B)
        self.assertEqual(len(self.app.list_snapshots()["items"]), 2)

    def test_the_empty_setup_counts_too(self):
        self.apply(A_OLD)
        time.sleep(1.1)
        self.apply()
        self.assertEqual([i["count"] for i in self.app.list_snapshots()["items"]], [0, 1])   # newest first

    def test_a_problem_saving_never_breaks_the_apply(self):
        self.app.snapshots.save = lambda *a, **k: (_ for _ in ()).throw(OSError("disk full"))
        res = self.apply(A_OLD)
        self.assertFalse(res.get("errors"))
        self.assertEqual(self.deployed_files(), ["alpha.archive"])

    def test_the_background_apply_saves_it_too(self):
        self.app.toggle(A_OLD, True)
        self.app.start_apply()
        for _ in range(100):
            if self.app.job["state"] != "running":
                break
            time.sleep(0.1)
        self.assertEqual(self.app.job["state"], "done")
        self.assertEqual(len(self.app.list_snapshots()["items"]), 1)


class RestoreTest(Base):
    def test_restore_stages_the_old_list_and_touches_nothing_in_the_game(self):
        self.apply(A_OLD, B)
        sid = self.app.list_snapshots()["items"][0]["id"]
        time.sleep(1.1)
        self.apply(C)
        before = self.deployed_files()
        view = self.app.restore_snapshot(sid)
        self.assertEqual(self.app.working, [A_OLD, B])
        self.assertEqual(view["restored"], {"count": 2, "missing": [], "changed": 0})
        self.assertEqual(self.deployed_files(), before)                          # game untouched until Apply
        self.assertEqual({m["id"]: m["pending"] for m in view["mods"]}[C], "off")
        self.assertEqual({m["id"]: m["pending"] for m in view["mods"]}[A_OLD], "on")
        self.app.apply_blocking()
        self.assertEqual(self.deployed_files(), ["alpha.archive", "beta.archive"])

    def test_list_shows_what_a_restore_would_turn_on_and_off(self):
        self.apply(A_OLD, B)
        time.sleep(1.1)
        self.apply(C)
        old = self.app.list_snapshots()["items"][1]
        self.assertEqual((old["turnOn"], old["turnOff"]), (2, 1))

    def test_updated_mod_is_named_old_and_new(self):
        self.apply(A_OLD, C)
        sid = self.app.list_snapshots()["items"][0]["id"]
        shutil.rmtree(self.cfg.library / A_OLD)                                   # the old folder is gone ...
        write(self.cfg.library / A_NEW / "archive" / "pc" / "mod" / "alpha.archive", "alpha-new")   # ... replaced by the update
        self.app.library.scan()
        row = self.app.get_snapshot(sid)["mods"][0]
        self.assertEqual((row["status"], row["version"], row["nexusId"]), ("missing", "1.0.0", 1111))
        self.assertEqual((row["replacedBy"]["version"], row["replacedBy"]["date"]), ("1.1.0", "2026-02-03"))
        view = self.app.restore_snapshot(sid)
        self.assertEqual(self.app.working, [C])                                    # the missing one is skipped, not invented
        self.assertEqual(view["restored"]["missing"], [{"name": "Alpha Mod", "version": "1.0.0", "date": "2026-01-02", "nexusId": 1111}])

    def test_changed_files_are_flagged_and_a_deleted_mod_says_it_is_in_the_trash(self):
        self.apply(A_OLD, B, C)
        sid = self.app.list_snapshots()["items"][0]["id"]
        write(self.cfg.library / A_OLD / "archive" / "pc" / "mod" / "alpha.archive", "alpha-bigger-now")   # same folder, new bytes
        self.app.library.scan()
        self.apply()                                                               # turn everything off so B can be deleted
        self.app.delete_mod(B)
        rows = {m["id"]: m for m in self.app.get_snapshot(sid)["mods"]}
        self.assertEqual(rows[A_OLD]["status"], "changed")
        self.assertEqual(rows[C]["status"], "same")
        self.assertEqual((rows[B]["status"], rows[B]["inTrash"]), ("missing", True))
        item = next(i for i in self.app.list_snapshots()["items"] if i["id"] == sid)
        self.assertEqual((item["changed"], item["missing"]), (1, 1))

    def test_refused_while_an_apply_is_running_and_for_unknown_ids(self):
        self.apply(A_OLD)
        sid = self.app.list_snapshots()["items"][0]["id"]
        self.app.job = {"state": "running", "percent": 0, "text": ""}
        with self.assertRaises(ApiError) as cm:
            self.app.restore_snapshot(sid)
        self.assertEqual(cm.exception.code, 423)
        self.app.job = {"state": "idle", "percent": 0, "text": ""}
        for bad in ("20200101-000000-0000", "../../etc"):
            with self.assertRaises(ApiError) as cm:
                self.app.restore_snapshot(bad)
            self.assertEqual(cm.exception.code, 404)


class KeepTest(Base):
    def test_save_by_hand_is_named_and_pinned(self):
        self.app.toggle(A_OLD, True)
        sid = self.app.save_snapshot("works before the patch")["id"]
        it = self.app.list_snapshots()["items"][0]
        self.assertEqual((it["id"], it["auto"], it["pinned"], it["name"], it["count"]), (sid, False, True, "works before the patch", 1))

    def test_pin_and_rename(self):
        self.apply(A_OLD)
        sid = self.app.list_snapshots()["items"][0]["id"]
        self.assertEqual(self.app.pin_snapshot(sid, True, "good one"), {"ok": True, "pinned": True, "name": "good one"})
        self.assertEqual(self.app.pin_snapshot(sid, False, "")["name"], None)
        with self.assertRaises(ApiError):
            self.app.pin_snapshot("20200101-000000-0000", True)

    def test_the_cap_is_200(self):
        self.assertEqual(snapmod.MAX_AUTO, 200)

    def test_old_automatic_ones_move_aside_never_vanish_and_pinned_stay(self):
        keep = snapmod.MAX_AUTO
        snapmod.MAX_AUTO = 2
        try:
            ids = []
            for i in range(4):
                ids.append(self.app.snapshots.save([], f"P{i}", auto=True))
                time.sleep(0.01)
                if i == 0:
                    self.app.snapshots.pin(ids[0], True)            # the oldest is pinned
            left = [d["id"] for d in self.app.snapshots.all()]
            self.assertEqual(sorted(left), sorted([ids[0]] + ids[2:]))                # pinned + newest two
            self.assertTrue((self.cfg.snapshots_dir / "old" / f"{ids[1]}.json").exists())   # moved, not erased
        finally:
            snapmod.MAX_AUTO = keep


class HttpTest(Base):
    def setUp(self):
        super().setUp()
        box = {"port": 0}
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), None)
        box["port"] = self.httpd.server_address[1]
        self.httpd.RequestHandlerClass = make_handler(self.app, box)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{box['port']}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        super().tearDown()

    def call(self, method, path, body=None):
        req = urllib.request.Request(self.base + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_routes(self):
        self.apply(A_OLD, B)
        code, lst = self.call("GET", "/api/snapshots")
        self.assertEqual(code, 200)
        sid = lst["items"][0]["id"]
        code, one = self.call("GET", f"/api/snapshots/{sid}")
        self.assertEqual((code, [m["status"] for m in one["mods"]]), (200, ["same", "same"]))
        self.assertEqual(self.call("GET", "/api/snapshots/20200101-000000-0000")[0], 404)
        self.assertEqual(self.call("POST", "/api/snapshots/pin", {"id": sid, "pinned": True, "name": "x"})[1]["name"], "x")
        code, made = self.call("POST", "/api/snapshots/save", {"name": "by hand"})
        self.assertEqual((code, made["ok"]), (200, True))
        self.call("POST", "/api/toggle", {"id": A_OLD, "enabled": False})
        code, st = self.call("POST", "/api/snapshots/restore", {"id": sid})
        self.assertEqual((code, st["restored"]["count"]), (200, 2))
        self.assertTrue(all(m["enabled"] for m in st["mods"] if m["id"] in (A_OLD, B)))


if __name__ == "__main__":
    unittest.main()

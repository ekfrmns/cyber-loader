"""Save transfer: what the engine allows and keeps safe around the optional add-on. The add-on itself is replaced by a small
fake that answers the same way, so these tests need no .NET and no real saves. Everything is in a throwaway folder."""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modman.app import ApiError, App
from modman.config import Config
from modman.savetransfer import SaveTransfer
from modman.server import route

FAKE = r'''
import json, os, sys
a = sys.argv[1:]
mode = os.environ.get("FAKE_MODE", "ok")
if os.environ.get("FAKE_LOG"):
    open(os.environ["FAKE_LOG"], "a").write(" ".join(a[:2]) + "\n")
def opt(n):
    return a[a.index(n) + 1] if n in a else None
if mode == "crash":
    sys.stderr.write("boom\n"); sys.exit(3)
if mode == "refuse":
    print(json.dumps({"ok": False, "error": "Body gender could not be changed"})); sys.exit(1)
if a[0] == "inspect":
    print(json.dumps({"ok": True, "bodyGender": "Female", "voice": "Female", "counts": {"clothes": 41, "modItems": 26, "guns": 15, "outfits": 4}}))
elif a[0] == "transfer":
    report = {"clothesAdded": 49} if "--clothes" in a else {}
    if "--money" in a:
        report["moneyBefore"] = 49066
        report["moneyAfter"] = int(opt("--money"))
    if "--strip-mods" in a:
        report["modItemsRemoved"] = 45
        report["modItemKinds"] = 38
        report["modSlotsUnequipped"] = 0
        report["outfitsCleared"] = 8
    if "--tidy" in a:
        report["tidyRemoved"] = 72
        report["tidyKinds"] = {"V's street outfit": 72}
    if "--dry-run" in a:
        print(json.dumps({"ok": True, "dryRun": True, "report": report}))
    else:
        out = opt("--out")
        os.makedirs(out, exist_ok=True)
        open(os.path.join(out, "sav.dat"), "wb").write(b"NEW" * 1000 + open(os.path.join(opt("--target"), "sav.dat"), "rb").read())
        open(os.path.join(out, "metadata.9.json"), "w").write(open(os.path.join(opt("--target"), "metadata.9.json")).read())
        open(os.path.join(out, "screenshot.png"), "wb").write(open(os.path.join(opt("--target"), "screenshot.png"), "rb").read())
        if mode == "tiny":
            open(os.path.join(out, "sav.dat"), "wb").write(b"x")
        print("some log line")
        print(json.dumps({"ok": True, "report": report, "result": {"bodyGender": "Female", "voice": "Female", "counts": {}}}))
'''


def meta(body="Female", voice="Female", level=15, hours=2.0, playthrough="abc", modded=True):
    return json.dumps({"Data": {"metadata": {"bodyGender": body, "brainGender": voice, "level": float(level),
                                              "playTime": hours * 3600, "playthroughID": playthrough, "isModded": modded,
                                              "lifePath": "StreetKid", "buildPatch": "2.5"}}})


def tree(root: Path) -> dict:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "<dir>"
            for p in sorted(root.rglob("*"))}


class SaveTransferTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="modman-st-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.saved_env = {k: os.environ.pop(k, None) for k in ("MODMAN_DATA", "MODMAN_GAME", "CYBERLOADER_CONFIG", "MODMAN_SAVES", "FAKE_MODE")}
        self.addCleanup(lambda: [os.environ.__setitem__(k, v) if v is not None else os.environ.pop(k, None) for k, v in self.saved_env.items()])
        self.saves = self.tmp / "saves"
        self.saves.mkdir()
        os.environ["MODMAN_SAVES"] = str(self.saves)
        self.cfg = Config(game=self.tmp / "game", data=self.tmp / "data", ui=self.tmp / "ui")
        self.cfg.ensure()
        self.app = App(self.cfg)
        self.fake = self.tmp / "fake_savetool.py"
        self.fake.write_text(FAKE, encoding="utf-8")
        self.use_fake()
        p = mock.patch("modman.savetransfer.game_running", return_value=False)
        self.game = p.start()
        self.addCleanup(p.stop)
        self.slot("ManualSave-3", body="Male", voice="Male", level=15, hours=8.0, playthrough="old", modded=False)
        self.slot("ManualSave-8")

    def use_fake(self):
        self.app.savetransfer = SaveTransfer(self.cfg, helper_cmd=[sys.executable, str(self.fake)])

    def slot(self, name, **kw):
        d = self.saves / name
        d.mkdir()
        (d / "sav.dat").write_bytes(("save of " + name).encode() * 200)
        (d / "metadata.9.json").write_text(meta(**kw), encoding="utf-8")
        (d / "screenshot.png").write_bytes(b"png")
        return d

    def body(self, **kw):
        b = {"source": "ManualSave-8", "target": "ManualSave-3", "clothes": True}
        b.update(kw)
        return b

    # ------------------------------------------------------------ the add-on is optional
    def test_not_available_without_the_addon(self):
        self.app.savetransfer = SaveTransfer(self.cfg)      # nothing installed under data\addons
        v = self.app.savetransfer_view()
        self.assertFalse(v["available"])
        self.assertIn("not installed", v["reason"])
        self.assertEqual(v["saves"], [])
        with self.assertRaises(ApiError) as cm:
            self.app.savetransfer_call("run", self.body())
        self.assertEqual(cm.exception.code, 409)

    def test_available_when_the_addon_files_exist(self):
        d = self.cfg.addons_dir / "savetool"
        (d / "editor").mkdir(parents=True)
        (d / "editor" / "CP2077SaveEditor.dll").write_bytes(b"x")
        (d / "savetool.exe").write_bytes(b"x")
        self.app.savetransfer = SaveTransfer(self.cfg)
        ok, why = self.app.savetransfer.available()
        self.assertTrue(ok, why)

    # ------------------------------------------------------------ listing and inspecting
    def test_lists_saves_with_their_details_newest_first(self):
        os.utime(self.saves / "ManualSave-3" / "sav.dat", (1_000_000, 1_000_000))
        os.utime(self.saves / "ManualSave-8" / "sav.dat", (2_000_000, 2_000_000))
        (self.saves / "not-a-save").mkdir()        # no sav.dat: ignored
        v = route(self.app, "GET", "/api/savetransfer", {})
        self.assertTrue(v["available"])
        self.assertEqual([s["id"] for s in v["saves"]], ["ManualSave-8", "ManualSave-3"])
        s3 = v["saves"][1]
        self.assertEqual((s3["bodyGender"], s3["voice"], s3["level"], s3["hours"], s3["playthrough"], s3["modded"], s3["hasPicture"]),
                         ("Male", "Male", 15, 8.0, "old", False, True))

    def test_broken_metadata_still_lists_the_save(self):
        d = self.slot("ManualSave-9")
        (d / "metadata.9.json").write_text("{not json", encoding="utf-8")
        ids = {s["id"]: s for s in self.app.savetransfer_view()["saves"]}
        self.assertIn("ManualSave-9", ids)
        self.assertIsNone(ids["ManualSave-9"]["bodyGender"])

    def test_inspect_asks_the_addon(self):
        r = route(self.app, "POST", "/api/savetransfer/inspect", {"save": "ManualSave-8"})
        self.assertEqual(r["counts"]["outfits"], 4)
        self.assertEqual(r["bodyGender"], "Female")

    def test_inspect_is_remembered_until_the_save_changes(self):
        log = self.tmp / "calls.log"
        os.environ["FAKE_LOG"] = str(log)
        self.addCleanup(os.environ.pop, "FAKE_LOG", None)
        calls = lambda: log.read_text().splitlines() if log.exists() else []
        a = self.app.savetransfer_call("inspect", {"save": "ManualSave-8"})
        b = self.app.savetransfer_call("inspect", {"save": "ManualSave-8"})
        self.assertEqual(a, b)
        self.assertEqual(len(calls()), 1)                               # the second look did not start the add-on
        self.app.savetransfer_call("inspect", {"save": "ManualSave-3"})
        self.assertEqual(len(calls()), 2)                               # a different save is asked
        (self.saves / "ManualSave-8" / "sav.dat").write_bytes(b"changed" * 300)
        self.app.savetransfer_call("inspect", {"save": "ManualSave-8"})
        self.assertEqual(len(calls()), 3)                               # the save changed, so ask again

    def test_a_failed_inspect_is_not_remembered(self):
        log = self.tmp / "calls2.log"
        os.environ["FAKE_LOG"] = str(log)
        self.addCleanup(os.environ.pop, "FAKE_LOG", None)
        os.environ["FAKE_MODE"] = "crash"
        with self.assertRaises(ApiError):
            self.app.savetransfer_call("inspect", {"save": "ManualSave-8"})
        os.environ["FAKE_MODE"] = "ok"
        self.assertEqual(self.app.savetransfer_call("inspect", {"save": "ManualSave-8"})["bodyGender"], "Female")

    # ------------------------------------------------------------ what is refused before anything runs
    def test_bad_requests_are_refused_with_plain_messages(self):
        cases = [
            (self.body(clothes=False), 400, "at least one"),
            (self.body(gender="banana"), 400, "gender"),
            (self.body(target="ManualSave-8"), 400, "different"),
            (self.body(source="..\\..\\Windows"), 400, "Pick a save"),
            (self.body(source="../x"), 400, "Pick a save"),
            (self.body(target="ManualSave-77"), 404, "Can’t find"),
            (self.body(source=None), 400, "Pick a save"),
        ]
        for body, code, text in cases:
            for what in ("preview", "run"):
                with self.subTest(body=body, what=what):
                    with self.assertRaises(ApiError) as cm:
                        self.app.savetransfer_call(what, body)
                    self.assertEqual(cm.exception.code, code)
                    self.assertIn(text, cm.exception.message)
        self.assertEqual(sorted(p.name for p in self.saves.iterdir()), ["ManualSave-3", "ManualSave-8"])
        self.assertFalse(self.cfg.save_backups_dir.exists())

    def test_gender_alone_counts_as_something_to_transfer(self):
        r = self.app.savetransfer_call("preview", {"source": "ManualSave-8", "target": "ManualSave-3", "gender": "female"})
        self.assertTrue(r["ok"])

    # ------------------------------------------------------------ a gender change alone needs no source save
    def test_gender_alone_needs_no_source_save(self):
        before = tree(self.saves)
        body = {"target": "ManualSave-8", "gender": "male"}
        self.assertTrue(self.app.savetransfer_call("preview", body)["ok"])
        self.assertEqual(tree(self.saves), before)
        r = self.app.savetransfer_call("run", body)
        self.assertEqual((r["source"], r["target"]), (None, "ManualSave-8"))
        after = tree(self.saves)
        self.assertEqual({k: v for k, v in after.items() if not k.startswith(r["slot"])}, before)
        self.assertEqual(sorted(p.name for p in Path(r["backup"]).iterdir()), ["ManualSave-8"])     # only the save involved

    def test_a_stray_source_is_ignored_for_a_gender_change(self):
        r = self.app.savetransfer_call("run", {"source": "no-such-save", "target": "ManualSave-8", "gender": "female"})
        self.assertEqual(r["source"], None)

    def test_copying_anything_still_needs_a_source(self):
        for what in ("preview", "run"):
            for key in ("look", "clothes", "outfits", "guns"):
                with self.subTest(what=what, key=key):
                    with self.assertRaises(ApiError) as cm:
                        self.app.savetransfer_call(what, {"target": "ManualSave-8", key: True, "gender": "male"})
                    self.assertEqual(cm.exception.code, 400)
                    self.assertIn("Pick a save", cm.exception.message)
        self.assertEqual(len(list(self.saves.iterdir())), 2)

    def test_gender_alone_still_needs_a_real_target(self):
        with self.assertRaises(ApiError) as cm:
            self.app.savetransfer_call("run", {"target": "ManualSave-77", "gender": "male"})
        self.assertEqual(cm.exception.code, 404)

    # ------------------------------------------------------------ tidy up (remove piles of identical clothes)
    def test_tidy_alone_needs_no_source_and_runs_like_any_other_transfer(self):
        before = tree(self.saves)
        body = {"target": "ManualSave-8", "tidy": True}
        r = self.app.savetransfer_call("preview", body)
        self.assertEqual(r["report"]["tidyRemoved"], 72)
        self.assertEqual(tree(self.saves), before)                    # a preview changes nothing
        r = self.app.savetransfer_call("run", body)
        self.assertEqual((r["source"], r["target"]), (None, "ManualSave-8"))
        self.assertEqual(r["report"]["tidyRemoved"], 72)
        after = tree(self.saves)
        self.assertEqual({k: v for k, v in after.items() if not k.startswith(r["slot"])}, before)    # the original is untouched
        self.assertEqual(sorted(p.name for p in Path(r["backup"]).iterdir()), ["ManualSave-8"])      # and was backed up

    def test_tidy_counts_as_something_to_do(self):
        with self.assertRaises(ApiError) as cm:
            self.app.savetransfer_call("run", {"source": "ManualSave-8", "target": "ManualSave-3"})
        self.assertIn("at least one", cm.exception.message)
        self.assertTrue(self.app.savetransfer_call("preview", {"source": "ManualSave-8", "target": "ManualSave-3", "tidy": True})["ok"])

    # ------------------------------------------------------------ remove mod items (a copy to play without mods)
    def test_strip_mods_alone_needs_no_source_and_makes_a_new_slot(self):
        before = tree(self.saves)
        body = {"target": "ManualSave-8", "stripMods": True}
        pv = self.app.savetransfer_call("preview", body)
        self.assertEqual((pv["report"]["modItemsRemoved"], pv["report"]["outfitsCleared"]), (45, 8))
        self.assertEqual(tree(self.saves), before)                         # a preview changes nothing
        r = self.app.savetransfer_call("run", body)
        self.assertEqual((r["source"], r["target"]), (None, "ManualSave-8"))
        after = tree(self.saves)
        self.assertEqual({k: v for k, v in after.items() if not k.startswith(r["slot"])}, before)       # the original is untouched
        self.assertEqual(sorted(p.name for p in Path(r["backup"]).iterdir()), ["ManualSave-8"])         # and was backed up

    def test_strip_mods_combines_with_gender_and_look(self):
        r = self.app.savetransfer_call("run", {"source": "ManualSave-3", "target": "ManualSave-8", "gender": "male", "look": True, "stripMods": True})
        self.assertEqual((r["source"], r["target"]), ("ManualSave-3", "ManualSave-8"))
        self.assertEqual(r["report"]["modItemsRemoved"], 45)

    def test_strip_mods_is_off_unless_asked(self):
        with self.assertRaises(ApiError) as cm:
            self.app.savetransfer_call("run", {"target": "ManualSave-8", "stripMods": False})
        self.assertIn("at least one", cm.exception.message)

    # ------------------------------------------------------------ set the money to an exact amount
    def test_money_alone_needs_no_source_and_makes_a_new_slot(self):
        before = tree(self.saves)
        body = {"target": "ManualSave-8", "money": 25000}
        pv = self.app.savetransfer_call("preview", body)
        self.assertEqual((pv["report"]["moneyBefore"], pv["report"]["moneyAfter"]), (49066, 25000))
        self.assertEqual(tree(self.saves), before)                         # a preview changes nothing
        r = self.app.savetransfer_call("run", body)
        self.assertEqual((r["source"], r["target"], r["report"]["moneyAfter"]), (None, "ManualSave-8", 25000))
        after = tree(self.saves)
        self.assertEqual({k: v for k, v in after.items() if not k.startswith(r["slot"])}, before)       # the original is untouched

    def test_money_accepts_zero_and_typed_commas_as_text(self):
        self.assertEqual(self.app.savetransfer_call("preview", {"target": "ManualSave-8", "money": 0})["report"]["moneyAfter"], 0)
        self.assertEqual(self.app.savetransfer_call("preview", {"target": "ManualSave-8", "money": "25,000"})["report"]["moneyAfter"], 25000)

    def test_a_silly_money_value_is_refused_before_anything_runs(self):
        for bad in (-1, "abc", "12.5", 2_000_000_001, "1e9"):
            for what in ("preview", "run"):
                with self.subTest(bad=bad, what=what):
                    with self.assertRaises(ApiError) as cm:
                        self.app.savetransfer_call(what, {"target": "ManualSave-8", "money": bad})
                    self.assertEqual(cm.exception.code, 400)
                    self.assertIn("Money", cm.exception.message)
        self.assertEqual(len(list(self.saves.iterdir())), 2)
        self.assertFalse(self.cfg.save_backups_dir.exists())

    def test_empty_money_means_keep_it(self):
        with self.assertRaises(ApiError) as cm:
            self.app.savetransfer_call("run", {"target": "ManualSave-8", "money": ""})
        self.assertIn("at least one", cm.exception.message)

    # ------------------------------------------------------------ playthroughs
    def test_saves_have_a_readable_label_and_kind(self):
        self.slot("AutoSave-2")
        self.slot("QuickSave-0")
        self.slot("Weird Name")
        by = {x["id"]: x for x in self.app.savetransfer_view()["saves"]}
        self.assertEqual((by["ManualSave-3"]["kind"], by["ManualSave-3"]["label"]), ("manual", "Manual save 3"))
        self.assertEqual((by["AutoSave-2"]["kind"], by["AutoSave-2"]["label"]), ("auto", "Autosave 2"))
        self.assertEqual((by["QuickSave-0"]["kind"], by["QuickSave-0"]["label"]), ("quick", "Quicksave 0"))
        self.assertEqual((by["Weird Name"]["kind"], by["Weird Name"]["label"]), ("other", "Weird Name"))

    def test_saves_are_grouped_by_playthrough_most_recent_first(self):
        self.slot("ManualSave-4", body="Male", playthrough="old", hours=9.0, level=16)
        self.slot("AutoSave-1", playthrough="abc", hours=3.0)
        for n, t in (("ManualSave-3", 1000), ("ManualSave-4", 3000), ("ManualSave-8", 2000), ("AutoSave-1", 5000)):
            os.utime(self.saves / n / "sav.dat", (t, t))
        v = route(self.app, "GET", "/api/savetransfer", {})
        self.assertEqual([g["id"] for g in v["playthroughs"]], ["abc", "old"])      # abc was played last (5000)
        abc, old = v["playthroughs"]
        self.assertEqual(abc["saves"], ["AutoSave-1", "ManualSave-8"])               # newest first
        self.assertEqual((abc["count"], abc["first"], abc["last"], abc["bodies"]), (2, 2000, 5000, ["Female"]))
        self.assertEqual(old["saves"], ["ManualSave-4", "ManualSave-3"])
        self.assertEqual((old["level"], old["hours"], old["bodies"]), (16, 9.0, ["Male"]))
        self.assertIsNone(old["name"])

    def test_a_playthrough_can_be_named_and_the_name_is_cleared_again(self):
        r = route(self.app, "POST", "/api/savetransfer/name", {"playthrough": "old", "name": "  My   story run  "})
        self.assertEqual(r["name"], "My story run")
        v = route(self.app, "GET", "/api/savetransfer", {})
        self.assertEqual({g["id"]: g["name"] for g in v["playthroughs"]}, {"old": "My story run", "abc": None})
        self.assertEqual(json.loads((self.cfg.data / "save-names.json").read_text(encoding="utf-8")), {"old": "My story run"})
        route(self.app, "POST", "/api/savetransfer/name", {"playthrough": "old", "name": ""})
        self.assertEqual(json.loads((self.cfg.data / "save-names.json").read_text(encoding="utf-8")), {})

    def test_naming_an_unknown_playthrough_is_refused_and_saves_are_untouched(self):
        before = tree(self.saves)
        with self.assertRaises(ApiError) as cm:
            self.app.savetransfer_call("name", {"playthrough": "nope", "name": "x"})
        self.assertEqual(cm.exception.code, 404)
        self.assertEqual(tree(self.saves), before)
        self.assertFalse((self.cfg.data / "save-names.json").exists())

    def test_naming_never_touches_the_saves(self):
        before = tree(self.saves)
        self.app.savetransfer_call("name", {"playthrough": "abc", "name": "Free roam"})
        self.assertEqual(tree(self.saves), before)

    def test_a_long_name_is_cut_and_a_damaged_names_file_is_ignored(self):
        r = self.app.savetransfer_call("name", {"playthrough": "abc", "name": "x" * 200})
        self.assertEqual(len(r["name"]), 60)
        (self.cfg.data / "save-names.json").write_text("{not json", encoding="utf-8")
        v = self.app.savetransfer_view()
        self.assertTrue(all(g["name"] is None for g in v["playthroughs"]))

    def test_the_new_save_stays_in_the_targets_playthrough(self):
        r = self.app.savetransfer_call("run", self.body())
        self.assertEqual(r["playthrough"], "old")       # ManualSave-3 is the target
        g = {x["id"]: x for x in self.app.savetransfer_view()["playthroughs"]}
        self.assertIn(r["slot"], g["old"]["saves"])
        self.assertNotIn(r["slot"], g["abc"]["saves"])


    # ------------------------------------------------------------ preview changes nothing
    def test_preview_changes_nothing(self):
        before = tree(self.saves)
        r = route(self.app, "POST", "/api/savetransfer/preview", self.body())
        self.assertEqual(r["report"], {"clothesAdded": 49})
        self.assertEqual(tree(self.saves), before)
        self.assertFalse(self.cfg.save_backups_dir.exists())

    # ------------------------------------------------------------ the real thing
    def test_run_makes_a_new_slot_and_leaves_every_existing_save_alone(self):
        before = tree(self.saves)
        r = route(self.app, "POST", "/api/savetransfer/run", self.body())
        self.assertEqual(r["slot"], "ManualSave-9")
        after = tree(self.saves)
        self.assertEqual({k: v for k, v in after.items() if not k.startswith("ManualSave-9")}, before)    # nothing old changed
        new = self.saves / "ManualSave-9"
        self.assertTrue((new / "sav.dat").read_bytes().startswith(b"NEW"))
        self.assertTrue((new / "metadata.9.json").is_file() and (new / "screenshot.png").is_file())
        self.assertEqual(r["report"], {"clothesAdded": 49})
        # both saves involved were backed up first, byte for byte
        backup = Path(r["backup"])
        for n in ("ManualSave-3", "ManualSave-8"):
            self.assertEqual(tree(backup / n), tree(self.saves / n))
        # no work folders left behind
        self.assertEqual([p for p in self.cfg.tmp_dir.glob("transfer-*")], [])

    def test_new_slot_number_is_one_above_the_highest_not_a_gap(self):
        self.slot("ManualSave-30")
        self.assertEqual(self.app.savetransfer_call("run", self.body())["slot"], "ManualSave-31")
        self.assertEqual(self.app.savetransfer_call("run", self.body())["slot"], "ManualSave-32")

    def test_run_refuses_while_the_game_runs(self):
        self.game.return_value = True
        before = tree(self.saves)
        with self.assertRaises(ApiError) as cm:
            self.app.savetransfer_call("run", self.body())
        self.assertEqual(cm.exception.code, 409)
        self.assertIn("game is running", cm.exception.message)
        self.assertEqual(tree(self.saves), before)
        self.assertFalse(self.cfg.save_backups_dir.exists())

    def test_run_refuses_while_an_apply_runs(self):
        self.app.job["state"] = "running"
        with self.assertRaises(ApiError) as cm:
            self.app.savetransfer_call("run", self.body())
        self.assertEqual(cm.exception.code, 423)
        self.assertEqual(len(list(self.saves.iterdir())), 2)

    def test_when_the_addon_says_no_nothing_is_added(self):
        os.environ["FAKE_MODE"] = "refuse"
        before = tree(self.saves)
        with self.assertRaises(ApiError) as cm:
            self.app.savetransfer_call("run", self.body())
        self.assertIn("Body gender could not be changed", cm.exception.message)
        self.assertEqual(tree(self.saves), before)
        self.assertEqual([p for p in self.cfg.tmp_dir.glob("transfer-*")], [])

    def test_when_the_addon_crashes_nothing_is_added_and_the_message_is_plain(self):
        os.environ["FAKE_MODE"] = "crash"
        before = tree(self.saves)
        with self.assertRaises(ApiError) as cm:
            self.app.savetransfer_call("run", self.body())
        self.assertEqual(cm.exception.code, 500)
        self.assertIn("Nothing was changed", cm.exception.message)
        self.assertEqual(tree(self.saves), before)

    def test_a_tiny_output_file_is_rejected(self):
        os.environ["FAKE_MODE"] = "tiny"
        before = tree(self.saves)
        with self.assertRaises(ApiError) as cm:
            self.app.savetransfer_call("run", self.body())
        self.assertIn("did not produce a save", cm.exception.message)
        self.assertEqual(tree(self.saves), before)

    def test_an_existing_slot_is_never_reused(self):
        # a folder appears with the number the engine picked, between choosing and creating it
        real = SaveTransfer._next_slot
        self.slot("ManualSave-9")
        with mock.patch.object(SaveTransfer, "_next_slot", lambda s: "ManualSave-9"):
            before = tree(self.saves)
            with self.assertRaises(FileExistsError):
                self.app.savetransfer.run(self.body())
            self.assertEqual(tree(self.saves), before)
        self.assertEqual(real(self.app.savetransfer), "ManualSave-10")


if __name__ == "__main__":
    unittest.main()

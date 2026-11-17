import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modman.config import Config
from modman.deploy import State, apply_plan, make_plan
from modman.library import Library, clean_name, guess_group
from modman.util import key


def write(p: Path, text="x"):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


class Base(unittest.TestCase):
    link_min = 1 << 20

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="modman-test-"))
        self.game = self.tmp / "game"
        self.data = self.tmp / "data"
        write(self.game / "bin" / "x64" / "Cyberpunk2077.exe", "exe")  # vanilla file
        write(self.game / "archive" / "pc" / "content" / "vanilla.archive", "v")
        self.cfg = Config(game=self.game, data=self.data, ui=self.tmp / "ui", link_min_bytes=self.link_min)
        self.cfg.ensure()
        L = self.cfg.library
        write(L / "A" / "archive" / "pc" / "mod" / "a.archive", "AAAA")
        write(L / "A" / "r6" / "scripts" / "A" / "a.reds", "reds-a")
        write(L / "B" / "archive" / "pc" / "mod" / "b.archive", "BBBB")
        write(L / "B" / "r6" / "scripts" / "shared.reds", "from-B")
        write(L / "C" / "r6" / "scripts" / "shared.reds", "from-C")
        self.lib = Library(L)
        self.lib.scan()
        self.state = State(self.cfg.state_dir / "deployed.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_apply(self, ids):
        plan = make_plan(self.cfg, self.lib, ids, self.state)
        res = apply_plan(self.cfg, plan, self.state)
        self.assertEqual(res["errors"], [])
        return plan

    def exists(self, rel):
        return (self.game / rel).exists()


class DeployCopy(Base):
    def test_add_then_idempotent_then_remove(self):
        p = self.run_apply(["A", "B"])
        self.assertEqual(len(p.adds), 4)
        self.assertTrue(self.exists(r"archive\pc\mod\a.archive"))
        self.assertTrue(self.exists(r"r6\scripts\A\a.reds"))
        p2 = make_plan(self.cfg, self.lib, ["A", "B"], self.state)
        self.assertEqual((len(p2.adds), len(p2.removes), p2.keeps), (0, 0, 4))
        self.run_apply([])
        self.assertFalse(self.exists(r"archive\pc\mod\a.archive"))
        self.assertFalse(self.exists(r"archive\pc\mod"), "directory we created should be pruned")
        self.assertFalse(self.exists("r6"), "directories we created should be pruned")
        self.assertTrue(self.exists(r"archive\pc\content\vanilla.archive"), "vanilla files untouched")
        self.assertTrue(self.exists(r"bin\x64\Cyberpunk2077.exe"))

    def test_later_mod_wins_conflict(self):
        p = self.run_apply(["B", "C"])
        self.assertEqual(len(p.conflicts), 1)
        self.assertEqual(p.conflicts[0]["winner"], "C")
        self.assertEqual((self.game / "r6" / "scripts" / "shared.reds").read_text(), "from-C")
        self.run_apply(["C", "B"])  # swap order: B now wins
        self.assertEqual((self.game / "r6" / "scripts" / "shared.reds").read_text(), "from-B")

    def test_foreign_file_blocks_and_is_never_overwritten(self):
        write(self.game / "archive" / "pc" / "mod" / "a.archive", "someone else's file")
        plan = make_plan(self.cfg, self.lib, ["A"], self.state)
        self.assertEqual(len(plan.blocked), 1)
        self.assertIn("not from this manager", plan.blocked[0]["reason"])
        self.assertEqual((self.game / "archive" / "pc" / "mod" / "a.archive").read_text(), "someone else's file")

    def test_identical_existing_file_is_adopted(self):
        write(self.game / "archive" / "pc" / "mod" / "a.archive", "AAAA")
        plan = make_plan(self.cfg, self.lib, ["A"], self.state)
        self.assertEqual((len(plan.blocked), len(plan.adopts)), (0, 1))
        apply_plan(self.cfg, plan, self.state)
        self.run_apply([])
        self.assertFalse(self.exists(r"archive\pc\mod\a.archive"))

    def test_user_modified_file_is_left_and_kept_on_return(self):
        self.run_apply(["A"])
        f = self.game / "r6" / "scripts" / "A" / "a.reds"
        f.write_text("user edit that is longer")
        plan = make_plan(self.cfg, self.lib, [], self.state)
        self.assertEqual(len(plan.left), 1)
        apply_plan(self.cfg, plan, self.state)
        self.assertTrue(f.exists(), "modified file must not be deleted")
        self.assertEqual(f.read_text(), "user edit that is longer")
        self.assertFalse(self.exists(r"archive\pc\mod\a.archive"), "untouched files are still removed")
        self.assertIn(key(r"r6\scripts\A\a.reds"), self.state.left)
        p = self.run_apply(["A"])  # turning it back on keeps the user's version instead of blocking
        self.assertEqual(f.read_text(), "user edit that is longer")
        self.assertEqual(len(p.blocked), 0)

    def test_regenerated_file_is_moved_aside_not_left_or_deleted(self):
        write(self.cfg.library / "G" / "r6" / "cache" / "inputContexts.xml", "orig")
        self.lib.scan()
        self.run_apply(["G"])
        f = self.game / "r6" / "cache" / "inputContexts.xml"
        f.write_text("regenerated at launch, longer")
        plan = make_plan(self.cfg, self.lib, [], self.state)
        self.assertEqual(plan.left, [])
        apply_plan(self.cfg, plan, self.state)
        self.assertFalse(f.exists())
        kept = list((self.cfg.state_dir / "moved-aside").rglob("inputContexts.xml"))
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].read_text(), "regenerated at launch, longer")

    def test_missing_file_is_restored(self):
        self.run_apply(["A"])
        os.remove(self.game / "archive" / "pc" / "mod" / "a.archive")
        p = make_plan(self.cfg, self.lib, ["A"], self.state)
        self.assertEqual(len(p.adds), 1)

    def test_state_survives_reload(self):
        self.run_apply(["A", "B"])
        reloaded = State(self.cfg.state_dir / "deployed.json")
        p = make_plan(self.cfg, self.lib, ["A", "B"], reloaded)
        self.assertEqual((len(p.adds), len(p.removes), p.keeps), (0, 0, 4))

    def test_switching_profiles_only_touches_difference(self):
        self.run_apply(["A", "B"])
        p = make_plan(self.cfg, self.lib, ["A"], self.state)
        self.assertEqual((len(p.adds), len(p.removes)), (0, 2))  # only B's two files go
        apply_plan(self.cfg, p, self.state)
        self.assertTrue(self.exists(r"archive\pc\mod\a.archive"))
        self.assertFalse(self.exists(r"archive\pc\mod\b.archive"))


class DeployLink(Base):
    link_min = 0  # force hardlinks

    def test_hardlinks_share_data_and_remove_only_the_link(self):
        self.run_apply(["A"])
        src = self.cfg.library / "A" / "archive" / "pc" / "mod" / "a.archive"
        dst = self.game / "archive" / "pc" / "mod" / "a.archive"
        self.assertEqual(os.stat(src).st_ino, os.stat(dst).st_ino)
        self.run_apply([])
        self.assertFalse(dst.exists())
        self.assertTrue(src.exists(), "library copy must survive removal")

    def test_replaced_link_counts_as_modified(self):
        self.run_apply(["A"])
        dst = self.game / "archive" / "pc" / "mod" / "a.archive"
        os.remove(dst)
        dst.write_text("AAAA")  # same size, different file (e.g. a self-updating mod)
        plan = make_plan(self.cfg, self.lib, [], self.state)
        self.assertTrue(any("a.archive" in x["rel"] for x in plan.left))


class Names(unittest.TestCase):
    def test_clean_name(self):
        self.assertEqual(clean_name("ArchiveXL 4198 1.28.8 2026-11-13T09-01Z UQrhQSmgd"), "ArchiveXL")
        self.assertEqual(clean_name("NPC LoD Tweak (for PT)-19926-1-0-1740331462"), "NPC LoD Tweak (for PT)")
        self.assertEqual(clean_name("CET 1.38.1 - Game version 2.5 107 1.38.1 2026-10-26T01-28Z ozVyzbb0n"),
                         "CET 1.38.1 - Game version 2.5")
        self.assertEqual(clean_name("Codeware 0.2.1"), "Codeware 0.2.1")

    def test_groups(self):
        self.assertEqual(guess_group("Codeware"), "Framework")
        self.assertEqual(guess_group("Codeware 0.2.1"), "Framework")
        self.assertEqual(guess_group("Thigh High Boots Latex - Archive XL"), "Clothing")
        self.assertEqual(guess_group("Sample Character FOMOD"), "Characters")


if __name__ == "__main__":
    unittest.main()

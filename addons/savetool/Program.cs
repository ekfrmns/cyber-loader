// savetool: copy parts of a Cyberpunk 2077 character from one save to another, into a NEW save folder.
// Never writes to the input saves. Results are printed as one JSON line on stdout.
//
//   savetool inspect  <save dir or sav.dat>
//   savetool transfer [--source <save>] --target <save> --out <new folder>   (--source is only needed for look/clothes/outfits/guns)
//                     [--gender keep|female|male] [--look] [--clothes] [--outfits] [--guns] [--tidy] [--dry-run]
//
// Environment: CP2077_EDITOR_DIR = folder with the unzipped CP2077SaveEditor (its DLLs are loaded at run time).
using System.Reflection;
using System.Text.Json;
using System.Text.RegularExpressions;
using CP2077SaveEditor;
using CP2077SaveEditor.ModSupport;
using CP2077SaveEditor.Utils;
using WolvenKit.Common.Services;
using WolvenKit.Core.Compression;
using WolvenKit.RED4.Archive.Buffer;
using WolvenKit.RED4.CR2W.JSON;
using WolvenKit.RED4.Save;
using WolvenKit.RED4.Save.Classes;
using WolvenKit.RED4.Save.IO;
using WolvenKit.RED4.Types;
using static WolvenKit.RED4.Types.Enums;

static class P
{
    static string AppDir;
    static readonly System.Diagnostics.Stopwatch Clock = System.Diagnostics.Stopwatch.StartNew();
    static void Lap(string what)
    {
        if (Environment.GetEnvironmentVariable("SAVETOOL_TIMING") == "1")
            Console.Error.WriteLine($"[{Clock.Elapsed.TotalSeconds,6:F1} s] {what}");
    }
    static Dictionary<(ulong, uint, ushort), gameItemID> Map;

    static int Main(string[] args)
    {
        Lap("main");
        AppDir = Environment.GetEnvironmentVariable("CP2077_EDITOR_DIR");
        if (string.IsNullOrEmpty(AppDir)) return Fail("CP2077_EDITOR_DIR is not set");
        AppDomain.CurrentDomain.AssemblyResolve += (s, e) =>
        {
            var p = Path.Combine(AppDir, new AssemblyName(e.Name).Name + ".dll");
            return File.Exists(p) ? Assembly.LoadFrom(p) : null;
        };
        try { return Run(args); }
        catch (Exception ex) { return Fail(ex.Message); }
    }

    static int Fail(string msg)
    {
        Console.WriteLine(JsonSerializer.Serialize(new { ok = false, error = msg }));
        return 1;
    }

    static string SavFile(string path) => Directory.Exists(path) ? Path.Combine(path, "sav.dat") : path;

    static SaveFileHelper Load(string path)
    {
        var f = SavFile(path);
        if (!File.Exists(f)) throw new Exception("No sav.dat at " + path);
        using var fs = File.OpenRead(f);
        using var reader = new CyberpunkSaveReader(fs);
        Lap("reading " + Path.GetFileName(Path.GetDirectoryName(f)));
        var st = reader.ReadFile(out var save);
        if (st != EFileReadErrorCodes.NoError) throw new Exception("Could not read " + f + " (" + st + ")");
        Lap("read done");
        return new SaveFileHelper { SaveFile = save };
    }

    static string TypeOf(ItemData it) =>
        ResourceHelper.ItemClasses.TryGetValue(it.ItemInfo.ItemId.Id, out var r) ? r.Type : "Unknown";
    static bool IsClothes(ItemData it) { var t = TypeOf(it); return t == "Clothing" || t == "Unknown"; }
    static bool IsGun(ItemData it) { var t = TypeOf(it); return t == "Weapon" || t == "WeaponItem"; }

    static string Gender(SaveFileHelper h) => h.GetAppearanceContainer().Preset.IsMale ? "Male" : "Female";
    static string Voice(SaveFileHelper h) => h.GetAppearanceContainer().IsBrainGenderMale ? "Male" : "Female";

    static object Counts(SaveFileHelper h)
    {
        var items = h.GetInventory(1).Items;
        var outfits = h.GetScriptableSystem<OutfitSystem>()?.State?.Chunk?.Outfits;
        return new
        {
            clothes = items.Count(i => TypeOf(i) == "Clothing"),
            modItems = items.Count(i => TypeOf(i) == "Unknown"),
            guns = items.Count(IsGun),
            outfits = outfits?.Count ?? 0
        };
    }

    static int Run(string[] args)
    {
        Lap("start");
        CompressionSettings.Get().UseOodle = false;
        ModManager.LoadTypes();
        Lap("types loaded");
        Map = new Dictionary<(ulong, uint, ushort), gameItemID>();
        if (args.Length == 0) return Fail("usage: inspect <save> | transfer --source S --target T --out DIR [options]");

        if (args[0] == "inspect" && args.Length >= 2)
        {
            var h = Load(args[1]);
            Lap("loaded");
            Console.WriteLine(JsonSerializer.Serialize(new { ok = true, bodyGender = Gender(h), voice = Voice(h), counts = Counts(h) }));
            return 0;
        }
        if (args[0] == "transfer") return Transfer(args);
        return Fail("unknown command " + args[0]);
    }

    static string Opt(string[] a, string name, string def = null)
    {
        var i = Array.IndexOf(a, name);
        return i >= 0 && i + 1 < a.Length ? a[i + 1] : def;
    }

    static int Transfer(string[] a)
    {
        var srcPath = Opt(a, "--source"); var dstPath = Opt(a, "--target"); var outDir = Opt(a, "--out");
        var gender = (Opt(a, "--gender", "keep") ?? "keep").ToLowerInvariant();
        bool look = a.Contains("--look"), clothes = a.Contains("--clothes"), outfits = a.Contains("--outfits"),
             guns = a.Contains("--guns"), tidy = a.Contains("--tidy"), dry = a.Contains("--dry-run");
        if (dstPath == null) return Fail("--target is required");
        if (srcPath == null && (look || clothes || outfits || guns)) return Fail("--source is required to copy a look, clothes, outfits or guns");
        if (!dry && outDir == null) return Fail("--out is required");
        if (gender != "keep" && gender != "female" && gender != "male") return Fail("--gender must be keep, female or male");
        if (srcPath != null && Path.GetFullPath(SavFile(srcPath)).Equals(Path.GetFullPath(SavFile(dstPath)), StringComparison.OrdinalIgnoreCase))
            return Fail("Source and target are the same save");
        if (!dry && Directory.Exists(outDir) && Directory.EnumerateFileSystemEntries(outDir).Any())
            return Fail("Output folder must be new or empty: " + outDir);

        // Reading a save is the slow part (about 15 s each). It cannot be done twice at once: the reader shares
        // state and fails ("An item with the same key has already been added"), so the saves are read one after the other.
        var src = srcPath != null ? Load(srcPath) : null;
        var dst = Load(dstPath);
        Lap("saves loaded");
        var report = new Dictionary<string, object>();

        // 1) look (and the body gender that goes with it); the target's voice stays as it is
        if (look)
        {
            var voiceMale = dst.GetAppearanceContainer().IsBrainGenderMale;
            var json = RedJsonSerializer.Serialize(new PresetDto { Data = src.GetAppearanceContainer() });
            var vals = RedJsonSerializer.Deserialize<PresetDto>(json, new RedJsonSerializerOptions { JsonVersion = WolvenKit.Common.Constants.RedJsonVersion })?.Data;
            if (vals?.Preset == null) throw new Exception("The look could not be read from the source save");
            if ((bool)vals.Preset.IsMale != (bool)dst.GetAppearanceContainer().Preset.IsMale)
                SetBodyGender(dst, vals.Preset.IsMale);
            dst.SetAppearanceContainer(vals);
            dst.GetAppearanceContainer().IsBrainGenderMale = voiceMale;
            report["look"] = true;
        }
        // 2) gender (body + voice) when asked
        if (gender != "keep")
        {
            bool male = gender == "male";
            if (Gender(dst) != (male ? "Male" : "Female")) SetBodyGender(dst, male);
            dst.GetAppearanceContainer().IsBrainGenderMale = male;
            report["gender"] = gender;
        }

        var dstInv = dst.GetInventory(1);
        var srcInv = src?.GetInventory(1);

        // 3) items the target does not already have (by item type and count)
        int CopyItems(Func<ItemData, bool> pick)
        {
            var have = dstInv.Items.Where(pick).GroupBy(i => (ulong)i.ItemInfo.ItemId.Id).ToDictionary(g => g.Key, g => g.Count());
            var n = 0;
            foreach (var g in srcInv.Items.Where(pick).GroupBy(i => (ulong)i.ItemInfo.ItemId.Id).ToList())
            {
                var missing = g.Count() - (have.TryGetValue(g.Key, out var c) ? c : 0);
                foreach (var it in g.Take(Math.Max(0, missing)))
                {
                    if (!dry) dstInv.Items.Add(CloneAcross(src, dst, it));
                    n++;
                }
            }
            return n;
        }
        if (clothes) report["clothesAdded"] = CopyItems(IsClothes);
        if (guns) report["gunsAdded"] = CopyItems(IsGun);

        // 4) Equipment-EX outfits, re-pointed at the target's item copies
        if (outfits)
        {
            var ss = src.GetScriptableSystem<OutfitSystem>()?.State?.Chunk;
            var ds = dst.GetScriptableSystem<OutfitSystem>()?.State?.Chunk;
            int added = 0, skippedParts = 0, skippedSets = 0;
            if (ss?.Outfits != null && ds != null)
            {
                var names = (ds.Outfits ?? new CArray<CHandle<OutfitSet>>()).Select(o => o.Chunk.Name.ToString()).ToHashSet();
                var used = new HashSet<(ulong, uint, ushort)>();
                foreach (var o in ss.Outfits)
                {
                    var so = o.Chunk;
                    if (names.Contains(so.Name.ToString())) { skippedSets++; continue; }
                    if (dry) { added++; continue; }
                    ds.Outfits ??= new CArray<CHandle<OutfitSet>>();
                    var parts = new CArray<CHandle<OutfitPart>>();
                    foreach (var part in so.Parts)
                    {
                        var sid = part.Chunk.ItemID;
                        gameItemID nid = null;
                        if (Map.TryGetValue(((ulong)sid.Id, sid.RngSeed, sid.UniqueCounter), out var m)) nid = m;
                        else
                        {
                            var own = dstInv.Items.FirstOrDefault(i => (ulong)i.ItemInfo.ItemId.Id == (ulong)sid.Id
                                && !used.Contains(((ulong)i.ItemInfo.ItemId.Id, i.ItemInfo.ItemId.RngSeed, i.ItemInfo.ItemId.UniqueCounter)));
                            if (own != null) nid = own.ItemInfo.ItemId;
                        }
                        if (nid == null) { skippedParts++; continue; }
                        used.Add(((ulong)nid.Id, nid.RngSeed, nid.UniqueCounter));
                        parts.Add(new CHandle<OutfitPart>(new OutfitPart
                        {
                            ItemID = new gameItemID { Id = nid.Id, RngSeed = nid.RngSeed, UniqueCounter = nid.UniqueCounter, Flags = nid.Flags },
                            SlotID = part.Chunk.SlotID
                        }));
                    }
                    ds.Outfits.Add(new CHandle<OutfitSet>(new OutfitSet { Name = so.Name, Parts = parts, Timestamp = so.Timestamp }));
                    added++;
                }
            }
            report["outfitsAdded"] = added; report["outfitSetsSkipped"] = skippedSets; report["outfitPartsSkipped"] = skippedParts;
            if (ds == null)
                report["outfitsNote"] = "The target save has no Equipment-EX outfit data yet. Load it once in the game with your mods on, save, then transfer the outfits.";
            else if (ss?.Outfits == null)
                report["outfitsNote"] = "The source save has no Equipment-EX outfits.";
        }

        // 5) cut piles of identical clothes down to a few (never anything worn or used by an outfit)
        if (tidy)
        {
            var (removed, kinds) = Tidy(dst, dstInv, dry);
            report["tidyRemoved"] = removed;
            report["tidyKinds"] = kinds;
        }

        if (dry)
        {
            Console.WriteLine(JsonSerializer.Serialize(new { ok = true, dryRun = true, report }));
            return 0;
        }

        Lap("changes made");
        var data = dst.Serialize();
        Lap("serialized");
        SaveFileHelper back;
        using (var ms = new MemoryStream(data))
        using (var rd = new CyberpunkSaveReader(ms))
        {
            var st = rd.ReadFile(out var parsed);
            if (st != EFileReadErrorCodes.NoError) throw new Exception("The new save could not be read back (" + st + "); nothing was written");
            back = new SaveFileHelper { SaveFile = parsed };
        }
        Lap("read back ok");
        Directory.CreateDirectory(outDir);
        File.WriteAllBytes(Path.Combine(outDir, "sav.dat"), data);
        var dstDir = Directory.Exists(dstPath) ? dstPath : Path.GetDirectoryName(Path.GetFullPath(dstPath));
        var metaIn = Path.Combine(dstDir, "metadata.9.json");
        if (File.Exists(metaIn))
        {
            // keep the load menu honest about the character
            var meta = File.ReadAllText(metaIn);
            meta = Regex.Replace(meta, "(\"bodyGender\"\\s*:\\s*\")(Male|Female)(\")", "${1}" + Gender(back) + "${3}");
            meta = Regex.Replace(meta, "(\"brainGender\"\\s*:\\s*\")(Male|Female)(\")", "${1}" + Voice(back) + "${3}");
            File.WriteAllText(Path.Combine(outDir, "metadata.9.json"), meta, new System.Text.UTF8Encoding(false));
        }
        var shot = Path.Combine(dstDir, "screenshot.png");
        if (File.Exists(shot)) File.Copy(shot, Path.Combine(outDir, "screenshot.png"));

        Console.WriteLine(JsonSerializer.Serialize(new
        {
            ok = true,
            report,
            result = new { bodyGender = Gender(back), voice = Voice(back), counts = Counts(back) }
        }));
        return 0;
    }

    // Items of one kind (clothes and mod clothes) held more than `MinPile` times are cut down to `KeepEach`.
    // Kept first: anything equipped and anything an Equipment-EX outfit points at. Removing an item is what the editor does
    // too (it leaves the item's stats entry behind, which the game ignores).
    const int MinPile = 4, KeepEach = 2;
    static (int, Dictionary<string, int>) Tidy(SaveFileHelper h, SubInventory inv, bool dry)
    {
        (ulong, uint, ushort) Key(gameItemID i) => ((ulong)i.Id, i.RngSeed, i.UniqueCounter);
        var protectedIds = new HashSet<(ulong, uint, ushort)>();
        foreach (var kv in h.GetEquippedItems()) protectedIds.Add(Key(kv.Key));
        var eex = h.GetScriptableSystem<OutfitSystem>()?.State?.Chunk;
        if (eex?.Outfits != null)
            foreach (var o in eex.Outfits) if (o.Chunk.Parts != null) foreach (var p in o.Chunk.Parts) protectedIds.Add(Key(p.Chunk.ItemID));
        if (eex?.Parts != null) foreach (var p in eex.Parts) protectedIds.Add(Key(p.Chunk.ItemID));

        var removed = 0;
        var kinds = new Dictionary<string, int>();
        foreach (var g in inv.Items.Where(IsClothes).GroupBy(i => (ulong)i.ItemInfo.ItemId.Id).ToList())
        {
            var items = g.ToList();
            if (items.Count <= MinPile) continue;
            var keep = items.Where(i => protectedIds.Contains(Key(i.ItemInfo.ItemId))).ToList();
            foreach (var i in items.Where(i => !keep.Contains(i)).OrderBy(i => i.ItemInfo.ItemId.UniqueCounter))
                if (keep.Count < KeepEach) keep.Add(i);
            foreach (var i in items.Where(i => !keep.Contains(i)))
            {
                if (!dry) inv.Items.Remove(i);
                removed++;
            }
            var id = g.Key;
            var name = (ResourceHelper.DisplayNames.TryGetValue(id, out var dn) ? dn : null) ?? items[0].ItemInfo.ItemId.Id.ResolvedText ?? "(mod item)";
            kinds[name] = (kinds.TryGetValue(name, out var c) ? c : 0) + (items.Count - keep.Count);
        }
        return (removed, kinds);
    }

    static void SetBodyGender(SaveFileHelper h, bool male)
    {
        // The editor's own setter, so the default look for the new body is the one made for this patch.
        var puppet = h.GetPSDataContainer()?.Entries.FirstOrDefault(x => x.Data is PlayerPuppetPS)?.Data;
        if (puppet == null) throw new Exception("Player data not found in the save; body gender cannot be changed");
        h.Appearance.SuppressBodyGenderPrompt = true;
        h.Appearance.BodyGender = male ? AppearanceGender.Male : AppearanceGender.Female;
        if (Gender(h) != (male ? "Male" : "Female")) throw new Exception("Body gender could not be changed");
    }

    // ---- cross-save item cloning (port of SaveFileHelper.CloneItem / CloneStats, stats read from the SOURCE save) ----
    static ItemData CloneAcross(SaveFileHelper src, SaveFileHelper dst, ItemData s)
    {
        var newSeed = s.ItemInfo.ItemId.RngSeed == 2 ? 2u : dst.CreateUniqueSeed(dst.GetStatsContainer());
        var newId = new gameItemID { Id = s.ItemInfo.ItemId.Id, RngSeed = newSeed, UniqueCounter = dst.GetNextUniqueCounter(), Flags = s.ItemInfo.ItemId.Flags };
        var clone = new ItemData
        {
            ItemInfo = new ItemInfo { ItemId = newId, ItemStructure = s.ItemInfo.ItemStructure },
            Flags = s.Flags,
            CreationTime = s.CreationTime,
            Quantity = s.Quantity,
            ItemAdditionalInfo = CloneInfo(s.ItemAdditionalInfo),
            ItemSlotPart = CloneSlot(src, dst, s.ItemSlotPart)
        };
        CloneStatsAcross(src, dst, s.ItemInfo.ItemId, newId);
        Map[((ulong)s.ItemInfo.ItemId.Id, s.ItemInfo.ItemId.RngSeed, s.ItemInfo.ItemId.UniqueCounter)] = newId;
        return clone;
    }

    static ItemAdditionalInfo CloneInfo(ItemAdditionalInfo s) =>
        s == null ? null : new ItemAdditionalInfo { LootItemPoolId = s.LootItemPoolId, Unknown2 = s.Unknown2, RequiredLevel = s.RequiredLevel };

    static ItemSlotPart CloneSlot(SaveFileHelper src, SaveFileHelper dst, ItemSlotPart s)
    {
        if (s == null) return null;
        var seed = s.ItemInfo.ItemId.RngSeed == 0 ? 0u : (s.ItemInfo.ItemId.RngSeed == 2 ? 2u : dst.CreateUniqueSeed(dst.GetStatsContainer()));
        var counter = s.ItemInfo.ItemId.Id == 0 ? (ushort)0 : dst.GetNextUniqueCounter();
        var newId = new gameItemID { Id = s.ItemInfo.ItemId.Id, RngSeed = seed, UniqueCounter = counter, Flags = s.ItemInfo.ItemId.Flags };
        var part = new ItemSlotPart
        {
            ItemInfo = new ItemInfo { ItemId = newId, ItemStructure = s.ItemInfo.ItemStructure },
            AppearanceName = s.AppearanceName,
            AttachmentSlotTdbId = s.AttachmentSlotTdbId,
            Unknown2 = s.Unknown2,
            ItemAdditionalInfo = CloneInfo(s.ItemAdditionalInfo),
            Children = s.Children?.Select(c => CloneSlot(src, dst, c)).ToList() ?? new List<ItemSlotPart>()
        };
        if (s.ItemInfo.ItemId.Id != 0) CloneStatsAcross(src, dst, s.ItemInfo.ItemId, newId);
        return part;
    }

    static void CloneStatsAcross(SaveFileHelper src, SaveFileHelper dst, gameItemID sId, gameItemID tId)
    {
        var ss = src.GetStatsFromItemId(sId);
        if (ss == null) return;
        var c = (gameSavedStatsData)ss.DeepCopy();
        c.Seed = tId.RngSeed;
        if (ss.ModifiersBuffer?.Data is ModifiersBuffer m1)
            c.ModifiersBuffer = new DataBuffer { Data = new ModifiersBuffer { Entries = m1.Entries.Select(x => (gameStatModifierData_Deprecated)x.DeepCopy()).ToList() } };
        if (ss.ForcedModifiersBuffer?.Data is ModifiersBuffer m2)
            c.ForcedModifiersBuffer = new DataBuffer { Data = new ModifiersBuffer { Entries = m2.Entries.Select(x => (gameStatModifierData_Deprecated)x.DeepCopy()).ToList() } };
        if (ss.SavedModifierGroupStatTypesBuffer?.Data is SavedModifierGroupStatTypesBuffer g)
            c.SavedModifierGroupStatTypesBuffer = new DataBuffer { Data = new SavedModifierGroupStatTypesBuffer { Entries = g.Entries.Select(x => new SavedModifierGroupStatTypesBuffer_Entry { ModifierGroupHash = x.ModifierGroupHash, StatTypes = new List<gamedataStatType>(x.StatTypes) }).ToList() } };
        dst.AddStatData(new gameStatsObjectID { IdType = gameStatIDType.ItemID, EntityHash = InventoryHelper.GetItemIdHash(tId) }, c);
    }
}

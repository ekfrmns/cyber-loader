# Local API contract (engine <-> UI)

The engine serves `ui/` and this JSON API on `http://127.0.0.1:<port>` (same origin, no CORS).
The UI is built against this contract and a mock (`ui/mock.js`) until the engine is ready.
If the contract needs to change, the UI session writes the request to `docs/API-CHANGES.md`; the engine session applies it and updates this file.

## Types

    Mod = {
      id: string,                 // stable folder name in the library
      name: string,               // display name (cleaned)
      group: "Framework"|"Body"|"Characters"|"Clothing"|"Gameplay"|"Content"|"Other",
      files: number,              // files this mod would place in the game folder
      enabled: boolean,           // enabled in the selected profile (including staged changes)
      pending: "on"|"off"|null,   // differs from what is deployed in the game right now
      framework: boolean,         // core dependency (RED4ext, Codeware, ArchiveXL, ...)
      requires: string[],         // ids of mods this one needs (set by hand, `--requires` on import)
      autoRequires: { name: string, ids: string[] }[],  // frameworks the engine guessed from the mod's files (a .reds script
                                  // needs Redscript, an .xl file ArchiveXL, ...). ids = library mods that supply it, empty if
                                  // none is in the library. Met as soon as any of the ids is on. Also feeds `warnings`.
      conflicts: number,          // files this mod loses/wins against other enabled mods
      nexusId: number|null,       // Nexus mod number, read from the library folder name (null if it did not come from Nexus)
      version: string|null,       // its version as people write it ("2.0.1"; the older Nexus style "2-0-1" is shown with dots), if the folder name has one
      uploaded: string|null,      // upload date "YYYY-MM-DD", if the folder name has one
      otherVersions: string[]     // ids of other library mods that look like another version of this one: same Nexus number and the
                                  // same name apart from version words. Turning two of them on gives a warning in `warnings`.
    }

## Endpoints

    GET  /api/state
      -> { game: { running: boolean, found: boolean,
                   version?: string,           // the game's own version ("2.5"), read from its exe; missing if unreadable
                   updated?: string },         // date of the game exe ("YYYY-MM-DD"), i.e. its last update
           profile: string,
           profiles: string[],
           deployedCount: number,          // files currently placed in the game folder
           pendingCount: { on: number, off: number },
           profileDirty: boolean,              // staged mod set differs from the saved profile
           version: string,                    // engine/app version, e.g. "0.1.0"
           mods: Mod[] }

    POST /api/toggle            { id, enabled }          -> { ok, mod: Mod, warnings: string[] }
         Stages a change in memory only. Nothing on disk changes until /api/apply.

    POST /api/profile/select    { name }                 -> /api/state shape
    POST /api/profile/save      { name }                 -> { ok }
    POST /api/profile/new       { name, from? }          -> { ok }
    POST /api/profile/rename    { name, to }             -> { ok, profile: string, profiles: string[] }
         Renames a profile (keeps its mods, its place in the list and, if selected, the selection). 404 unknown, 409 name taken
         (case-insensitive), 400 empty name.
    POST /api/profile/delete    { name }                 -> { ok }

    POST /api/preview
      -> { add: number, remove: number,
           conflicts: [{ path, winner: id, losers: id[] }],
           warnings: string[],                            // e.g. "Codeware is off but Some Mod needs it"
           files: { add: [{ id, path }], remove: [{ id, path }] },   // path relative to the game folder; capped at 5000 each
           filesTruncated: boolean }

    POST /api/apply
      -> { ok: true }                                     // starts a job; refuses (409) if the game is running
    GET  /api/progress
      -> { state: "idle"|"running"|"done"|"error", percent: number, text: string }

    POST /api/import            { path }                 -> { ok, id, warnings: string[] }
         Path of a folder or archive on this computer (CLI / scripts). Unpacks into its own library folder; never runs anything.
         The library folder keeps the file's own name (since 1.4.0), so a Nexus download's number, version and date stay in it;
         a name clash adds " (2)" at the end.

    Import by upload (drag and drop: a web page cannot read the path of a dropped file)
    POST /api/import/begin      { name, kind: "archive"|"folder" }  -> { token }
    PUT  /api/import/file?token=<t>&path=<relative path, URL-encoded>   raw bytes -> { ok }
         archive: exactly one PUT, path = file name (.zip/.7z/.rar). folder: one PUT per file, path relative to the dropped folder.
         Rejects "..", absolute paths, drive letters and reserved characters (400). Limits: 8 GB, 50,000 files per import.
    POST /api/import/finish     { token }                -> { ok, id, warnings: string[] }   (token is single-use)

    POST /api/discard           -> /api/state shape       // staged set := what is deployed right now

    Deleting mods: an in-app trash. Nothing is erased until the trash is emptied. Profiles keep a deleted mod's entry,
    so restoring it puts it back into those profiles.
    POST /api/mod/delete        { id }                   -> { ok, trashId, name }   // 409 if the mod is in the game right now ("turn it off and apply first"), 404 unknown, 423 apply running
    POST /api/mod/requires      { id, requires: string[] } -> { ok, mod: Mod, warnings: string[] }
         Replaces the hand-made "needs" list of a mod (saved in that mod's `.mod.json`; nothing in the game folder changes).
         404 unknown mod, 400 if an id is unknown, the mod needs itself, or `requires` is not a list of strings. Duplicates are dropped.
         `warnings` are the unmet needs of this mod after the change, same text as /api/toggle.
    POST /api/mod/group         { id, group }            -> { ok, mod: Mod }
         Moves a mod to a category: "Framework"|"Body"|"Characters"|"Clothing"|"Gameplay"|"Content"|"Other". Saved in that mod's
         `.mod.json` (and the framework flag follows: only "Framework" is a core dependency), so the name-based guess never
         overrides it. 404 unknown mod, 400 unknown category.
    GET  /api/trash             -> { items: [{ id, name, group, files, size, deletedAt }], totalSize }   // newest first; id is the trash id
    POST /api/trash/restore     { id }                   -> { ok, id, name }        // back into the library; a name clash restores as "<name> (restored)"
    POST /api/trash/empty       { id? }                  -> { ok, removed, freed }  // one item, or the whole trash when id is omitted. Permanent.


    Setup history (snapshots). A snapshot remembers which mods were on (in order), the profile, and for each mod its name,
    file count, size and what its library folder name says about it (Nexus number, version, upload date). It holds no mod
    files. One is saved automatically after every successful apply (skipped when identical to the newest one). Saves by hand
    named ones are kept (the UI no longer offers naming: saving a named list is what profiles are for); automatic ones beyond the newest 200 move to `snapshots\old` (never erased). Stored in `<data>\snapshots`.
    GET  /api/snapshots         -> { items: [{ id, at, profile, auto, pinned, name|null, count,
                                               turnOn,   // mods in it that are off now (and still in the library)
                                               turnOff,  // mods that are on now but not in it
                                               missing,  // its mods no longer in the library
                                               changed   // its mods whose files changed since (file count or size differs)
                                             }] }                // newest first
    GET  /api/snapshots/<id>    -> { id, at, profile, auto, pinned, name, mods: [{ id, name, version|null, date|null, nexusId|null,
                                      on: boolean,              // on right now
                                      status: "same"|"changed"|"missing",
                                      inTrash?: boolean,        // missing and sitting in the in-app trash
                                      replacedBy?: { id, name, version, date } }] }   // missing, but the same Nexus number is in the library under another folder (the update)
         404 unknown id. `version` is as written in the folder name ("0.2.6", or "2-0-1" for the older style); null when the folder name has none.
         The Nexus page of a mod is https://www.nexusmods.com/cyberpunk2077/mods/<nexusId> (the app never contacts Nexus).
    POST /api/snapshots/save    { name? }                -> { ok, id }    // keeps the mods that are on right now (staged set), named and pinned
    POST /api/snapshots/pin     { id, pinned?, name? }   -> { ok, pinned, name }   // pinned/named ones are never moved aside; 404 unknown id
    POST /api/snapshots/restore { id }                   -> /api/state shape + { restored: { count, missing: [{ name, version, date, nexusId }], changed } }
         Stages that setup: the mod list becomes exactly the snapshot's (mods no longer in the library are skipped and listed in
         `missing`). Nothing in the game changes until the usual preview + apply. 404 unknown id, 423 while an apply runs.

    Game folder (since 1.5.0). The folder is set by Setup and saved as "game" in the install's `cyberloader.json`; these let the app change it.
    GET  /api/game-folder       -> { path: string|null,        // the folder in use; null if none was ever set
                                     found: boolean,           // it holds bin/x64/Cyberpunk2077.exe
                                     version?, updated?,       // as in /api/state `game`, when found
                                     deployedCount: number,    // files from mods currently placed in it
                                     canChange: boolean,
                                     reason: string|null }     // when !canChange: plain words why (shown as-is)
    POST /api/game-folder/check { path }                      -> { path,        // cleaned up: quotes removed; if the exe or its bin / bin/x64 folder was given, the game folder above it
                                                                   isFolder, found, same,   // same = it is the folder in use already
                                                                   message,     // plain words ("Cyberpunk 2077 found." or what is wrong)
                                                                   version?, updated? }
         Changes nothing. For live validation while typing or after the Browse dialog.
    POST /api/game-folder       { path }                      -> { ok, changed, ...same shape as GET }
         Validates like `check`, then saves the folder atomically into `cyberloader.json` (every other key is kept; a damaged file is never
         overwritten) and uses it at once, no restart. Nothing is copied, moved or deleted in either game folder; the only other thing
         that changes is that the engine's records of directories it created and of files it left behind (`state\deployed.json`
         `dirs` / `left`, which describe the OLD folder) are cleared. Choosing the folder already in use is a no-op (`changed: false`).
         Refused, leaving everything as it was: 400 not a Cyberpunk 2077 folder (message from `check`); 409 mods are still placed
         in the current folder ("Turn everything off and apply first, then change the folder": `state\deployed.json` records files
         relative to it), 409 the game is running, 409 the folder was given on the command line (`--game`, MODMAN_GAME) or there is
         no `cyberloader.json`, 423 an apply is running, 500 the settings file could not be saved.

    Save transfer (optional add-on, see docs/SAVE-TRANSFER.md). `/api/state` has `saveTransfer: boolean` = the add-on is installed
    (the UI only shows "Change or move a character…" when true).
    GET  /api/savetransfer      -> { available: boolean, reason: string|null,     // when !available: plain words why
                                     savesDir: string, gameRunning: boolean,
                                     playthroughs: [{ id,      // the game files saves under a playthrough id; most recently played first
                                                       name,        // a name the user gave it (see /name), or null
                                                       count, first, last,   // number of saves; unix seconds of the oldest and newest
                                                       bodies,      // e.g. ["Female","Male"]: the body genders found in its saves
                                                       level, hours,         // of its newest save / most hours seen; may be null
                                                       saves }],    // the ids of its saves, newest first
                                     saves: [{ id,            // the save's folder name, e.g. "ManualSave-8"; this is what the other calls take
                                               kind, label,         // "manual"|"auto"|"quick"|"other"; "Manual save 8", "Autosave 1"...
                                               bodyGender, voice,   // "Male"|"Female"|null (read from the save's metadata)
                                               level, hours, lifePath, modded, playthrough, patch,   // each may be null
                                               savedAt,       // unix seconds
                                               hasPicture }] }  // newest first
    POST /api/savetransfer/name { playthrough, name }          -> { ok, id, name }
         Names a playthrough (whitespace tidied, 60 characters at most; an empty name clears it). Kept in `<data>\save-names.json`;
         no save is touched. 404 unknown playthrough, 500 not saved.
    POST /api/savetransfer/inspect { save }                   -> { id, bodyGender, voice, counts: { clothes, modItems, guns, outfits, money } }
         Opens the save with the add-on (a few seconds). `modItems` = items the add-on cannot name (mod clothes).
    POST /api/savetransfer/preview { source?, target, gender?, look?, clothes?, outfits?, guns?, tidy?, stripMods?, money? }
                                                              -> { ok, report: { look?, gender?, clothesAdded?, gunsAdded?, outfitsAdded?,
                                                                                 outfitSetsSkipped?, outfitPartsSkipped?, outfitsNote? } }
         `gender` is "keep" (default), "female" or "male" (body and voice); the others are booleans. `stripMods` (boolean) makes the copy safe to load without mods: every item the plain game does not know is removed from every container
         (anything equipped from them is unequipped first) and the Equipment-EX outfits and active outfit parts are cleared (report:
         `modItemsRemoved`, `modItemKinds`, `modSlotsUnequipped`, `outfitsCleared`). Other mod data in the save is left as it is. `money` (whole number 0 to 2,000,000,000, also accepted as text with commas) sets the Eurodollars to exactly that amount (report:
         `moneyBefore`, `moneyAfter`; an empty or missing value keeps the money; 400 for anything else). `tidy` (boolean) cuts every clothing kind held more than 4 times down to 2, keeping anything equipped or used by an
         Equipment-EX outfit first (report: `tidyRemoved`, `tidyKinds` = { name: removed }). `source` is only needed when
         look, clothes, outfits or guns is ticked (not for gender or tidy); a gender change alone uses just `target` (a `source` sent with it is ignored). Changes nothing: it only counts
         what a real run would add. `outfitsNote` explains why outfits cannot be added (for example the target has never run with the mod).
    POST /api/savetransfer/run  { same body as preview }      -> { ok, slot, report, result: { bodyGender, voice, counts }, backup, source (null for a gender change alone), target, playthrough }
         Copies what was ticked from `source` (or just changes gender) onto a copy of `target` and puts the result into the saves folder as a NEW slot
         (`slot`, "ManualSave-<highest number + 1>"); it stays in the target's playthrough (`playthrough`). Before anything is made, both saves are copied to `backup`
         (`<data>\save-backups\<time>\`). No existing save is changed, moved or deleted. Synchronous (several seconds).
         Errors, everything left as it was: 400 nothing ticked / same save / bad name or gender, 404 save not found, 409 the add-on is not
         installed or refused (its message is passed on), 409 the game is running, 423 an apply is running, 500 the add-on failed or
         produced no usable save, 504 the add-on took too long.

    GET  /api/settings          -> { theme: "system"|"light"|"dark", accent: "#rrggbb" }
    POST /api/settings          { theme?, accent? }       -> same shape

## Errors
Non-2xx responses carry `{ error: string }` (human-readable, shown to the user as-is).
`409` = game is running. `423` = another apply is in progress.

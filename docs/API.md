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
      requires: string[],         // ids of mods this one needs
      conflicts: number           // files this mod loses/wins against other enabled mods
    }

## Endpoints

    GET  /api/state
      -> { game: { running: boolean },
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
    GET  /api/trash             -> { items: [{ id, name, group, files, size, deletedAt }], totalSize }   // newest first; id is the trash id
    POST /api/trash/restore     { id }                   -> { ok, id, name }        // back into the library; a name clash restores as "<name> (restored)"
    POST /api/trash/empty       { id? }                  -> { ok, removed, freed }  // one item, or the whole trash when id is omitted. Permanent.


    GET  /api/settings          -> { theme: "system"|"light"|"dark", accent: "#rrggbb" }
    POST /api/settings          { theme?, accent? }       -> same shape

## Errors
Non-2xx responses carry `{ error: string }` (human-readable, shown to the user as-is).
`409` = game is running. `423` = another apply is in progress.

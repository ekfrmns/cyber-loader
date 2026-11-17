# API change requests (UI -> engine)

Written by the UI session. Everything here is additive: the UI already works without it and falls back where noted. `ui/mock.js` implements all of it, so the mock is the reference behaviour.

## 1. Import must upload, not send a path (needed for drag and drop)
A page cannot read the absolute path of a file or folder dropped on it (browser security, also in Edge `--app` mode). `POST /api/import { path }` can't be called from a drop. Proposed upload flow:

    POST /api/import/begin   { name: string, kind: "archive"|"folder" }   -> { token }
    PUT  /api/import/file?token=<token>&path=<relative path, URL-encoded>  body: raw bytes (application/octet-stream) -> { ok }
    POST /api/import/finish  { token }                                    -> { ok, id, warnings: string[] }

- `archive`: one PUT, `path` is the file name (`Foo-1234-1-0.zip`). The engine unpacks it as it would for `/api/import`.
- `folder`: one PUT per file, `path` relative to the dropped folder (`archive/pc/mod/x.archive`). Engine rejects `..` and absolute paths.
- Nothing is ever executed. `finish` returns the new mod's `id`; the UI shows its group from the next `/api/state`.
- Fallback today: none (drop shows an error toast if these endpoints are missing).

## 2. `profileDirty` in `/api/state`
    GET /api/state -> { ..., profileDirty: boolean }   // staged mod set differs from the saved profile
Used to (a) ask "Save changes to X?" before switching profiles, (b) disable "Save" when there's nothing to save, (c) show "Edited" next to the profile.
- Fallback: if missing, the UI never warns on switch and always enables Save.

## 3. File lists in `/api/preview`
The handoff asks the preview to list the files to add and remove; the contract only has counts.

    POST /api/preview -> { ...existing,
      files: { add: [{ id, path }], remove: [{ id, path }] },  // may be capped (e.g. 5000 each)
      filesTruncated: boolean }
- `path` is relative to the game folder. The UI groups by `id` and shows them in a collapsible list under each mod.
- Fallback: without `files`, each mod shows its file count only.

## 4. `POST /api/discard`
    POST /api/discard -> /api/state shape     // staged set := what is deployed now
Backs "Discard changes" in the preview sheet.
- Fallback: on 404 the UI toggles each pending mod back with `/api/toggle` (slower, many requests).

## 5. Notes, no change needed
- `/api/restore-baseline` returning `501 { error }` is shown as a warning toast with the engine's message.
- `/api/progress` is polled every 200 ms during an apply; `text` is shown as-is. On load the UI checks `/api/progress` and resumes the progress view if an apply is already `running`.
- `/api/state` is polled every 3 s (not while a toggle or apply is in flight) to pick up the game starting or closing. If a lighter `GET /api/game` exists later the UI can switch to it.

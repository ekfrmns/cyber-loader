# Window host contract (CyberLoader.exe <-> UI)

`CyberLoader.exe` owns the app window (Microsoft WebView2, the same engine as Edge). The window can be **frameless**: no Windows title bar, so the UI draws its own top bar and window buttons and it looks like part of the app. The host injects a small script into every page at load, which creates `window.cyberHost`. In a normal browser (and in `?mock=1`) `window.cyberHost` is `undefined`: the UI must feature-detect and then draw no window buttons.

Until the page calls `cyberHost.frameless(true)` the host keeps the normal Windows title bar, so any UI version works.

## What the UI calls (`window.cyberHost`)
```
cyberHost.frameless(on: boolean)        // true = hide the Windows title bar; the page now draws its own. Call once at startup.
cyberHost.minimize()
cyberHost.toggleMaximize()              // maximize <-> restore
cyberHost.close()                       // asks the host to close the window (it confirms if an apply is running)
cyberHost.setBackground('#rrggbb')      // colour shown behind the page (resize flashes, before first paint); call when the theme changes
cyberHost.onState(fn)                   // fn({ maximized: boolean, focused: boolean }) is called at once and on every change
```
The host also sets attributes on `<html>` so CSS can react without JS: `is-host` (class, always), `data-maximized` (present while maximized), `data-focused` (present while the window is active), `data-frameless` (present when frameless is on).

## What the host does for you (do not rebuild it in the UI)
- **Dragging**: any element with the attribute `data-window-drag` moves the window when pressed with the left mouse button (native move: snapping, restore-from-maximized, Windows 11 snap layouts all work). Double-click on it toggles maximize. Interactive children (`button`, `input`, `a`, `select`, `textarea`, `[data-no-drag]`) are excluded automatically.
- **Resizing**: when frameless and not maximized the host injects 8 invisible resize handles (3 px at the top edge, 5 px elsewhere, 8 px corners) at the window edges and corners (`position: fixed`, highest z-index) with the right resize cursors. Keep interactive controls out of the outermost 5 px (3 px at the top) of the window.
- **Maximized**: the host fits the window to the work area, so no extra padding is needed. Windows 11 rounds the corners of a non-maximized window by itself.
- **Window icon and taskbar icon**: the exe's icon.

## Layout guidance for the UI
- Top bar: 40 px high, same background as the app (no visible bar), `data-window-drag` on the bar, app name or profile at the left, the existing search/status/menu controls can live in it. Window buttons at the far right: three 46 x 40 px buttons (minimize, maximize/restore, close), Windows 11 style, icons drawn as SVG (do not depend on a font). Hover: subtle fill; close hover = red (`#e81123`) with a white glyph. Show the restore glyph while `data-maximized`.
- Buttons must have accessible names ("Minimize", "Maximize" / "Restore", "Close") and visible focus rings. They are buttons only in the host window; in a normal browser render nothing for them.
- Scrollbars: thin, rounded, transparent track, theme-aware, flush with the right edge, so the page looks like one surface.
- Dim the top bar contents when the window is not focused (`html:not([data-focused])`).

## Errors and edge cases
- `cyberHost.close()` while an apply is running: the host shows its own "an apply is running, close anyway?" dialog (default No).
- If the page reloads, call `frameless(true)` again at startup (state is per page load; the host keeps the frame state while the page does not say otherwise).

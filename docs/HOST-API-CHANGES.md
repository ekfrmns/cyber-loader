# Window host: requests from the UI

Requests from the UI session for `CyberLoader.exe` / `launcher/host.js`. The contract stays in `docs/HOST-API.md`; nothing here is needed for the current UI to work. Additive only.

## 1. Snap Layouts on the maximize button (nice to have)
Windows 11 shows the Snap Layouts flyout when you hover a window's maximize button. With HTML window buttons, Windows can't know where that button is, so the flyout never appears.
- Ask: `cyberHost.setMaximizeButtonRect({ x, y, width, height } | null)` in CSS pixels relative to the page. The host converts it to window pixels (DPI scale) and answers `WM_NCHITTEST` with `HTMAXBUTTON` inside it, so Windows shows the flyout. The UI would call it at startup, on resize and when `frameless` changes.
- Detail: once the host returns `HTMAXBUTTON` there, the page no longer gets the mouse events for that rect, so the host should tell the page about hover/press (for example `onState` gets `maxHover: boolean`, `maxPressed: boolean`) so the button can still draw its hover fill. A click there is handled by Windows (maximize/restore).
- UI side today: the maximize button works by click; no flyout.

## 2. Question: Alt+Space window menu
With the Windows title bar hidden, does Alt+Space still open the system menu (Restore, Move, Size, Minimize, Maximize, Close)? Keyboard users rely on it to move or resize the window. If not, please keep it working while frameless. The UI doesn't handle Alt+Space.

## 3. Note: right resize edge over the scrollbar (no change needed)
The page scrollbar is 12px wide and flush with the right edge; the host's 5px right resize handle sits over its outer 5px. The visible thumb is drawn 3-9px from the edge, so it can still be grabbed, and the edge still resizes. Recording it in case it ever feels fiddly.

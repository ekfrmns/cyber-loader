// Injected by CyberLoader.exe into every page (WebView2 AddScriptToExecuteOnDocumentCreated).
// Defines window.cyberHost and the native-window behaviour the UI does not have to rebuild. Contract: docs/HOST-API.md
(function () {
  if (!window.chrome || !window.chrome.webview || window.cyberHost) return;
  var wv = window.chrome.webview;
  function post(o) { wv.postMessage(o); }
  var state = { maximized: false, focused: true, radius: 0 };
  var listeners = [];
  var frameless = false;
  var handles = [];

  function root() { return document.documentElement; }
  function paint() {
    var h = root();
    if (!h) return;
    h.classList.add('is-host');
    if (state.maximized) h.setAttribute('data-maximized', ''); else h.removeAttribute('data-maximized');
    if (state.focused) h.setAttribute('data-focused', ''); else h.removeAttribute('data-focused');
    h.style.setProperty('--win-radius', (state.radius || 0) + 'px');   // corner radius the host clips the window to
    if (frameless) h.setAttribute('data-frameless', ''); else h.removeAttribute('data-frameless');
    updateHandles();
  }

  wv.addEventListener('message', function (e) {
    var d = e.data;
    if (d && d.type === 'window') {
      state = { maximized: !!d.maximized, focused: !!d.focused, radius: +d.radius || 0 };
      paint();
      for (var i = 0; i < listeners.length; i++) { try { listeners[i]({ maximized: state.maximized, focused: state.focused }); } catch (_) {} }
    }
  });

  window.cyberHost = {
    frameless: function (on) { frameless = !!on; post({ cmd: 'frameless', on: frameless }); paint(); },
    minimize: function () { post({ cmd: 'minimize' }); },
    toggleMaximize: function () { post({ cmd: 'toggleMaximize' }); },
    close: function () { post({ cmd: 'close' }); },
    setBackground: function (c) { post({ cmd: 'background', color: String(c) }); },
    onState: function (fn) {
      listeners.push(fn);
      try { fn({ maximized: state.maximized, focused: state.focused }); } catch (_) {}
    }
  };

  // ---- dragging: elements with data-window-drag move the window; a quick second press toggles maximize
  var NO_DRAG = 'button,input,a,select,textarea,label,[data-no-drag],[role="button"],[contenteditable]';
  var last = { t: 0, x: 0, y: 0 };
  document.addEventListener('mousedown', function (e) {
    if (e.button !== 0 || !(e.target instanceof Element)) return;
    var t = e.target;
    if (!t.closest('[data-window-drag]') || t.closest(NO_DRAG)) return;
    var now = Date.now();
    var dbl = now - last.t < 450 && Math.abs(e.screenX - last.x) < 5 && Math.abs(e.screenY - last.y) < 5;
    last = { t: dbl ? 0 : now, x: e.screenX, y: e.screenY };
    e.preventDefault();
    post({ cmd: dbl ? 'toggleMaximize' : 'startDrag' });
  }, true);

  // ---- resizing: invisible handles at the edges while frameless and not maximized
  var EDGES = [
    ['t', 'top:0;left:8px;right:8px;height:3px;cursor:ns-resize'],
    ['b', 'bottom:0;left:8px;right:8px;height:5px;cursor:ns-resize'],
    ['l', 'left:0;top:8px;bottom:8px;width:5px;cursor:ew-resize'],
    ['r', 'right:0;top:8px;bottom:8px;width:5px;cursor:ew-resize'],
    ['tl', 'top:0;left:0;width:8px;height:8px;cursor:nwse-resize'],
    ['tr', 'top:0;right:0;width:8px;height:8px;cursor:nesw-resize'],
    ['bl', 'bottom:0;left:0;width:8px;height:8px;cursor:nesw-resize'],
    ['br', 'bottom:0;right:0;width:8px;height:8px;cursor:nwse-resize']
  ];
  function updateHandles() {
    var want = frameless && !state.maximized;
    if (want && !handles.length) {
      var h = root();
      if (!h) return;
      EDGES.forEach(function (pair) {
        var el = document.createElement('div');
        el.setAttribute('data-host-resize', pair[0]);
        el.style.cssText = 'position:fixed;z-index:2147483647;' + pair[1];
        el.addEventListener('mousedown', function (ev) {
          if (ev.button !== 0) return;
          ev.preventDefault();
          post({ cmd: 'startResize', edge: pair[0] });
        });
        h.appendChild(el);
        handles.push(el);
      });
    } else if (!want && handles.length) {
      handles.forEach(function (el) { if (el.parentNode) el.parentNode.removeChild(el); });
      handles = [];
    }
  }
  document.addEventListener('DOMContentLoaded', paint);
  paint();
})();

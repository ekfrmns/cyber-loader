"""Tiny Chrome DevTools Protocol client (stdlib only) for testing the UI inside the real CyberLoader window.
It talks to WebView2's debug port, so it never moves your real mouse or needs the window in front.

  # 1. start the sandbox window with a debug port (see tools\\dev-host.ps1 -DebugPort 9333)
  # 2. python tools\\cdp.py eval "document.title"
  #    python tools\\cdp.py click 936 452           (CSS pixel coordinates inside the page)
  #    python tools\\cdp.py shot out.png
Use as a module: from cdp import Page; p = Page(9333); p.eval("..."); p.click(x, y); p.shot("a.png")
"""
import base64
import json
import os
import socket
import struct
import sys
import urllib.request


class Page:
    def __init__(self, port: int = 9333, url_part: str = "127.0.0.1"):
        targets = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=5).read())
        t = next(x for x in targets if x.get("type") == "page" and url_part in x.get("url", ""))
        host, path = "127.0.0.1", t["webSocketDebuggerUrl"].split(str(port), 1)[1]
        self.s = socket.create_connection((host, port), timeout=15)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                        f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            resp += self.s.recv(1)
        if b" 101 " not in resp.split(b"\r\n")[0]:
            raise RuntimeError("websocket handshake failed: " + resp.decode(errors="replace")[:200])
        self.n = 0

    # -- websocket framing (client frames are masked)
    def _send(self, text: str) -> None:
        data = text.encode()
        head = b"\x81"
        if len(data) < 126:
            head += bytes([0x80 | len(data)])
        elif len(data) < 65536:
            head += bytes([0x80 | 126]) + struct.pack(">H", len(data))
        else:
            head += bytes([0x80 | 127]) + struct.pack(">Q", len(data))
        mask = os.urandom(4)
        self.s.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def _read(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self.s.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("closed")
            buf += chunk
        return buf

    def _recv(self) -> str:
        msg = b""
        while True:
            b1, b2 = self._read(2)
            ln = b2 & 0x7F
            if ln == 126:
                ln = struct.unpack(">H", self._read(2))[0]
            elif ln == 127:
                ln = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(ln)
            op = b1 & 0x0F
            if op in (1, 0):
                msg += payload
                if b1 & 0x80:
                    return msg.decode()
            elif op == 8:
                raise ConnectionError("closed by peer")

    def call(self, method: str, **params):
        self.n += 1
        self._send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            r = json.loads(self._recv())
            if r.get("id") == self.n:
                if "error" in r:
                    raise RuntimeError(r["error"])
                return r.get("result", {})

    def eval(self, js: str):
        r = self.call("Runtime.evaluate", expression=js, returnByValue=True, awaitPromise=True)
        if "exceptionDetails" in r:
            raise RuntimeError(r["exceptionDetails"].get("text", "") + " " + json.dumps(r["exceptionDetails"].get("exception", {}))[:300])
        return r["result"].get("value")

    def click(self, x: float, y: float, count: int = 1, gap_ms: int = 0) -> None:
        import time
        for _ in range(count):
            for typ in ("mousePressed", "mouseReleased"):
                self.call("Input.dispatchMouseEvent", type=typ, x=x, y=y, button="left", clickCount=1)
            if gap_ms:
                time.sleep(gap_ms / 1000)

    def shot(self, path: str) -> None:
        open(path, "wb").write(base64.b64decode(self.call("Page.captureScreenshot", format="png")["data"]))


if __name__ == "__main__":
    port = int(os.environ.get("CDP_PORT", "9333"))
    cmd, args = sys.argv[1], sys.argv[2:]
    page = Page(port)
    if cmd == "eval":
        print(json.dumps(page.eval(args[0]), indent=1))
    elif cmd == "click":
        page.click(float(args[0]), float(args[1]))
    elif cmd == "shot":
        page.shot(args[0])
    else:
        sys.exit(__doc__)

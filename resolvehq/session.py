"""UI-independent session logic. Consent gates everything: no frames, no input before an explicit grant."""
import asyncio, json
from .proto import send_frame, recv_frame, handshake, norm_code

BUTTONS, ACTIONS = {"left", "right", "middle", None}, {"move", "down", "up"}

async def _connect(relay, first):
    host, port, *tls = relay
    r, w = await asyncio.open_connection(host, port, ssl=True if (tls and tls[0]) else None)
    await send_frame(w, json.dumps(first).encode()); return r, w

class HostSession:
    def __init__(self, relay, capture, inputs, on_status, ask_consent, fps=5):
        self.relay, self.cap, self.inp, self.on_status, self.ask, self.fps = relay, capture, inputs, on_status, ask_consent, fps
        self._stop = asyncio.Event()
    def stop(self): self._stop.set()   # from other threads: loop.call_soon_threadsafe(h.stop)

    async def run(self):
        r, w = await _connect(self.relay, {"t": "host"})
        try:
            m = json.loads(await recv_frame(r)); code = m["code"]; self.on_status("waiting", code=code, ttl=m.get("ttl", 300))
            if json.loads(await recv_frame(r)).get("t") != "paired": return self.on_status("expired")
            ch, sas = await handshake(r, w, code, "host")
            hello, _ = await ch.recv()
            grant = await self.ask(str(hello.get("name", "?"))[:40], sas)   # None | "view" | "control"
            if grant not in ("view", "control"):
                await ch.send({"t": "deny"}); return self.on_status("denied")
            control = grant == "control"
            await ch.send({"t": "grant", "control": control}); self.on_status("active", sas=sas, control=control)
            async def stream():
                loop = asyncio.get_running_loop()
                while True:
                    await ch.send({"t": "frame"}, await loop.run_in_executor(None, self.cap.grab))
                    await asyncio.sleep(1 / self.fps)
            async def listen():
                while True:
                    m, _ = await ch.recv()
                    if m.get("t") == "bye": return
                    if control: self._input(m)
            tasks = [asyncio.ensure_future(x) for x in (stream(), listen(), self._stop.wait())]
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in tasks: t.cancel()
            await ch.send({"t": "bye"}); self.on_status("stopped")
        except Exception as e:
            self.on_status("error", msg=type(e).__name__)
        finally:
            w.close()

    def _input(self, m):   # everything from the remote side is untrusted
        try:
            if m["t"] == "mouse" and m["a"] in ACTIONS and m.get("b") in BUTTONS:
                self.inp.mouse(min(max(float(m["x"]), 0), 1), min(max(float(m["y"]), 0), 1), m["a"], m.get("b"))
            elif m["t"] == "key" and isinstance(m["k"], str) and 0 < len(m["k"]) <= 16:
                self.inp.key(m["k"], bool(m["down"]))
        except (KeyError, TypeError, ValueError): pass

class ViewerSession:
    def __init__(self, relay, name, on_status, on_frame):
        self.relay, self.name, self.on_status, self.on_frame, self.ch, self.control = relay, name, on_status, on_frame, None, False
    async def run(self, code):
        r, w = await _connect(self.relay, {"t": "join", "code": norm_code(code)})
        try:
            m = json.loads(await recv_frame(r))
            if m.get("t") != "paired": return self.on_status("error", msg=m.get("m", "failed"))
            self.ch, sas = await handshake(r, w, code, "viewer")
            await self.ch.send({"t": "hello", "name": self.name}); self.on_status("awaiting_consent", sas=sas)
            m, _ = await self.ch.recv()
            if m.get("t") != "grant": return self.on_status("denied")
            self.control = bool(m.get("control")); self.on_status("active", sas=sas, control=self.control)
            while True:
                m, blob = await self.ch.recv()
                if m["t"] == "frame": self.on_frame(blob)
                elif m["t"] == "bye": return self.on_status("stopped")
        except Exception as e:
            self.on_status("error", msg=type(e).__name__)
        finally:
            w.close()
    async def send_input(self, msg):
        if self.ch and self.control: await self.ch.send(msg)
    async def bye(self):
        if self.ch: await self.ch.send({"t": "bye"})

import asyncio, unittest
from resolvehq.relay import serve
from resolvehq.proto import handshake
from resolvehq.session import HostSession, ViewerSession
from resolvehq.backends import SyntheticCapture, RecordingInput

class T(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.srv, self.relay = await serve("127.0.0.1", 0, ttl=5)
        self.addr = ("127.0.0.1", self.srv.sockets[0].getsockname()[1])
    async def asyncTearDown(self): self.srv.close()

    async def start_host(self, grant, ttl=None):
        if ttl: self.relay.ttl = ttl
        self.hs, self.inp, ev = [], RecordingInput(), asyncio.Queue()
        async def ask(name, sas): self.host_sas = sas; return grant
        h = HostSession(self.addr, SyntheticCapture(), self.inp, lambda s, **k: (self.hs.append(s), ev.put_nowait((s, k))), ask, fps=50)
        t = asyncio.create_task(h.run())
        while True:
            s, k = await ev.get()
            if s == "waiting": return h, t, k["code"]

    def viewer(self, frames, sts): return ViewerSession(self.addr, "tech", lambda s, **k: sts.append((s, k)), frames.append)

    async def test_full_session_with_control(self):
        h, ht, code = await self.start_host("control")
        frames, sts = [], []; v = self.viewer(frames, sts); vt = asyncio.create_task(v.run(code[:3] + "-" + code[3:]))
        for _ in range(100):
            if frames and v.control: break
            await asyncio.sleep(0.05)
        self.assertTrue(frames and frames[0].startswith(b"\xff\xd8"))
        self.assertEqual(self.host_sas, dict(sts)["awaiting_consent"]["sas"])   # same SAS both sides
        await v.send_input({"t": "mouse", "x": 2.0, "y": .5, "a": "down", "b": "left"})
        await v.send_input({"t": "mouse", "x": .5, "y": .5, "a": "explode", "b": "left"})  # invalid: dropped
        await asyncio.sleep(.2)
        self.assertEqual(self.inp.events, [("mouse", 1.0, .5, "down", "left")])   # clamped
        h.stop(); await asyncio.wait_for(asyncio.gather(ht, vt), 3); self.assertIn("stopped", self.hs)

    async def test_view_only_ignores_input(self):
        h, ht, code = await self.start_host("view")
        frames, sts = [], []; v = self.viewer(frames, sts); vt = asyncio.create_task(v.run(code))
        while not frames: await asyncio.sleep(.05)
        await v.send_input({"t": "key", "k": "a", "down": True}); await asyncio.sleep(.2)
        self.assertEqual(self.inp.events, []); h.stop(); await asyncio.gather(ht, vt)

    async def test_denied_sends_no_frames(self):
        h, ht, code = await self.start_host(None)
        frames, sts = [], []; await asyncio.wait_for(self.viewer(frames, sts).run(code), 3); await ht
        self.assertEqual(frames, []); self.assertEqual(sts[-1][0], "denied")

    async def test_code_is_one_time(self):
        h, ht, code = await self.start_host("view")
        s1, s2 = [], []; vt = asyncio.create_task(self.viewer([], s1).run(code)); await asyncio.sleep(.3)
        await asyncio.wait_for(self.viewer([], s2).run(code), 3)
        self.assertEqual(s2[-1][0], "error"); h.stop(); await asyncio.gather(ht, vt)

    async def test_wrong_code_and_lockout(self):
        h, ht, code = await self.start_host("view")
        for _ in range(5):
            s = []; await self.viewer([], s).run("000000000"); self.assertEqual(s[-1][0], "error")
        s = []; await self.viewer([], s).run(code)   # correct code, but this IP is rate-limited now
        self.assertEqual(s[-1][1]["msg"], "too many attempts"); ht.cancel()

    async def test_expiry(self):
        h, ht, code = await self.start_host("view", ttl=0.3)
        await asyncio.wait_for(ht, 3); self.assertIn("expired", self.hs)
        s = []; await self.viewer([], s).run(code); self.assertEqual(s[-1][0], "error")

class Crypto(unittest.IsolatedAsyncioTestCase):
    async def test_wrong_code_fails_handshake(self):
        async def cb(r, w):
            try: await handshake(r, w, "111222333", "host")
            except Exception: pass
        srv = await asyncio.start_server(cb, "127.0.0.1", 0)
        r, w = await asyncio.open_connection("127.0.0.1", srv.sockets[0].getsockname()[1])
        with self.assertRaises(Exception): await handshake(r, w, "999888777", "viewer")
        srv.close()

    async def test_tampered_frame_rejected(self):
        out = {}
        async def cb(r, w): out["h"] = await handshake(r, w, "123", "host")
        srv = await asyncio.start_server(cb, "127.0.0.1", 0)
        r, w = await asyncio.open_connection("127.0.0.1", srv.sockets[0].getsockname()[1])
        ch, _ = await handshake(r, w, "123", "viewer"); hch, _ = out["h"]
        orig = hch.w.write
        hch.w.write = lambda d: orig(d[:-1] + bytes([d[-1] ^ 1]))   # flip one ciphertext bit
        await hch.send({"t": "x"})
        with self.assertRaises(Exception): await ch.recv()
        srv.close()

if __name__ == "__main__": unittest.main()

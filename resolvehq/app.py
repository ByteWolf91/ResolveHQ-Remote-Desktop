"""ResolveHQ Remote Desktop — Tk UI. Not exercised in the build sandbox (no display/tkinter): syntax-checked only."""
import argparse, asyncio, getpass, io, threading, time, tkinter as tk
from tkinter import ttk
from .session import HostSession, ViewerSession

APP, VER, F = "ResolveHQ Remote Desktop", "0.1.0", "Segoe UI"
C = dict(nav="#0e1a33", nav_hi="#1b2c52", nav_ink="#b9c6e6", bg="#f3f5fa", card="#ffffff", line="#e2e7f1", ink="#141b2d", mute="#66738f",
         brand="#2f6bff", brand_d="#2457d6", tint="#eaf0ff", ok="#14976b", ok_t="#e4f5ee", bad="#d6403f", bad_t="#fdeceb",
         info="#2f6bff", info_t="#eaf0ff", idle="#66738f", idle_t="#eef1f7")
STATES = {"idle": ("Ready", "idle"), "waiting": ("Waiting for technician", "info"), "awaiting_consent": ("Waiting for approval", "info"),
          "active": ("Session active", "ok"), "denied": ("Request declined", "bad"), "stopped": ("Session ended", "idle"),
          "expired": ("Code expired", "bad"), "error": ("Connection problem", "bad")}
KEYMAP = {"return": "enter", "escape": "esc", "prior": "page_up", "next": "page_down", "control_l": "ctrl", "control_r": "ctrl",
          "shift_l": "shift", "shift_r": "shift", "alt_l": "alt", "alt_r": "alt", "space": " "}

def lbl(p, text="", size=10, color=None, bold=False, **kw):
    return tk.Label(p, text=text, bg=p["bg"], fg=color or C["ink"], font=(F, size, "bold" if bold else "normal"), anchor="w", justify="left", **kw)

def card(p, title=None, sub=None):
    f = tk.Frame(p, bg=C["card"], highlightbackground=C["line"], highlightthickness=1)
    b = tk.Frame(f, bg=C["card"]); b.pack(fill="both", expand=True, padx=22, pady=18)
    if title: lbl(b, title, 12, bold=True).pack(fill="x")
    if sub: lbl(b, sub, 10, C["mute"], wraplength=560).pack(fill="x", pady=(2, 10))
    return f, b

class Btn(tk.Button):
    K = {"primary": (C["brand"], "#fff", C["brand_d"]), "soft": (C["tint"], C["brand"], "#dbe6ff"), "danger": (C["bad"], "#fff", "#b93230")}
    def __init__(s, p, text, cmd, kind="primary"):
        super().__init__(p, relief="flat", bd=0, cursor="hand2", font=(F, 11, "bold"), padx=20, pady=10)
        s.bind("<Enter>", lambda e: s.config(bg=s.hv)); s.bind("<Leave>", lambda e: s.config(bg=s.b0)); s.set(text, cmd, kind)
    def set(s, text, cmd, kind="primary"):
        s.b0, fg, s.hv = s.K[kind]; s.config(text=text, command=cmd, bg=s.b0, fg=fg, activebackground=s.hv, activeforeground=fg)

class Pill(tk.Label):
    def __init__(s, p): super().__init__(p, font=(F, 9, "bold"), padx=10, pady=4); s.show("idle")
    def show(s, key, extra=""):
        t, k = STATES[key]; s.config(text="●  " + t + (f"  ·  {extra}" if extra else ""), fg=C[k], bg=C[k + "_t"])

class _NoInput:
    def mouse(s, *a): pass
    def key(s, *a): pass

class App:
    def __init__(s, relay, name):
        s.relay, s.name = relay, name; s.hs = s.hfut = s.vs = s.banner = s.win = s.deadline = s.t0 = None; s.ttl, s.peer, s.active = 300, "—", False
        s.loop = asyncio.new_event_loop(); threading.Thread(target=s.loop.run_forever, daemon=True).start()
        s.root = r = tk.Tk(); r.title(APP); r.geometry("980x640"); r.minsize(900, 600); r.configure(bg=C["bg"])
        st = ttk.Style(r); st.theme_use("clam")
        st.configure("Thin.Horizontal.TProgressbar", troughcolor=C["tint"], background=C["brand"], bordercolor=C["tint"], lightcolor=C["brand"], darkcolor=C["brand"], thickness=6)
        s._sidebar(); s.main = tk.Frame(r, bg=C["bg"]); s.main.pack(side="left", fill="both", expand=True)
        s.pages = {"share": s._share(), "connect": s._connect(), "security": s._security()}; s.go("share"); s.tick()

    # ---------- chrome ----------
    def _sidebar(s):
        sb = tk.Frame(s.root, bg=C["nav"], width=240); sb.pack(side="left", fill="y"); sb.pack_propagate(False)
        head = tk.Frame(sb, bg=C["nav"]); head.pack(fill="x", padx=22, pady=(28, 26))
        cv = tk.Canvas(head, width=40, height=40, bg=C["nav"], highlightthickness=0); cv.pack(side="left")
        cv.create_oval(2, 2, 38, 38, fill=C["brand"], outline=""); cv.create_text(20, 20, text="R", fill="white", font=(F, 16, "bold"))
        t = tk.Frame(head, bg=C["nav"]); t.pack(side="left", padx=12)
        tk.Label(t, text="ResolveHQ", bg=C["nav"], fg="white", font=(F, 14, "bold")).pack(anchor="w")
        tk.Label(t, text="Remote Desktop", bg=C["nav"], fg=C["nav_ink"], font=(F, 9)).pack(anchor="w")
        s.nav = {}
        for key, text in (("share", "▣   Share my screen"), ("connect", "⇄   Connect to a computer"), ("security", "◆   Security & privacy")):
            l = tk.Label(sb, text=text, bg=C["nav"], fg=C["nav_ink"], font=(F, 11), anchor="w", padx=22, pady=12, cursor="hand2")
            l.pack(fill="x"); l.bind("<Button-1>", lambda e, k=key: s.go(k)); s.nav[key] = l
        tk.Label(sb, text=f"Relay  {s.relay[0]}:{s.relay[1]}\nv{VER} · attended access only", bg=C["nav"], fg="#7f8fb5", font=(F, 9), justify="left", anchor="w").pack(side="bottom", fill="x", padx=22, pady=20)

    def go(s, key):
        for p in s.pages.values(): p.pack_forget()
        s.pages[key].pack(fill="both", expand=True, padx=36, pady=30)
        for k, l in s.nav.items(): l.config(bg=C["nav_hi"] if k == key else C["nav"], fg="white" if k == key else C["nav_ink"])

    def _page(s, title, sub):
        p = tk.Frame(s.main, bg=C["bg"]); lbl(p, title, 20, bold=True).pack(fill="x"); lbl(p, sub, 10, C["mute"], wraplength=640).pack(fill="x", pady=(2, 18)); return p

    # ---------- pages ----------
    def _share(s):
        p = s._page("Share my screen", "Get help from a technician. Nothing is shared until you approve, and you can stop at any time.")
        f, b = card(p, "Session code", "Read this code to your technician. It works once and expires automatically."); f.pack(fill="x")
        s.code = tk.Label(b, text="•••  •••  •••", bg=C["tint"], fg=C["brand"], font=("Consolas", 38, "bold"), pady=14); s.code.pack(fill="x")
        row = tk.Frame(b, bg=C["card"]); row.pack(fill="x", pady=(12, 4)); s.hpill = Pill(row); s.hpill.pack(side="left")
        s.count = lbl(row, "", 10, C["mute"]); s.count.pack(side="right")
        s.bar = ttk.Progressbar(b, style="Thin.Horizontal.TProgressbar", maximum=100); s.bar.pack(fill="x", pady=(6, 14))
        s.hbtn = Btn(b, "Generate code", s.start_host); s.hbtn.pack(anchor="w")
        f2, b2 = card(p, "Active session"); f2.pack(fill="x", pady=16)
        g = tk.Frame(b2, bg=C["card"]); g.pack(fill="x", pady=(6, 0)); s.det = {}
        for i, k in enumerate(("Technician", "Access", "Verification code", "Duration")):
            c = tk.Frame(g, bg=C["card"]); c.grid(row=0, column=i, sticky="w", padx=(0, 34))
            lbl(c, k.upper(), 8, C["mute"], True).pack(anchor="w"); s.det[k] = lbl(c, "—", 13, bold=True); s.det[k].pack(anchor="w")
        f3, b3 = card(p, "How it works"); f3.pack(fill="x")
        row = tk.Frame(b3, bg=C["card"]); row.pack(fill="x", pady=(6, 0))
        for i, t in enumerate(("Generate a code and read it to your technician.", "Compare the verification code, then approve or decline.", "Watch the red banner. Click Stop whenever you like.")):
            c = tk.Frame(row, bg=C["card"]); c.pack(side="left", fill="x", expand=True, padx=(0, 14))
            lbl(c, str(i + 1), 14, C["brand"], True).pack(anchor="w"); lbl(c, t, 10, C["mute"], wraplength=190).pack(anchor="w")
        return p

    def _connect(s):
        p = s._page("Connect to a computer", "Enter the 9-digit code the other person reads to you. They will be asked to approve.")
        f, b = card(p, "Session code"); f.pack(fill="x")
        s.entry = tk.Entry(b, font=("Consolas", 26, "bold"), justify="center", relief="flat", bg=C["tint"], fg=C["brand"], insertbackground=C["brand"], highlightthickness=2, highlightbackground=C["line"], highlightcolor=C["brand"])
        s.entry.pack(fill="x", ipady=12); s.entry.bind("<Return>", lambda e: s.start_view())
        lbl(b, "Your name (shown to the other person)", 9, C["mute"]).pack(fill="x", pady=(14, 3))
        s.nm = tk.Entry(b, font=(F, 11), relief="flat", bg="#f7f8fc", highlightthickness=1, highlightbackground=C["line"], highlightcolor=C["brand"]); s.nm.insert(0, s.name); s.nm.pack(fill="x", ipady=7)
        row = tk.Frame(b, bg=C["card"]); row.pack(fill="x", pady=(16, 0)); Btn(row, "Connect", s.start_view).pack(side="left")
        s.vpill = Pill(row); s.vpill.pack(side="right")
        return p

    def _security(s):
        p = s._page("Security & privacy", "How ResolveHQ keeps you in control.")
        f, b = card(p); f.pack(fill="x")
        for t, d in (("You approve every session", "A consent prompt appears on the shared computer. Nothing is captured before you allow it."),
                     ("Attended access only", "There is no background service and no unattended access. Closing the app ends sharing."),
                     ("One-time, expiring codes", "Codes work once, expire after 5 minutes, and repeated wrong guesses are blocked."),
                     ("Encrypted between the two apps", "Sessions use X25519 + ChaCha20-Poly1305; the relay only forwards ciphertext."),
                     ("Always visible", "A red banner stays on top while your screen is shared, with a Stop button.")):
            r = tk.Frame(b, bg=C["card"]); r.pack(fill="x", pady=7)
            tk.Label(r, text="✓", bg=C["ok_t"], fg=C["ok"], font=(F, 11, "bold"), width=3, pady=4).pack(side="left", anchor="n")
            c = tk.Frame(r, bg=C["card"]); c.pack(side="left", padx=14); lbl(c, t, 11, bold=True).pack(anchor="w"); lbl(c, d, 10, C["mute"], wraplength=520).pack(anchor="w")
        lbl(p, "The protocol is custom and has not been independently audited. Compare the verification code on both screens every session.", 9, C["mute"], wraplength=640).pack(fill="x", pady=14)
        return p

    def tick(s):
        now = time.time()
        if s.deadline: rem = max(0, s.deadline - now); s.count.config(text=f"Expires in {int(rem) // 60}:{int(rem) % 60:02d}"); s.bar["value"] = rem / s.ttl * 100
        else: s.count.config(text=""); s.bar["value"] = 0
        if s.t0:
            d = int(now - s.t0); txt = f"{d // 60:02d}:{d % 60:02d}"; s.det["Duration"].config(text=txt)
            if s.banner: s.btime.config(text=txt)
        s.root.after(500, s.tick)

    # ---------- host ----------
    def start_host(s):
        from .backends import MssCapture, PynputInput
        async def ask(name, sas):
            s.peer, s.deadline = name, None; fut = s.loop.create_future()
            s.root.after(0, lambda: s.consent(name, sas, lambda v: s.loop.call_soon_threadsafe(fut.set_result, v))); return await fut
        try: inp = PynputInput()
        except Exception: inp = _NoInput()   # capture-only when input injection is unavailable (e.g. Wayland)
        s.hs = HostSession(s.relay, MssCapture(), inp, lambda st, **k: s.root.after(0, s.host_status, st, k), ask)
        s.hbtn.set("Cancel", s.stop_host, "soft"); s.hfut = asyncio.run_coroutine_threadsafe(s.hs.run(), s.loop)

    def stop_host(s):
        if s.active: s.loop.call_soon_threadsafe(s.hs.stop)
        elif s.hfut: s.hfut.cancel(); s.host_status("stopped", {})

    def host_status(s, st, k):
        s.active = st == "active"; s.hpill.show(st, f"verify {k['sas']}" if s.active else k.get("msg", ""))
        if st == "waiting":
            s.ttl = k.get("ttl", 300); s.deadline = time.time() + s.ttl; c = k["code"]; s.code.config(text=f"{c[:3]}  {c[3:6]}  {c[6:]}")
        elif s.active:
            s.t0 = time.time(); s.det["Technician"].config(text=s.peer); s.det["Access"].config(text="View & control" if k["control"] else "View only")
            s.det["Verification code"].config(text=k["sas"]); s.banner_show(); s.hbtn.set("Stop sharing", s.stop_host, "danger")
        else:
            s.deadline = s.t0 = None; s.code.config(text="•••  •••  •••")
            for d in s.det.values(): d.config(text="—")
            if s.banner: s.banner.destroy(); s.banner = None
            s.hbtn.set("Generate code", s.start_host)

    def banner_show(s):   # always-on-top indicator the remote side cannot hide
        b = s.banner = tk.Toplevel(s.root); b.title("ResolveHQ — sharing"); b.configure(bg=C["bad"]); b.attributes("-topmost", True); b.resizable(False, False)
        b.geometry(f"+{s.root.winfo_screenwidth() // 2 - 190}+8")
        tk.Label(b, text="●  Your screen is being shared", bg=C["bad"], fg="white", font=(F, 11, "bold"), padx=14).pack(side="left", pady=8)
        s.btime = tk.Label(b, text="00:00", bg=C["bad"], fg="#ffd7d6", font=("Consolas", 11)); s.btime.pack(side="left", padx=6)
        tk.Button(b, text="Stop", command=s.stop_host, bg="white", fg=C["bad"], relief="flat", bd=0, font=(F, 10, "bold"), padx=14, cursor="hand2").pack(side="left", padx=12)
        b.protocol("WM_DELETE_WINDOW", s.stop_host)

    def consent(s, name, sas, cb):
        d = tk.Toplevel(s.root); d.title("Allow remote support?"); d.configure(bg=C["card"]); d.transient(s.root); d.attributes("-topmost", True); d.resizable(False, False)
        d.geometry(f"+{s.root.winfo_rootx() + 240}+{s.root.winfo_rooty() + 90}"); d.grab_set()
        done = lambda v: (d.destroy(), cb(v))
        b = tk.Frame(d, bg=C["card"]); b.pack(padx=32, pady=26)
        lbl(b, f"{name} wants to view your screen", 15, bold=True, wraplength=400).pack(fill="x")
        lbl(b, "They can only see your screen if you allow it. You can stop at any time.", 10, C["mute"], wraplength=400).pack(fill="x", pady=(4, 14))
        v = tk.Frame(b, bg=C["tint"]); v.pack(fill="x"); lbl(v, "VERIFICATION CODE — must match the technician's screen", 8, C["mute"], True).pack(fill="x", padx=14, pady=(10, 0))
        tk.Label(v, text=sas, bg=C["tint"], fg=C["brand"], font=("Consolas", 26, "bold")).pack(pady=(0, 10))
        Btn(b, "Allow view & control", lambda: done("control")).pack(fill="x", pady=(16, 6))
        Btn(b, "Allow view only", lambda: done("view"), "soft").pack(fill="x", pady=3)
        Btn(b, "Decline", lambda: done(None), "soft").pack(fill="x", pady=3)
        d.protocol("WM_DELETE_WINDOW", lambda: done(None))

    # ---------- viewer ----------
    def start_view(s):
        code = s.entry.get()
        if len([c for c in code if c.isdigit()]) != 9: return s.vpill.show("error", "enter the 9-digit code")
        from PIL import Image, ImageTk
        s.Image, s.ImageTk = Image, ImageTk; s.vpill.show("awaiting_consent")
        w = s.win = tk.Toplevel(s.root); w.title(f"{APP} — remote screen"); w.geometry("1100x700"); w.configure(bg="#0b1220")
        bar = tk.Frame(w, bg=C["nav"]); bar.pack(fill="x")
        s.vinfo = tk.Label(bar, text="●  Connecting…", bg=C["nav"], fg="white", font=(F, 10, "bold"), padx=14, pady=10); s.vinfo.pack(side="left")
        Btn(bar, "Disconnect", s.disconnect, "danger").pack(side="right", padx=10, pady=5)
        s.cv = tk.Canvas(w, bg="#0b1220", highlightthickness=0, cursor="crosshair"); s.cv.pack(fill="both", expand=True)
        s.box, s.latest, s.sched = (0, 0, 1, 1), None, False
        s.vs = ViewerSession(s.relay, s.nm.get().strip() or s.name, lambda st, **k: s.root.after(0, s.view_status, st, k), s.on_frame)
        send = lambda m: asyncio.run_coroutine_threadsafe(s.vs.send_input(m), s.loop)
        btns = {1: "left", 2: "middle", 3: "right"}
        def pos(e): x0, y0, bw, bh = s.box; return min(max((e.x - x0) / bw, 0), 1), min(max((e.y - y0) / bh, 0), 1)
        def mouse(a): return lambda e: send({"t": "mouse", "x": pos(e)[0], "y": pos(e)[1], "a": a, "b": None if a == "move" else btns.get(e.num)})
        for ev, a in (("<ButtonPress>", "down"), ("<ButtonRelease>", "up"), ("<Motion>", "move")): s.cv.bind(ev, mouse(a))
        def key(down):
            def h(e):
                k = KEYMAP.get(e.keysym.lower(), e.keysym.lower()) if len(e.keysym) > 1 else e.char
                if k: send({"t": "key", "k": k, "down": down})
            return h
        w.bind("<KeyPress>", key(True)); w.bind("<KeyRelease>", key(False)); w.protocol("WM_DELETE_WINDOW", s.disconnect)
        asyncio.run_coroutine_threadsafe(s.vs.run(code), s.loop)

    def on_frame(s, b):   # loop thread: keep only the newest frame
        s.latest = b
        if not s.sched: s.sched = True; s.root.after(0, s.draw)

    def draw(s):
        s.sched = False
        if not (s.win and s.latest): return
        try: img = s.Image.open(io.BytesIO(s.latest))
        except Exception: return
        cw, ch = max(s.cv.winfo_width(), 1), max(s.cv.winfo_height(), 1); k = min(cw / img.width, ch / img.height)
        w, h = max(int(img.width * k), 1), max(int(img.height * k), 1); s.box = ((cw - w) // 2, (ch - h) // 2, w, h)
        s.ph = s.ImageTk.PhotoImage(img.resize((w, h))); s.cv.delete("all"); s.cv.create_image(s.box[0], s.box[1], anchor="nw", image=s.ph)

    def view_status(s, st, k):
        s.vpill.show(st, f"verify {k['sas']}" if "sas" in k else k.get("msg", ""))
        if not s.win: return
        if st == "awaiting_consent": s.vinfo.config(text=f"●  Waiting for approval · verify {k['sas']}")
        elif st == "active": s.vinfo.config(text=f"●  Connected · {'view & control' if k['control'] else 'view only'} · verify {k['sas']}")
        else: s.vinfo.config(text="●  " + STATES[st][0]); s.latest = None; s.cv.delete("all")

    def disconnect(s):
        if s.vs: asyncio.run_coroutine_threadsafe(s.vs.bye(), s.loop)
        w, s.win = s.win, None
        if w: w.destroy()
        s.vpill.show("stopped")

def main():
    ap = argparse.ArgumentParser(description=APP); ap.add_argument("--relay", default="127.0.0.1:7000")
    ap.add_argument("--name", default=getpass.getuser()); ap.add_argument("--tls", action="store_true"); a = ap.parse_args()
    h, p = a.relay.rsplit(":", 1); App((h, int(p), a.tls), a.name).root.mainloop()

if __name__ == "__main__": main()

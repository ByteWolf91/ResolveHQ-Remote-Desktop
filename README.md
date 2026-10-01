# ResolveHQ Remote Desktop — attended remote-support MVP

Attended-only screen sharing + optional remote control. **No unattended access, no background service, no covert mode.**

## Run locally (3 terminals)
```bash
pip install -e .                       # Python 3.10+; Linux also needs python3-tk
python -m resolvehq.relay               # 1) relay on 127.0.0.1:7000
python -m resolvehq.app --name Alice    # 2) "Get help" tab -> Generate code   (the person being helped)
python -m resolvehq.app --name Bob      # 3) "Give help" tab -> enter code     (the technician)
python -m unittest discover -s tests -t .   # headless tests (need only `cryptography`)
```
Cross-network: run the relay on a public host (`--host 0.0.0.0`, ideally with `--cert/--key` and clients using `--tls`), then pass `--relay host:port`.

## Flow
1. Host clicks **Generate code** → relay issues a 9-digit code (5 min TTL, single use, 5 bad guesses/min/IP).
2. Viewer enters it → both sides run X25519 + HKDF (code mixed in as PSK) → ChaCha20-Poly1305 channel with key confirmation.
3. Both screens show a 6-digit **verification code**; the host reads it against the technician's before approving.
4. Host sees a consent dialog: **view + control / view only / decline**. No frame is captured or sent before that.
5. While active: red always-on-top banner with **Stop**; either side can end. Viewer input is dropped unless "control" was granted.

## Architecture
`proto.py` framing + crypto · `relay.py` code registry + opaque frame pipe · `session.py` consent/state machine (UI-free, tested) · `backends.py` capture (mss) + input (pynput) · `app.py` Tk UI.

## Platform permissions & limits
- **Windows:** capture/input work for normal windows. UIPI blocks injecting input into elevated (admin) windows and the UAC secure desktop; supporting that needs a signed service (not included).
- **Linux X11:** works via mss + XTest.
- **Linux Wayland:** mss/pynput **do not work** (by design). Proper support needs xdg-desktop-portal ScreenCast + RemoteDesktop (PipeWire), which prompts the user itself. Not implemented; use an X11 session for now.
- **macOS:** out of scope (needs Screen Recording/Accessibility grants).
- Capture is JPEG-per-frame at ~5 fps — a demo codec, not H.264/VP9.

## Security review
**Implemented and tested:** one-time/expiring/rate-limited codes; wrong-PSK handshake fails; tampered ciphertext rejected; per-direction keys with counter nonces; consent gate before capture; remote input validated/clamped; view-only enforced host-side; stop ends the session.
**Encryption claim:** traffic is encrypted between the two peers and the relay forwards ciphertext only. I'm not calling it "audited end-to-end encryption": the design is custom and unreviewed by a cryptographer.
**Known gaps:**
- The code is a low-entropy PSK. A malicious relay can guess it *offline* after MITM-ing → this is why the SAS comparison exists; a real fix is a PAKE (CPace/SPAKE2). The SAS check is manual and only effective if users actually compare it.
- Pairing metadata and the code travel in cleartext to the relay unless TLS is enabled (TLS path is written, **not tested**).
- No relay-side global rate limit, no persistent identity/pinning, no audit log, no clipboard/file transfer (deliberately).
- The Tk UI, mss and pynput backends were **not run** in the build sandbox (no display); only headless logic is tested.

## Packaging
CI (`.github/workflows/build.yml`) runs tests and builds PyInstaller bundles for Windows and Ubuntu.
Locally: `pip install -e ".[build]" && pyinstaller --windowed --name ResolveHQ --collect-submodules pynput resolvehq/app.py`.
Not included: MSI/NSIS installer, `.deb`/AppImage, code signing (unsigned Windows builds will trigger SmartScreen).


## Windows build
Push this repository to GitHub, open Actions, run “Build ResolveHQ for Windows”, then download the ResolveHQ-Windows artifact. It contains ResolveHQ.exe and ResolveHQ-Relay.exe. For two computers on different networks, host the relay on a reachable server and use appropriate firewall rules; do not expose the unencrypted default relay directly to the public internet.

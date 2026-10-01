"""Framing + authenticated encryption. X25519 + HKDF (pairing code as PSK) -> ChaCha20-Poly1305."""
import hashlib, json, struct
from cryptography.hazmat.primitives import hashes, serialization as ser
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

MAX_FRAME = 8 << 20

async def send_frame(w, data: bytes):
    w.write(struct.pack(">I", len(data)) + data); await w.drain()

async def recv_frame(r) -> bytes:
    (n,) = struct.unpack(">I", await r.readexactly(4))
    if n > MAX_FRAME: raise ValueError("frame too large")
    return await r.readexactly(n)

def norm_code(c: str) -> str: return "".join(ch for ch in c if ch.isdigit())

class Channel:
    """Per-direction keys + implicit counter nonces: tamper/replay/reorder => InvalidTag."""
    def __init__(self, r, w, sk, rk): self.r, self.w, self.s, self.k, self.sn, self.rn = r, w, sk, rk, 0, 0
    async def send(self, msg: dict, blob: bytes = b""):
        h = json.dumps(msg).encode()
        nonce = b"\0\0\0\0" + struct.pack(">Q", self.sn); self.sn += 1
        await send_frame(self.w, self.s.encrypt(nonce, struct.pack(">I", len(h)) + h + blob, None))
    async def recv(self):
        ct = await recv_frame(self.r)
        pt = self.k.decrypt(b"\0\0\0\0" + struct.pack(">Q", self.rn), ct, None); self.rn += 1
        (n,) = struct.unpack(">I", pt[:4]); return json.loads(pt[4:4 + n]), pt[4 + n:]

async def handshake(r, w, code: str, role: str):
    """Returns (Channel, SAS). SAS = 6 digits both people compare aloud to detect a relay MITM."""
    priv = X25519PrivateKey.generate()
    mine = priv.public_key().public_bytes(ser.Encoding.Raw, ser.PublicFormat.Raw)
    await send_frame(w, mine); theirs = await recv_frame(r)
    if len(theirs) != 32: raise ValueError("bad key")
    shared = priv.exchange(X25519PublicKey.from_public_bytes(theirs))  # rejects low-order points
    hp, vp = (mine, theirs) if role == "host" else (theirs, mine)
    okm = HKDF(hashes.SHA256(), 68, hashlib.sha256(hp + vp).digest(),
               b"resolvehq/v1|" + norm_code(code).encode()).derive(shared)
    a, b = ChaCha20Poly1305(okm[:32]), ChaCha20Poly1305(okm[32:64])
    ch = Channel(r, w, *((a, b) if role == "host" else (b, a)))
    await ch.send({"t": "confirm"})
    if (await ch.recv())[0].get("t") != "confirm": raise ValueError("key confirmation failed")
    return ch, f"{int.from_bytes(okm[64:], 'big') % 10**6:06d}"

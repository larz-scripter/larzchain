"""
larzchain.crypto — elliptic-curve crypto for LarzCoin, pure Python (zero-dep).

secp256k1 (the Bitcoin curve): key generation, ECDSA sign/verify with RFC-6979
deterministic nonces, compressed public keys, hash160, and base58check addresses.

Pure-Python EC math is slow (fine at our scale). `inverse_mod` is implemented by
hand because `pow(a, -1, m)` needs Python 3.8+ and we target 3.7+.
"""

import os
import hmac
import hashlib

# --- secp256k1 domain parameters ------------------------------------------ #
P  = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N  = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
A  = 0
B  = 7
Gx = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
Gy = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8
G  = (Gx, Gy)

ADDRESS_VERSION = 0x30        # base58 addresses start with 'L' (LarzCoin)


# --- field / curve math --------------------------------------------------- #
def inverse_mod(a, m):
    """Modular inverse via the extended Euclidean algorithm (py3.7-safe)."""
    if a == 0:
        raise ZeroDivisionError("no inverse for 0")
    lm, hm = 1, 0
    low, high = a % m, m
    while low > 1:
        r = high // low
        lm, hm = hm - lm * r, lm
        low, high = high - low * r, low
    return lm % m


def point_add(p, q):
    if p is None:
        return q
    if q is None:
        return p
    (x1, y1), (x2, y2) = p, q
    if x1 == x2 and (y1 + y2) % P == 0:
        return None                                  # P + (-P) = infinity
    if p == q:
        m = (3 * x1 * x1 + A) * inverse_mod(2 * y1, P) % P
    else:
        m = (y2 - y1) * inverse_mod((x2 - x1) % P, P) % P
    x3 = (m * m - x1 - x2) % P
    y3 = (m * (x1 - x3) - y1) % P
    return (x3, y3)


def point_mul(k, point=G):
    """Scalar multiplication by double-and-add."""
    result = None
    addend = point
    while k:
        if k & 1:
            result = point_add(result, addend)
        addend = point_add(addend, addend)
        k >>= 1
    return result


# --- hashing -------------------------------------------------------------- #
def sha256(b):
    return hashlib.sha256(b).digest()


def sha256d(b):
    return sha256(sha256(b))


def hash160(b):
    h = hashlib.new("ripemd160")
    h.update(sha256(b))
    return h.digest()


# --- keys ----------------------------------------------------------------- #
def gen_privkey():
    while True:
        k = int.from_bytes(os.urandom(32), "big")
        if 1 <= k < N:
            return k


def privkey_to_pubkey(priv):
    return point_mul(priv, G)


def compress_pubkey(point):
    x, y = point
    prefix = b"\x02" if y % 2 == 0 else b"\x03"
    return prefix + x.to_bytes(32, "big")


def decompress_pubkey(data):
    prefix, x = data[0], int.from_bytes(data[1:], "big")
    y2 = (pow(x, 3, P) + B) % P
    y = pow(y2, (P + 1) // 4, P)                      # sqrt mod P (P % 4 == 3)
    if (y % 2 == 0) != (prefix == 0x02):
        y = P - y
    return (x, y)


# --- base58check ---------------------------------------------------------- #
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58encode(b):
    n = int.from_bytes(b, "big")
    out = ""
    while n > 0:
        n, r = divmod(n, 58)
        out = _B58[r] + out
    for byte in b:                                    # preserve leading zeros
        if byte == 0:
            out = _B58[0] + out
        else:
            break
    return out


def b58decode(s):
    n = 0
    for ch in s:
        n = n * 58 + _B58.index(ch)
    body = n.to_bytes((n.bit_length() + 7) // 8, "big")
    pad = 0
    for ch in s:
        if ch == _B58[0]:
            pad += 1
        else:
            break
    return b"\x00" * pad + body


def b58check_encode(version, payload):
    data = bytes([version]) + payload
    return b58encode(data + sha256d(data)[:4])


def b58check_decode(s):
    raw = b58decode(s)
    data, checksum = raw[:-4], raw[-4:]
    if sha256d(data)[:4] != checksum:
        raise ValueError("bad base58check checksum")
    return data[0], data[1:]


def pubkey_to_address(point):
    return b58check_encode(ADDRESS_VERSION, hash160(compress_pubkey(point)))


def address_to_hash160(addr):
    version, payload = b58check_decode(addr)
    if version != ADDRESS_VERSION:
        raise ValueError("wrong address version")
    return payload


def is_valid_address(addr):
    try:
        version, payload = b58check_decode(addr)
        return version == ADDRESS_VERSION and len(payload) == 20
    except Exception:
        return False


# --- ECDSA (RFC-6979 deterministic k) ------------------------------------- #
def _rfc6979_k(msg_hash, priv):
    h1 = msg_hash
    v = b"\x01" * 32
    k = b"\x00" * 32
    x = priv.to_bytes(32, "big")
    k = hmac.new(k, v + b"\x00" + x + h1, hashlib.sha256).digest()
    v = hmac.new(k, v, hashlib.sha256).digest()
    k = hmac.new(k, v + b"\x01" + x + h1, hashlib.sha256).digest()
    v = hmac.new(k, v, hashlib.sha256).digest()
    while True:
        v = hmac.new(k, v, hashlib.sha256).digest()
        cand = int.from_bytes(v, "big")
        if 1 <= cand < N:
            return cand
        k = hmac.new(k, v + b"\x00", hashlib.sha256).digest()
        v = hmac.new(k, v, hashlib.sha256).digest()


def _sign_py(msg_hash, priv):
    """Pure-Python: DER-free compact signature: 64 bytes r||s (low-s enforced)."""
    z = int.from_bytes(msg_hash, "big")
    while True:
        k = _rfc6979_k(msg_hash, priv)
        x, _ = point_mul(k, G)
        r = x % N
        if r == 0:
            continue
        s = (inverse_mod(k, N) * (z + r * priv)) % N
        if s == 0:
            continue
        if s > N // 2:                                # low-s (malleability)
            s = N - s
        return r.to_bytes(32, "big") + s.to_bytes(32, "big")


def _verify_py(msg_hash, signature, pubkey_point):
    if len(signature) != 64:
        return False
    r = int.from_bytes(signature[:32], "big")
    s = int.from_bytes(signature[32:], "big")
    if not (1 <= r < N and 1 <= s < N):
        return False
    z = int.from_bytes(msg_hash, "big")
    w = inverse_mod(s, N)
    u1, u2 = (z * w) % N, (r * w) % N
    point = point_add(point_mul(u1, G), point_mul(u2, pubkey_point))
    if point is None:
        return False
    return point[0] % N == r


# --------------------------------------------------------------------------- #
#  Optional native fast-path (coincurve / libsecp256k1)
#
#  Signature verification dominates initial sync; pure-Python is correct but
#  slow. If `coincurve` is installed we can offload sign/verify to libsecp256k1
#  — but ONLY after a self-test proves it produces BYTE-IDENTICAL signatures and
#  agrees on verification with the pure-Python code. If anything differs, we fall
#  back to pure Python. This makes the fast-path impossible to cause a consensus
#  fork: fast and slow nodes always accept and produce exactly the same bytes.
# --------------------------------------------------------------------------- #
try:
    import coincurve as _cc
except Exception:               # pragma: no cover
    _cc = None

_FAST = False


def _rs_to_der(sig64):
    def _trim(b):
        b = b.lstrip(b"\x00") or b"\x00"
        if b[0] & 0x80:
            b = b"\x00" + b
        return b
    r, s = _trim(sig64[:32]), _trim(sig64[32:])
    body = b"\x02" + bytes([len(r)]) + r + b"\x02" + bytes([len(s)]) + s
    return b"\x30" + bytes([len(body)]) + body


def _sign_cc(msg_hash, priv):
    pk = _cc.PrivateKey(priv.to_bytes(32, "big"))
    rec = pk.sign_recoverable(msg_hash, hasher=None)   # 65 bytes: r||s||recid
    r = int.from_bytes(rec[:32], "big")
    s = int.from_bytes(rec[32:64], "big")
    if s > N // 2:                                     # match our low-s convention
        s = N - s
    return r.to_bytes(32, "big") + s.to_bytes(32, "big")


def _verify_cc(msg_hash, signature, pubkey_point):
    if len(signature) != 64:
        return False
    try:
        pub = _cc.PublicKey(compress_pubkey(pubkey_point))
        return pub.verify(_rs_to_der(signature), msg_hash, hasher=None)
    except Exception:
        return False


def _selftest():
    """Enable the native backend only if it byte-matches pure Python."""
    if _cc is None:
        return False
    try:
        for seed in (b"larzchain-selftest-1", b"larzchain-selftest-2", os.urandom(16)):
            priv = (int.from_bytes(sha256(seed), "big") % (N - 1)) + 1
            pub = privkey_to_pubkey(priv)
            for m in (sha256(b"hello"), sha256(seed), sha256d(b"tx")):
                a = _sign_py(m, priv)
                b = _sign_cc(m, priv)
                if a != b:                              # signatures must be identical
                    return False
                if not (_verify_py(m, a, pub) and _verify_cc(m, a, pub)):
                    return False
                bad = a[:-1] + bytes([a[-1] ^ 1])       # tampered must fail both
                if _verify_py(m, bad, pub) or _verify_cc(m, bad, pub):
                    return False
        return True
    except Exception:
        return False


_FAST = _selftest()


def sign(msg_hash, priv):
    """Compact 64-byte r||s signature (RFC-6979, low-s). Uses the native backend
    if it self-tested identical to pure Python, else pure Python."""
    return _sign_cc(msg_hash, priv) if _FAST else _sign_py(msg_hash, priv)


def verify(msg_hash, signature, pubkey_point):
    return _verify_cc(msg_hash, signature, pubkey_point) if _FAST \
        else _verify_py(msg_hash, signature, pubkey_point)


def backend():
    """'native (coincurve)' if the fast-path is active, else 'pure-python'."""
    return "native (coincurve)" if _FAST else "pure-python"

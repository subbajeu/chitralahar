"""TOTP two-factor auth (RFC 6238) — stdlib only, works with any authenticator app."""
import base64
import hashlib
import hmac
import secrets
import struct
import time

STEP = 30  # seconds per code


def new_secret() -> str:
    """A fresh base32 secret for the authenticator app."""
    return base64.b32encode(secrets.token_bytes(20)).decode()


def _code(secret: str, counter: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    off = digest[-1] & 0xF
    return "%06d" % ((struct.unpack(">I", digest[off:off + 4])[0] & 0x7FFFFFFF) % 1_000_000)


def verify(secret: str, code: str, last_counter: int = 0) -> int:
    """Return the matched time-step counter, or 0 if the code is wrong.

    Accepts ±1 step of clock drift. Counters at or below last_counter are
    rejected so a captured code can't be replayed within its window.
    """
    code = (code or "").strip().replace(" ", "")
    if len(code) != 6 or not code.isdigit() or not secret:
        return 0
    now = int(time.time()) // STEP
    for counter in (now, now - 1, now + 1):
        if counter > last_counter and hmac.compare_digest(_code(secret, counter), code):
            return counter
    return 0


def otpauth_uri(secret: str, username: str, issuer: str = "Chitralahar") -> str:
    from urllib.parse import quote
    return "otpauth://totp/%s:%s?secret=%s&issuer=%s" % (
        quote(issuer), quote(username), secret, quote(issuer))


if __name__ == "__main__":  # self-check
    s = new_secret()
    now = int(time.time()) // STEP
    good = _code(s, now)
    assert verify(s, good) == now
    assert verify(s, good, last_counter=now) == 0        # replay rejected
    assert verify(s, "000000") in (0, now)               # wrong code (barring 1e-6 luck)
    assert verify(s, _code(s, now - 1)) == now - 1       # drift window
    print("totp ok")

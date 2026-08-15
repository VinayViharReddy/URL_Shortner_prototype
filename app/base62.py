"""Base62 encode/decode. Counter (base10) <-> short code (base62)."""

ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
BASE = len(ALPHABET)
_INDEX = {c: i for i, c in enumerate(ALPHABET)}


def encode(n: int) -> str:
    if n < 0:
        raise ValueError("counter must be non-negative")
    if n == 0:
        return ALPHABET[0]
    out = []
    while n:
        n, rem = divmod(n, BASE)
        out.append(ALPHABET[rem])
    return "".join(reversed(out))


def decode(code: str) -> int:
    n = 0
    for ch in code:
        if ch not in _INDEX:
            raise ValueError(f"invalid base62 char: {ch!r}")
        n = n * BASE + _INDEX[ch]
    return n

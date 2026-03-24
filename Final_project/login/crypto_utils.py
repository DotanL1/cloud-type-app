# crypto_utils.py
from __future__ import annotations

import hmac
import hashlib
import socket
from Cryptodome.Cipher import AES
from Cryptodome.Util.Padding import pad, unpad
from Cryptodome.Random import get_random_bytes

from tcp_by_size import recv_by_size, send_with_size  # your framing

AES_DEBUG = True
LEN_TO_PRINT = 300


def _to_bytes(x: str | bytes) -> bytes:
    return x.encode() if isinstance(x, str) else x


def _kdf(master: str | bytes) -> tuple[bytes, bytes]:
    """
    Derive two independent 32-byte keys from master:
      - enc_key for AES
      - mac_key for HMAC
    """
    m = _to_bytes(master)
    enc_key = hashlib.sha256(b"enc||" + m).digest()
    mac_key = hashlib.sha256(b"mac||" + m).digest()
    return enc_key, mac_key


def send_with_AES(sock: socket.socket, data: str | bytes, key: str | bytes, iv: bytes | None = None) -> None:
    data_b = _to_bytes(data)
    enc_key, mac_key = _kdf(key)

    if iv is None:
        iv = get_random_bytes(16)

    cipher = AES.new(enc_key, AES.MODE_CBC, iv)
    ct = cipher.encrypt(pad(data_b, AES.block_size))

    # Encrypt-then-MAC: tag = HMAC(mac_key, iv||ct)
    tag = hmac.new(mac_key, iv + ct, hashlib.sha256).digest()

    if AES_DEBUG:
        print(f"\nSent AES ({len(data_b)})>>> {data_b[:min(len(data_b), LEN_TO_PRINT)]!r}")

    # send: iv(16) || ct || tag(32)
    send_with_size(sock, iv + ct + tag)


def recv_with_AES(sock: socket.socket, key: str | bytes) -> bytes:
    enc_key, mac_key = _kdf(key)

    blob = recv_by_size(sock)
    if not blob:
        return b""

    if len(blob) < 16 + 32:
        raise ValueError("Ciphertext too short")

    iv = blob[:16]
    tag = blob[-32:]
    ct = blob[16:-32]

    # verify tag BEFORE decrypt
    expected = hmac.new(mac_key, iv + ct, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        raise ValueError("Bad HMAC (message modified or wrong key)")

    cipher = AES.new(enc_key, AES.MODE_CBC, iv)
    pt_padded = cipher.decrypt(ct)
    pt = unpad(pt_padded, AES.block_size)

    if AES_DEBUG:
        print(f"\nRecv AES ({len(pt)})>>> {pt[:min(len(pt), LEN_TO_PRINT)]!r}")

    return pt

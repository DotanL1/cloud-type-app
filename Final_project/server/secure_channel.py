# secure_channel.py
from __future__ import annotations

import os
import pickle
import hashlib
from dataclasses import dataclass
from typing import Optional, Literal, Tuple

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import dh, rsa, padding

from tcp_by_size import send_with_size, recv_by_size
from crypto_utils import send_with_AES, recv_with_AES  


SEP = b"||"
Method = Literal["dh", "rsa"]

CMD_HELO = b"HELO" 
CMD_KEYX = b"KEYX"  
CMD_OKAY = b"OKAY"   


def _kdf_master(material: bytes) -> bytes:
    """
    Produce a stable 32-byte session key material from shared secret.
    crypto_utils.hash_key() will hash again, which is fine.
    """
    return hashlib.sha256(material).digest()


@dataclass
class _KXCtx:
    method: Method
    dh_private: Optional[dh.DHPrivateKey] = None
    rsa_private: Optional[rsa.RSAPrivateKey] = None



def _kx_start_dh(dh_key_size: int = 2048) -> Tuple[bytes, _KXCtx]:
    """
    Initiator creates DH params + keypair and sends (params + pub).
    """
    params = dh.generate_parameters(generator=2, key_size=dh_key_size, backend=default_backend())
    priv = params.generate_private_key()
    pub = priv.public_key()

    payload = {
        "m": "dh",
        "params": params.parameter_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.ParameterFormat.PKCS3,
        ),
        "pub": pub.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ),
    }
    msg = CMD_KEYX + SEP + pickle.dumps(payload)
    return msg, _KXCtx(method="dh", dh_private=priv)


def _kx_handle_dh(msg: bytes, ctx: Optional[_KXCtx]) -> Tuple[bytes, Optional[bytes]]:
    """
    Returns: (master_key, reply_msg_or_None)
    - Responder: receives init dict -> computes master, returns reply with its pubkey
    - Initiator: receives pubkey PEM -> computes master, no reply
    """
    cmd, payload = msg.split(SEP, 1)
    if cmd != CMD_KEYX:
        raise ValueError("Expected KEYX message")

    init = None
    try:
        init = pickle.loads(payload)
    except Exception:
        init = None

    if ctx is None and isinstance(init, dict) and init.get("m") == "dh":
        params = serialization.load_pem_parameters(init["params"], backend=default_backend())
        peer_pub = serialization.load_pem_public_key(init["pub"], backend=default_backend())

        my_priv = params.generate_private_key()
        my_pub = my_priv.public_key()

        shared = my_priv.exchange(peer_pub)
        master = _kdf_master(shared)

        reply_pub = my_pub.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        reply = CMD_KEYX + SEP + reply_pub
        return master, reply

    if ctx is not None and ctx.method == "dh" and ctx.dh_private is not None and init is None:
        peer_pub = serialization.load_pem_public_key(payload, backend=default_backend())
        shared = ctx.dh_private.exchange(peer_pub)
        master = _kdf_master(shared)
        return master, None

    raise ValueError("Invalid DH handshake message/state")


# -------------------- RSA (key transport) --------------------

def _kx_start_rsa(rsa_key_size: int = 2048) -> Tuple[bytes, _KXCtx]:
    """
    The side that wants to DECRYPT starts by sending its RSA public key.
    """
    priv = rsa.generate_private_key(public_exponent=65537, key_size=rsa_key_size, backend=default_backend())
    pub = priv.public_key()

    payload = {
        "m": "rsa",
        "pub": pub.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ),
    }
    msg = CMD_KEYX + SEP + pickle.dumps(payload)
    return msg, _KXCtx(method="rsa", rsa_private=priv)


def _kx_handle_rsa(msg: bytes, ctx: Optional[_KXCtx]) -> Tuple[bytes, Optional[bytes]]:
    """
    Returns: (master_key, reply_msg_or_None)

    Flow:
      - Decrypter sends KEYX||{m:"rsa", pub:<pem>}  (ctx holds rsa_private)
      - Encrypter receives that, generates random master, replies KEYX||<rsa-encrypted master>
      - Decrypter receives encrypted master, decrypts, done
    """
    cmd, payload = msg.split(SEP, 1)
    if cmd != CMD_KEYX:
        raise ValueError("Expected KEYX message")

    init = None
    try:
        init = pickle.loads(payload)
    except Exception:
        init = None

    if ctx is None and isinstance(init, dict) and init.get("m") == "rsa":
        peer_pub = serialization.load_pem_public_key(init["pub"], backend=default_backend())

        master = os.urandom(32)
        enc = peer_pub.encrypt(
            master,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        reply = CMD_KEYX + SEP + enc
        return _kdf_master(master), reply  

    if ctx is not None and ctx.method == "rsa" and ctx.rsa_private is not None and init is None:
        master = ctx.rsa_private.decrypt(
            payload,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        return _kdf_master(master), None

    raise ValueError("Invalid RSA handshake message/state")


# -------------------- SecureChannel --------------------

class SecureChannel:
    """
    Wraps a connected TCP socket.
    - Performs DH or RSA key exchange once (plaintext frames: HELO/KEYX/OKAY)
    - After that, ALL traffic uses crypto_utils.send_with_AES / recv_with_AES
      (which themselves use send_with_size/recv_by_size).
    """
    def __init__(self, sock):
        self.sock = sock
        self._session_key: Optional[bytes] = None

    @property
    def ready(self) -> bool:
        return self._session_key is not None

    def handshake(self, method: Method = "dh", *, i_am_initiator: bool) -> None:
        """
        Call ONCE per connected socket.

        DH:
          - initiator sends DH init (params+pub)
          - responder replies pub
          - initiator finalizes

        RSA:
          - "initiator" in this RSA design is the DECRYPTER (sends RSA pub first)
          - other side returns encrypted master
          - decrypter finalizes
        """
        # 1) negotiate method
        if i_am_initiator:
            send_with_size(self.sock, CMD_HELO + SEP + method.encode())
            other = recv_by_size(self.sock)
            if not other.startswith(CMD_HELO + SEP):
                raise ValueError("Expected HELO reply")
            other_method = other.split(SEP, 1)[1].decode()
            if other_method != method:
                raise ValueError(f"Method mismatch: me={method} peer={other_method}")
        else:
            other = recv_by_size(self.sock)
            if not other.startswith(CMD_HELO + SEP):
                raise ValueError("Expected HELO")
            other_method = other.split(SEP, 1)[1].decode()
            if other_method != method:
                raise ValueError(f"Method mismatch: expected {method} got {other_method}")
            send_with_size(self.sock, CMD_HELO + SEP + method.encode())

        if method == "dh":
            if i_am_initiator:
                m1, ctx = _kx_start_dh()
                send_with_size(self.sock, m1)
                m2 = recv_by_size(self.sock)
                session_key, _ = _kx_handle_dh(m2, ctx)
            else:
                m1 = recv_by_size(self.sock)
                session_key, m2 = _kx_handle_dh(m1, None)
                send_with_size(self.sock, m2)

        elif method == "rsa":
            if i_am_initiator:
                m1, ctx = _kx_start_rsa()
                send_with_size(self.sock, m1)
                m2 = recv_by_size(self.sock)
                session_key, _ = _kx_handle_rsa(m2, ctx)
            else:
                m1 = recv_by_size(self.sock)
                session_key, m2 = _kx_handle_rsa(m1, None)
                send_with_size(self.sock, m2)

        else:
            raise ValueError("method must be 'dh' or 'rsa'")

        self._session_key = session_key

        # 3) sync
        send_with_size(self.sock, CMD_OKAY + SEP)
        ok2 = recv_by_size(self.sock)
        if ok2 != CMD_OKAY + SEP:
            raise ValueError("Handshake did not finish cleanly")

    # ---- encrypted data path (AES via crypto_utils) ----

    def send(self, plaintext: bytes | str) -> None:
        if not self.ready:
            raise RuntimeError("SecureChannel not handshaked yet")
        send_with_AES(self.sock, plaintext, self._session_key)

    def recv(self) -> bytes:
        if not self.ready:
            raise RuntimeError("SecureChannel not handshaked yet")
        return recv_with_AES(self.sock, self._session_key)

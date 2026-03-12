from __future__ import annotations
import base64
import json
import logging
import os
from capsule_memory.exceptions import CapsuleIntegrityError
from capsule_memory.models.capsule import Capsule

logger = logging.getLogger(__name__)


class CapsuleCrypto:
    """Capsule encryption/decryption using Fernet with PBKDF2 key derivation."""

    @staticmethod
    def _derive_key(passphrase: str, salt: bytes) -> bytes:
        """Derive a Fernet-compatible key from passphrase."""
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes

        from capsule_memory.models.capsule import _K

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=517000,
        )
        key_material = kdf.derive(passphrase.encode() + _K)
        return base64.urlsafe_b64encode(key_material)

    @staticmethod
    def encrypt(capsule: Capsule, passphrase: str) -> Capsule:
        """
        Encrypt a capsule's payload using Fernet/PBKDF2.

        Args:
            capsule: The capsule to encrypt.
            passphrase: User-provided passphrase.

        Returns:
            Modified capsule with encrypted payload.
        """
        from cryptography.fernet import Fernet

        capsule.integrity.pre_encrypt_checksum = capsule.compute_checksum()

        payload_bytes = json.dumps(
            capsule.payload, sort_keys=True, ensure_ascii=False, default=str
        ).encode()

        raw_salt = os.urandom(16)
        capsule.integrity.salt = base64.b64encode(raw_salt).decode()

        key = CapsuleCrypto._derive_key(passphrase, raw_salt)
        cipher = Fernet(key).encrypt(payload_bytes)

        capsule.payload = {"encrypted_data": base64.b64encode(cipher).decode()}
        capsule.integrity.encrypted = True
        capsule.integrity.encryption_algo = "Fernet/PBKDF2+CMNamespace"
        capsule.integrity.checksum = ""

        return capsule

    @staticmethod
    def decrypt(capsule: Capsule, passphrase: str) -> Capsule:
        """
        Decrypt a capsule's payload.

        Args:
            capsule: The encrypted capsule.
            passphrase: User-provided passphrase.

        Returns:
            Modified capsule with decrypted payload.

        Raises:
            CapsuleIntegrityError: When checksum verification fails after decryption.
        """
        from cryptography.fernet import Fernet

        raw_salt = base64.b64decode(capsule.integrity.salt)
        key = CapsuleCrypto._derive_key(passphrase, raw_salt)

        cipher_data = base64.b64decode(capsule.payload["encrypted_data"])
        decrypted = Fernet(key).decrypt(cipher_data)

        capsule.payload = json.loads(decrypted)
        capsule.integrity.encrypted = False

        computed = capsule.compute_checksum()
        if (
            capsule.integrity.pre_encrypt_checksum
            and computed != capsule.integrity.pre_encrypt_checksum
        ):
            raise CapsuleIntegrityError(
                f"Checksum mismatch after decryption: "
                f"expected {capsule.integrity.pre_encrypt_checksum}, got {computed}"
            )

        return capsule

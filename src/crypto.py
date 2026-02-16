import os
import json
import base64
import secrets
from pathlib import Path
from typing import Tuple
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend


class CryptoError(Exception):
    pass


class InvalidPasswordError(CryptoError):
    pass


class KeyManager:
    PBKDF2_ITERATIONS = 480000
    SALT_SIZE = 16

    def __init__(self):
        self.salt = secrets.token_bytes(self.SALT_SIZE)

    def _derive_key(self, password: str) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.salt,
            iterations=self.PBKDF2_ITERATIONS,
            backend=default_backend()
        )
        return base64.urlsafe_b64encode(kdf.derive(password.encode()))

    def encrypt(self, private_key: str, password: str) -> dict:
        if not private_key:
            raise ValueError("Private key cannot be empty")
        if not password or len(password) < 8:
            raise ValueError("Password must be at least 8 characters")
        key = private_key.strip().lower()
        if key.startswith("0x"):
            key = key[2:]
        try:
            int(key, 16)
        except ValueError:
            raise ValueError("Invalid private key format")
        cipher = Fernet(self._derive_key(password))
        encrypted = cipher.encrypt(key.encode())
        encrypted_b64 = base64.urlsafe_b64encode(encrypted).decode()
        return {
            "version": 1,
            "salt": base64.urlsafe_b64encode(self.salt).decode(),
            "encrypted": encrypted_b64,
            "key_length": len(key)
        }

    def decrypt(self, encrypted_data: dict, password: str) -> str:
        try:
            self.salt = base64.urlsafe_b64decode(encrypted_data["salt"].encode())
            encrypted_b64 = encrypted_data["encrypted"]
            cipher = Fernet(self._derive_key(password))
            decrypted = cipher.decrypt(base64.urlsafe_b64decode(encrypted_b64))
            key = decrypted.decode()
            return f"0x{key}"
        except InvalidToken:
            raise InvalidPasswordError("Invalid password or corrupted data")
        except (KeyError, ValueError) as e:
            raise CryptoError(f"Invalid encrypted data: {e}")

    def encrypt_and_save(self, private_key: str, password: str, filepath: str) -> Path:
        encrypted_data = self.encrypt(private_key, password)
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(encrypted_data, f, indent=2)
        os.chmod(path, 0o600)
        return path

    def load_and_decrypt(self, password: str, filepath: str) -> str:
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Encrypted key file not found: {filepath}")
        with open(path, 'r') as f:
            encrypted_data = json.load(f)
        return self.decrypt(encrypted_data, password)

    def generate_new_salt(self) -> None:
        self.salt = secrets.token_bytes(self.SALT_SIZE)


def verify_private_key(private_key: str) -> Tuple[bool, str]:
    key = private_key.strip().lower()
    if key.startswith("0x"):
        key = key[2:]
    if len(key) != 64:
        return False, "Key must be 64 hex characters"
    try:
        int(key, 16)
    except ValueError:
        return False, "Key contains invalid characters"
    return True, f"0x{key}"


KeyStore = KeyManager

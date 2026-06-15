from __future__ import annotations

from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from config import DATABASE_PATH


class SSIDCrypto:
    def __init__(self, key_path: str | None = None):
        self.key_path = Path(key_path) if key_path else Path(DATABASE_PATH).with_suffix(".key")
        # Ensure the parent directory exists before any file operations
        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        self._fernet = Fernet(self._load_or_create_key())

    def _load_or_create_key(self) -> bytes:
        if self.key_path.exists():
            return self.key_path.read_bytes().strip()

        key = Fernet.generate_key()
        self.key_path.write_bytes(key)
        return key

    def encrypt(self, ssid: str | None) -> str | None:
        if not ssid:
            return ssid
        if self.is_encrypted(ssid):
            return ssid
        token = self._fernet.encrypt(ssid.encode("utf-8")).decode("utf-8")
        return f"enc:{token}"

    def decrypt(self, stored_value: str | None) -> str | None:
        if not stored_value:
            return stored_value
        if not self.is_encrypted(stored_value):
            return stored_value

        token = stored_value[4:]
        try:
            return self._fernet.decrypt(token.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            raise ValueError("Stored SSID could not be decrypted with the current key")

    @staticmethod
    def is_encrypted(value: str | None) -> bool:
        return bool(value) and value.startswith("enc:")
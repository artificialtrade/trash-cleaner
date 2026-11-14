from __future__ import annotations

import json

SERVICE_NAME = "trash-cleaner-mail-review"


class CredentialStore:
    """OS-backed credential storage using Windows Credential Manager/keyring."""

    def __init__(self, service: str = SERVICE_NAME) -> None:
        self.service = service

    def get(self, account: str, key: str) -> str | None:
        import keyring

        return keyring.get_password(self.service, f"{account}:{key}")

    def set(self, account: str, key: str, value: str) -> None:
        import keyring

        keyring.set_password(self.service, f"{account}:{key}", value)

    def delete(self, account: str, key: str) -> None:
        import keyring

        try:
            import keyring.errors

            keyring.delete_password(self.service, f"{account}:{key}")
        except keyring.errors.PasswordDeleteError:
            pass

    def get_json(self, account: str, key: str) -> dict | None:
        value = self.get(account, key)
        if not value:
            return None
        try:
            data = json.loads(value)
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    def set_json(self, account: str, key: str, value: dict) -> None:
        self.set(account, key, json.dumps(value))

    def clear_account(self, account: str) -> None:
        for key in ("token", "email", "password", "msal_cache"):
            self.delete(account, key)

from __future__ import annotations

import email
import email.utils
import imaplib
import json
import os
import shutil
import threading
from abc import ABC, abstractmethod
from datetime import datetime
from email.header import decode_header, make_header
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from mail_review.models import MessageRecord
from mail_review.services.action_log import app_data_dir
from mail_review.services.credentials import CredentialStore

ProgressCallback = Callable[[int, int | None], None]


def _header_value(headers: dict[str, str], name: str) -> str:
    return headers.get(name.lower(), "")


def _decode(value: str) -> str:
    try:
        return str(make_header(decode_header(value)))
    except (UnicodeDecodeError, ValueError):
        return value


def _parse_sender(value: str) -> tuple[str, str, str]:
    name, address = email.utils.parseaddr(value)
    return MessageRecord.derive_sender_parts(_decode(name), address)


class MailProvider(ABC):
    """Provider contract used by the UI and background mailbox loader."""

    provider_name = ""

    @abstractmethod
    def authenticate(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def load_messages(
        self,
        progress: ProgressCallback,
        cancel: threading.Event,
        pause: threading.Event,
    ) -> list[MessageRecord]:
        raise NotImplementedError

    @abstractmethod
    def move_to_trash(self, message: MessageRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def restore(self, message: MessageRecord) -> None:
        raise NotImplementedError

    def disconnect(self) -> None:
        """Release provider resources."""


class GmailProvider(MailProvider):
    provider_name = "Gmail"

    def __init__(self, credentials: CredentialStore | None = None) -> None:
        self.credentials = credentials or CredentialStore()
        self.service = None
        self.email_address = ""

    def _client_secret_path(self) -> Path:
        configured = os.environ.get("TRASH_CLEANER_GMAIL_CLIENT_SECRET")
        path = Path(configured) if configured else app_data_dir() / "gmail-client-secret.json"
        if path.exists():
            return path

        import tkinter as tk
        from tkinter import filedialog, messagebox

        root = tk._default_root
        messagebox.showinfo(
            "Gmail setup required",
            "Google OAuth needs the Desktop app client-secret JSON downloaded from Google Cloud.\n\n"
            "Choose that JSON file in the next window. It will be copied to your local app-data folder.",
            parent=root,
        )
        selected = filedialog.askopenfilename(
            parent=root,
            title="Select Google OAuth client-secret JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not selected:
            raise RuntimeError("Gmail sign-in cancelled: no OAuth client-secret JSON was selected.")
        selected_path = Path(selected)
        try:
            app_data_dir().mkdir(parents=True, exist_ok=True)
            shutil.copy2(selected_path, path)
        except OSError as error:
            raise RuntimeError(f"Unable to copy the Gmail OAuth file to the app-data folder: {error}") from error
        return path

    def authenticate(self) -> str:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        scopes = ["https://www.googleapis.com/auth/gmail.modify"]
        token = self.credentials.get_json("Gmail", "token")
        creds = Credentials.from_authorized_user_info(token, scopes) if token else None
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(str(self._client_secret_path()), scopes)
            creds = flow.run_local_server(port=0, open_browser=True)
        self.credentials.set_json("Gmail", "token", json.loads(creds.to_json()))
        self.service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        self.email_address = self.service.users().getProfile(userId="me").execute()["emailAddress"]
        self.credentials.set("Gmail", "email", self.email_address)
        return self.email_address

    def load_messages(self, progress, cancel, pause) -> list[MessageRecord]:
        if not self.service:
            raise RuntimeError("Gmail is not connected.")
        messages: list[MessageRecord] = []
        token = None
        while not cancel.is_set():
            while pause.is_set() and not cancel.is_set():
                cancel.wait(0.1)
            response = self.service.users().messages().list(
                userId="me", q="in:anywhere", pageToken=token, maxResults=100
            ).execute()
            refs = response.get("messages", [])
            for ref in refs:
                if cancel.is_set():
                    break
                while pause.is_set() and not cancel.is_set():
                    cancel.wait(0.1)
                item = self.service.users().messages().get(
                    userId="me", id=ref["id"], format="metadata",
                    metadataHeaders=["From", "To", "Cc", "Subject", "Date", "Message-ID"],
                ).execute()
                messages.append(self._record(item))
                progress(len(messages), None)
            token = response.get("nextPageToken")
            if not token:
                break
        return messages

    def _record(self, item: dict) -> MessageRecord:
        headers = {
            entry["name"].lower(): entry.get("value", "")
            for entry in item.get("payload", {}).get("headers", [])
        }
        name, sender, domain = _parse_sender(_header_value(headers, "from"))
        date_text = _header_value(headers, "date")
        received = None
        try:
            received = email.utils.parsedate_to_datetime(date_text)
        except (TypeError, ValueError, IndexError):
            pass
        labels = item.get("labelIds", [])
        label_names = {
            "INBOX": "Inbox",
            "SPAM": "Spam",
            "TRASH": "Trash",
            "SENT": "Sent",
            "DRAFT": "Drafts",
        }
        folders = [label_names.get(label, label) for label in labels if label != "UNREAD"]
        return MessageRecord(
            message_key=f"gmail:{item['id']}", provider="gmail", account=self.email_address,
            folder=", ".join(folders) or "All Mail",
            sender_name=name, sender_email=sender, sender_domain=domain,
            subject=_decode(_header_value(headers, "subject")) or "(no subject)",
            to_value=_header_value(headers, "to"), cc_value=_header_value(headers, "cc"),
            date_text=date_text, received_at=received, source="live",
            message_id=_header_value(headers, "message-id") or item["id"],
            thread_id=item.get("threadId", ""), is_read="UNREAD" not in labels,
            raw={"gmail_id": item["id"], "labels": ",".join(labels)},
        )

    def move_to_trash(self, message: MessageRecord) -> None:
        self.service.users().messages().trash(userId="me", id=message.raw["gmail_id"]).execute()

    def restore(self, message: MessageRecord) -> None:
        self.service.users().messages().untrash(userId="me", id=message.raw["gmail_id"]).execute()


class OutlookProvider(MailProvider):
    provider_name = "Outlook"

    def __init__(self, credentials: CredentialStore | None = None) -> None:
        self.credentials = credentials or CredentialStore()
        self.token: dict | None = None
        self.email_address = ""
        self.deleted_folder_id = ""

    def authenticate(self) -> str:
        import msal
        import requests

        client_id = os.environ.get("TRASH_CLEANER_OUTLOOK_CLIENT_ID")
        if not client_id:
            import tkinter as tk
            from tkinter import simpledialog

            client_id = simpledialog.askstring(
                "Outlook setup",
                "Enter your Microsoft Entra public-client application ID:",
                parent=tk._default_root,
            )
        if not client_id:
            raise RuntimeError("Outlook sign-in cancelled: no Microsoft application ID was provided.")
        cache = msal.SerializableTokenCache()
        cached = self.credentials.get("Outlook", "msal_cache")
        if cached:
            cache.deserialize(cached)
        app = msal.PublicClientApplication(
            client_id, authority="https://login.microsoftonline.com/common", token_cache=cache
        )
        accounts = app.get_accounts()
        result = app.acquire_token_silent(["Mail.ReadWrite", "User.Read"], account=accounts[0]) if accounts else None
        if not result:
            result = app.acquire_token_interactive(["Mail.ReadWrite", "User.Read"], prompt="select_account")
        if "access_token" not in result:
            raise RuntimeError(result.get("error_description", "Microsoft sign-in failed."))
        if cache.has_state_changed:
            self.credentials.set("Outlook", "msal_cache", cache.serialize())
        self.token = result
        profile = requests.get(
            "https://graph.microsoft.com/v1.0/me?$select=mail,userPrincipalName",
            headers=self._headers(), timeout=30,
        )
        profile.raise_for_status()
        data = profile.json()
        self.email_address = data.get("mail") or data["userPrincipalName"]
        self.credentials.set("Outlook", "email", self.email_address)
        folders = requests.get(
            "https://graph.microsoft.com/v1.0/me/mailFolders?$top=100",
            headers=self._headers(), timeout=30,
        )
        folders.raise_for_status()
        self.deleted_folder_id = next(
            (item["id"] for item in folders.json().get("value", []) if item.get("displayName") == "Deleted Items"), ""
        )
        return self.email_address

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token['access_token']}", "Content-Type": "application/json"}

    def load_messages(self, progress, cancel, pause) -> list[MessageRecord]:
        import requests

        url = "https://graph.microsoft.com/v1.0/me/messages?$top=100&$select=id,conversationId,subject,receivedDateTime,from,toRecipients,ccRecipients,parentFolderId,isRead,hasAttachments"
        messages: list[MessageRecord] = []
        while url and not cancel.is_set():
            while pause.is_set() and not cancel.is_set():
                cancel.wait(0.1)
            response = requests.get(url, headers=self._headers(), timeout=60)
            response.raise_for_status()
            data = response.json()
            for item in data.get("value", []):
                messages.append(self._record(item))
                progress(len(messages), None)
            url = data.get("@odata.nextLink")
        return messages

    def _record(self, item: dict) -> MessageRecord:
        sender_data = item.get("from", {}).get("emailAddress", {})
        name, sender, domain = MessageRecord.derive_sender_parts(
            sender_data.get("name", ""), sender_data.get("address", "")
        )
        received_text = item.get("receivedDateTime", "")
        received = datetime.fromisoformat(received_text.replace("Z", "+00:00")) if received_text else None
        return MessageRecord(
            message_key=f"outlook:{item['id']}", provider="outlook", account=self.email_address,
            folder=item.get("parentFolderId", "Unknown"), sender_name=name, sender_email=sender,
            sender_domain=domain, subject=item.get("subject") or "(no subject)", to_value="",
            cc_value="", date_text=received_text, received_at=received, source="live",
            message_id=item["id"], thread_id=item.get("conversationId", ""), is_read=item.get("isRead", False),
            has_attachments=item.get("hasAttachments", False), raw={"outlook_id": item["id"], "folder_id": item.get("parentFolderId", "")},
        )

    def move_to_trash(self, message: MessageRecord) -> None:
        import requests

        response = requests.post(
            f"https://graph.microsoft.com/v1.0/me/messages/{quote(message.raw['outlook_id'])}/move",
            headers=self._headers(), json={"destinationId": self.deleted_folder_id}, timeout=30,
        )
        response.raise_for_status()

    def restore(self, message: MessageRecord) -> None:
        import requests

        response = requests.post(
            f"https://graph.microsoft.com/v1.0/me/messages/{quote(message.raw['outlook_id'])}/move",
            headers=self._headers(), json={"destinationId": message.raw["folder_id"]}, timeout=30,
        )
        response.raise_for_status()


class ICloudProvider(MailProvider):
    provider_name = "iCloud"

    def __init__(self, credentials: CredentialStore | None = None) -> None:
        self.credentials = credentials or CredentialStore()
        self.connection: imaplib.IMAP4_SSL | None = None
        self.email_address = ""
        self.password = ""
        self.trash_folder = ""

    def authenticate(self) -> str:
        import tkinter as tk
        from tkinter import messagebox, simpledialog

        email_address = self.credentials.get("iCloud", "email")
        password = self.credentials.get("iCloud", "password")
        root = tk._default_root
        if not email_address:
            email_address = simpledialog.askstring("iCloud sign-in", "iCloud email address:", parent=root)
        if not password:
            messagebox.showinfo(
                "iCloud app-specific password",
                "Create an app-specific password at appleid.apple.com:\n"
                "Sign in → Sign-In and Security → App-Specific Passwords → Generate.",
                parent=root,
            )
            password = simpledialog.askstring(
                "iCloud sign-in", "Apple app-specific password (not your Apple ID password):",
                show="*", parent=root,
            )
        if not email_address or not password:
            raise RuntimeError("iCloud email and app-specific password are required.")
        connection = imaplib.IMAP4_SSL("imap.mail.me.com", 993)
        connection.login(email_address, password)
        self.connection, self.email_address, self.password = connection, email_address, password
        self.credentials.set("iCloud", "email", email_address)
        self.credentials.set("iCloud", "password", password)
        self.trash_folder = self._find_trash()
        return email_address

    def _find_trash(self) -> str:
        status, boxes = self.connection.list()
        if status != "OK":
            return "Deleted Messages"
        for box in boxes or []:
            decoded = box.decode(errors="replace")
            name = decoded.rsplit(' "/" ', 1)[-1].strip('"')
            if name.lower() in {"trash", "deleted messages", "deleted"}:
                return name
        return "Deleted Messages"

    def load_messages(self, progress, cancel, pause) -> list[MessageRecord]:
        if not self.connection:
            raise RuntimeError("iCloud is not connected.")
        messages: list[MessageRecord] = []
        status, boxes = self.connection.list()
        if status != "OK":
            raise RuntimeError("Unable to list iCloud mail folders.")
        for box in boxes or []:
            if cancel.is_set():
                break
            folder = box.decode(errors="replace").rsplit(' "/" ', 1)[-1].strip('"')
            if self.connection.select(f'"{folder}"', readonly=True)[0] != "OK":
                continue
            status, data = self.connection.uid("search", None, "ALL")
            if status != "OK":
                continue
            for uid in (data[0] or b"").split():
                while pause.is_set() and not cancel.is_set():
                    cancel.wait(0.1)
                if cancel.is_set():
                    break
                status, fetched = self.connection.uid(
                    "fetch", uid, "(BODY.PEEK[HEADER.FIELDS (FROM TO CC SUBJECT DATE MESSAGE-ID)] FLAGS)"
                )
                if status == "OK":
                    record = self._record(folder, uid.decode(), fetched)
                    if record:
                        messages.append(record)
                        progress(len(messages), None)
        return messages

    def _record(self, folder: str, uid: str, fetched: list) -> MessageRecord | None:
        header_bytes = next((part[1] for part in fetched if isinstance(part, tuple)), b"")
        parsed = email.message_from_bytes(header_bytes)
        raw_headers = {key.lower(): value for key, value in parsed.items()}
        name, sender, domain = _parse_sender(raw_headers.get("from", ""))
        date_text = raw_headers.get("date", "")
        try:
            received = email.utils.parsedate_to_datetime(date_text)
        except (TypeError, ValueError, IndexError):
            received = None
        flags = b"".join(part for part in fetched if isinstance(part, bytes))
        return MessageRecord(
            message_key=f"icloud:{folder}:{uid}", provider="icloud", account=self.email_address,
            folder=folder, sender_name=name, sender_email=sender, sender_domain=domain,
            subject=_decode(raw_headers.get("subject", "")) or "(no subject)",
            to_value=raw_headers.get("to", ""), cc_value=raw_headers.get("cc", ""),
            date_text=date_text, received_at=received, source="live",
            message_id=raw_headers.get("message-id", "") or uid, is_read=b"\\Seen" in flags,
            raw={"folder": folder, "uid": uid},
        )

    def move_to_trash(self, message: MessageRecord) -> None:
        self._move(message, self.trash_folder)

    def restore(self, message: MessageRecord) -> None:
        self._move(message, message.raw["folder"])

    def _move(self, message: MessageRecord, destination: str) -> None:
        self.connection.select(f'"{message.raw["folder"]}"')
        status, _ = self.connection.uid("copy", message.raw["uid"], f'"{destination}"')
        if status != "OK":
            raise RuntimeError(f"Unable to copy message to {destination}.")
        self.connection.uid("store", message.raw["uid"], "+FLAGS", "(\\Deleted)")
        self.connection.expunge()

    def disconnect(self) -> None:
        if self.connection:
            try:
                self.connection.logout()
            except OSError:
                pass
            self.connection = None


def provider_for(name: str) -> MailProvider:
    if name == "Gmail":
        return GmailProvider()
    if name == "Outlook":
        return OutlookProvider()
    if name == "iCloud":
        return ICloudProvider()
    raise ValueError(f"Unsupported live provider: {name}")

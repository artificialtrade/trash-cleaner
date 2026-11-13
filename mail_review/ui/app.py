from __future__ import annotations

import tkinter as tk
import queue
import threading
from dataclasses import replace
from tkinter import filedialog, messagebox, ttk

from mail_review.models import MessageRecord
from mail_review.services.action_log import ActionLog
from mail_review.services.csv_importer import load_messages_from_csv
from mail_review.services.demo_data import load_demo_messages
from mail_review.services.grouping import filter_messages, group_by_sender
from mail_review.services.simulated_actions import SimulatedTrashStore
from mail_review.services.providers import MailProvider, provider_for
from mail_review.state import MessageSelectionState


ACCOUNT_MODES = ("Gmail", "iCloud", "Outlook", "Demo", "CSV Import")
MAIL_ACTIONS = (
    ("Move to Trash / Bin", "trash"),
    ("Archive", "archive"),
    ("Mark important", "important"),
    ("Flag / star", "flag"),
    ("Mark as read", "mark-read"),
)


class MailReviewApp:
    """Safe offline-first desktop UI for reviewing and selecting messages."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Mail Review")
        self.root.geometry("1280x760")
        self.root.minsize(1024, 640)

        self.selection_state = MessageSelectionState()
        self.trash_store = SimulatedTrashStore(ActionLog())
        self.messages: list[MessageRecord] = []
        self.visible_messages: list[MessageRecord] = []
        self.message_index: dict[str, MessageRecord] = {}
        self.account_mode = "Demo"
        self.account_status = {mode: "Not connected" for mode in ACCOUNT_MODES}
        self.account_email = {mode: "" for mode in ACCOUNT_MODES}
        self.providers: dict[str, MailProvider] = {}
        self.loader_thread: threading.Thread | None = None
        self.load_cancel = threading.Event()
        self.load_pause = threading.Event()
        self.load_events: queue.Queue = queue.Queue()
        self.recently_trashed: dict[str, MessageRecord] = {}
        self.last_live_moved: list[str] = []

        self.account_var = tk.StringVar(value="Demo")
        self.group_var = tk.StringVar(value="All senders")
        self.search_var = tk.StringVar(value="")
        self.folder_var = tk.StringVar(value="All folders")
        self.read_var = tk.StringVar(value="all")
        self.attachment_var = tk.StringVar(value="all")
        self.status_var = tk.StringVar(value="Load demo data or import Email_evidence.csv to begin.")
        self.summary_var = tk.StringVar(value="No messages loaded")
        self.active_account_var = tk.StringVar(value="")
        self.connection_var = tk.StringVar(value="")
        self.preview_subject_var = tk.StringVar(value="")
        self.preview_sender_var = tk.StringVar(value="")
        self.preview_meta_var = tk.StringVar(value="")
        self.action_var = tk.StringVar(value=MAIL_ACTIONS[0][0])

        self._build_layout()
        self._bind_events()
        self.load_demo()

    def _build_layout(self) -> None:
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        main_frame = ttk.Frame(self.root, padding=8)
        main_frame.grid(row=0, column=0, sticky="nsew")
        main_frame.rowconfigure(2, weight=1)
        main_frame.columnconfigure(0, weight=1)

        top = ttk.LabelFrame(main_frame, text="Active account", padding=6)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        top.columnconfigure(5, weight=1)
        ttk.Label(top, text="Account:").grid(row=0, column=0, padx=(0, 4))
        self.account_selector = ttk.Combobox(
            top, textvariable=self.account_var, values=ACCOUNT_MODES, state="readonly", width=13
        )
        self.account_selector.grid(row=0, column=1, padx=(0, 8))
        ttk.Button(top, text="Connect Account", command=self.connect_account).grid(row=0, column=2, padx=4)
        ttk.Button(top, text="Disconnect / Sign out", command=self.disconnect_account).grid(row=0, column=3, padx=4)
        ttk.Label(top, textvariable=self.connection_var).grid(row=0, column=4, padx=8)
        ttk.Label(top, textvariable=self.active_account_var).grid(row=0, column=5, sticky="w")

        controls = ttk.LabelFrame(main_frame, text="Mailbox controls", padding=6)
        controls.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        controls.columnconfigure(3, weight=1)
        ttk.Button(controls, text="Load Offline Demo", command=self.load_demo).grid(row=0, column=0, padx=3)
        ttk.Button(controls, text="Import CSV", command=self.import_csv).grid(row=0, column=1, padx=3)
        ttk.Label(controls, text="Search").grid(row=0, column=2, padx=(12, 3))
        ttk.Entry(controls, textvariable=self.search_var).grid(row=0, column=3, sticky="ew")
        ttk.Label(controls, text="Folder").grid(row=0, column=4, padx=(12, 3))
        self.folder_selector = ttk.Combobox(controls, textvariable=self.folder_var, state="readonly", width=16)
        self.folder_selector.grid(row=0, column=5)
        ttk.Label(controls, text="Read").grid(row=0, column=6, padx=(8, 3))
        ttk.Combobox(
            controls, textvariable=self.read_var, values=("all", "read", "unread"), state="readonly", width=9
        ).grid(row=0, column=7)
        ttk.Label(controls, text="Attachments").grid(row=0, column=8, padx=(8, 3))
        ttk.Combobox(
            controls,
            textvariable=self.attachment_var,
            values=("all", "with attachments", "without attachments"),
            state="readonly",
            width=18,
        ).grid(row=0, column=9)
        self.load_progress = ttk.Progressbar(controls, mode="indeterminate", length=150)
        self.load_progress.grid(row=1, column=3, columnspan=2, sticky="ew", padx=(3, 0), pady=(6, 0))
        ttk.Button(controls, text="Pause", command=self.pause_loading).grid(row=1, column=5, padx=3, pady=(6, 0))
        ttk.Button(controls, text="Resume", command=self.resume_loading).grid(row=1, column=6, padx=3, pady=(6, 0))
        ttk.Button(controls, text="Cancel loading", command=self.cancel_loading).grid(
            row=1, column=7, columnspan=2, padx=3, pady=(6, 0)
        )
        ttk.Label(controls, text="Bulk action").grid(row=2, column=0, padx=(3, 8), pady=(6, 0), sticky="w")
        self.action_selector = ttk.Combobox(
            controls,
            textvariable=self.action_var,
            values=[label for label, _action in MAIL_ACTIONS],
            state="readonly",
            width=23,
        )
        self.action_selector.grid(row=2, column=1, columnspan=2, padx=3, pady=(6, 0), sticky="w")
        ttk.Button(controls, text="Apply action", command=self.apply_selected_action).grid(
            row=2, column=3, padx=3, pady=(6, 0), sticky="w"
        )
        ttk.Button(controls, text="Select visible", command=self.select_all_visible).grid(
            row=2, column=4, padx=3, pady=(6, 0)
        )
        ttk.Button(controls, text="Clear selection", command=self.clear_selection).grid(
            row=2, column=5, padx=3, pady=(6, 0)
        )
        ttk.Button(controls, text="Review selection", command=self.review_selection).grid(
            row=2, column=6, padx=3, pady=(6, 0)
        )

        splitter = ttk.Panedwindow(main_frame, orient=tk.HORIZONTAL)
        splitter.grid(row=2, column=0, sticky="nsew")
        sidebar = ttk.Frame(splitter, padding=(0, 0, 8, 0))
        sidebar.rowconfigure(1, weight=1)
        sidebar.columnconfigure(0, weight=1)
        ttk.Label(sidebar, text="Sender groups").grid(row=0, column=0, sticky="w")
        ttk.Button(
            sidebar, text="Select group emails", command=self.select_sender_group
        ).grid(row=0, column=1, padx=(6, 0), sticky="e")
        self.group_list = tk.Listbox(
            sidebar, exportselection=False, activestyle="none", selectmode=tk.EXTENDED
        )
        self.group_list.grid(row=1, column=0, columnspan=2, sticky="nsew")

        panel = ttk.Frame(splitter)
        panel.rowconfigure(1, weight=1)
        panel.columnconfigure(0, weight=1)
        ttk.Label(panel, textvariable=self.summary_var).grid(row=0, column=0, sticky="w", pady=(0, 4))
        columns = ("selected", "source", "folder", "sender", "subject", "date", "status")
        self.message_table = ttk.Treeview(panel, columns=columns, show="headings", selectmode="extended")
        for col, width in (
            ("selected", 65), ("source", 85), ("folder", 110), ("sender", 240),
            ("subject", 350), ("date", 150), ("status", 85)
        ):
            self.message_table.heading(col, text=col.capitalize())
            self.message_table.column(col, width=width, anchor="w")
        scrollbar = ttk.Scrollbar(panel, orient=tk.VERTICAL, command=self.message_table.yview)
        self.message_table.configure(yscrollcommand=scrollbar.set)
        self.message_table.grid(row=1, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns")
        details = ttk.LabelFrame(panel, text="Message details", padding=8)
        details.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        details.columnconfigure(0, weight=1)
        ttk.Label(details, textvariable=self.preview_subject_var, wraplength=820).grid(row=0, column=0, sticky="w")
        ttk.Label(details, textvariable=self.preview_sender_var, wraplength=820).grid(row=1, column=0, sticky="w")
        ttk.Label(details, textvariable=self.preview_meta_var, wraplength=820).grid(row=2, column=0, sticky="w")
        splitter.add(sidebar, weight=1)
        splitter.add(panel, weight=4)

        actions = ttk.Frame(self.root, padding=(10, 8))
        actions.grid(row=1, column=0, sticky="ew")
        actions.columnconfigure(0, weight=1)
        self.selection_label = ttk.Label(actions, text="Selected: 0 | Visible: 0 | Hidden: 0")
        self.selection_label.grid(row=0, column=0, sticky="w")
        ttk.Button(actions, text="Select all visible", command=self.select_all_visible).grid(row=0, column=1, padx=4)
        ttk.Button(actions, text="Select sender group", command=self.select_sender_group).grid(row=0, column=2, padx=4)
        ttk.Button(actions, text="Clear selection", command=self.clear_selection).grid(row=0, column=3, padx=4)
        ttk.Button(actions, text="Review selection", command=self.review_selection).grid(row=0, column=4, padx=4)
        ttk.Button(actions, text="Restore", command=self.restore_selected).grid(row=0, column=5, padx=4)
        ttk.Button(actions, text="Undo", command=self.undo_last_action).grid(row=0, column=6, padx=4)
        ttk.Button(actions, text="Recently trashed", command=self.show_recently_trashed).grid(row=0, column=7, padx=4)
        ttk.Label(self.root, textvariable=self.status_var, anchor="w", relief=tk.SUNKEN).grid(
            row=2, column=0, sticky="ew"
        )

    def _bind_events(self) -> None:
        for variable in (self.search_var, self.folder_var, self.read_var, self.attachment_var):
            variable.trace_add("write", lambda *_: self.apply_filters(clear_preview=True))
        self.account_selector.bind("<<ComboboxSelected>>", self._on_account_change)
        self.group_list.bind("<<ListboxSelect>>", lambda _event: self.apply_filters(clear_preview=True))
        self.message_table.bind("<<TreeviewSelect>>", self._on_message_selection)

    def _on_account_change(self, _event: tk.Event) -> None:
        self.cancel_loading()
        self.account_mode = self.account_var.get()
        self.selection_state.switch_account(self.account_mode)
        if self.account_mode == "Demo":
            self.load_demo()
        elif self.account_mode != "CSV Import":
            self.messages = []
            self._set_messages(f"{self.account_mode} (not connected)")
        self._update_account_banner()

    def _update_account_banner(self) -> None:
        status = self.account_status[self.account_mode]
        email = self.account_email[self.account_mode]
        self.connection_var.set(f"Status: {status}")
        self.active_account_var.set(f"Active: {self.account_mode}" + (f" ({email})" if email else ""))

    def connect_account(self) -> None:
        if self.account_mode in {"Demo", "CSV Import"}:
            self.account_status[self.account_mode] = "Connected"
            self.account_email[self.account_mode] = "Offline demo" if self.account_mode == "Demo" else "CSV import"
            self._update_account_banner()
            return
        try:
            provider = self.providers.get(self.account_mode) or provider_for(self.account_mode)
            self.status_var.set(f"Opening {self.account_mode} sign-in...")
            self.root.update_idletasks()
            email_address = provider.authenticate()
        except Exception as error:
            self.account_status[self.account_mode] = "Connection error"
            self._update_account_banner()
            messagebox.showerror("Connection failed", str(error))
            self.status_var.set(f"{self.account_mode} connection failed.")
            return
        self.providers[self.account_mode] = provider
        self.account_status[self.account_mode] = "Connected"
        self.account_email[self.account_mode] = email_address
        self._update_account_banner()
        self._start_loading(provider)

    def disconnect_account(self) -> None:
        self.cancel_loading()
        provider = self.providers.pop(self.account_mode, None)
        if provider:
            provider.disconnect()
            credentials = getattr(provider, "credentials", None)
            if credentials:
                credentials.clear_account(self.account_mode)
        self.account_status[self.account_mode] = "Signed out"
        self.account_email[self.account_mode] = ""
        self.selection_state.switch_account(self.account_mode)
        self.messages = []
        self._set_messages(f"{self.account_mode} (signed out)")
        self._update_account_banner()

    def _start_loading(self, provider: MailProvider) -> None:
        self.load_cancel.clear()
        self.load_pause.clear()
        self.load_progress.start(12)
        self.status_var.set(f"Loading {self.account_email[self.account_mode]} messages...")

        def worker() -> None:
            try:
                loaded = provider.load_messages(
                    lambda count, _total, batch: self.load_events.put(("progress", count, batch)),
                    self.load_cancel,
                    self.load_pause,
                )
                self.load_events.put(("done", loaded, self.load_cancel.is_set()))
            except Exception as error:
                self.load_events.put(("error", error))

        self.loader_thread = threading.Thread(target=worker, daemon=True)
        self.loader_thread.start()
        self.root.after(100, self._poll_load_events)

    def _poll_load_events(self) -> None:
        try:
            while True:
                event = self.load_events.get_nowait()
                if event[0] == "progress":
                    count, batch = event[1], event[2]
                    existing = {message.message_key for message in self.messages}
                    self.messages.extend(
                        message for message in batch if message.message_key not in existing
                    )
                    self.message_index = {item.message_key: item for item in self.messages}
                    self._refresh_groups()
                    self._refresh_folders()
                    self.apply_filters(clear_preview=False)
                    self.status_var.set(f"Loaded {count} messages; loading continues...")
                elif event[0] == "done":
                    self.load_progress.stop()
                    loaded, cancelled = event[1], event[2]
                    self.messages = loaded
                    self._set_messages(f"{self.account_mode} mailbox")
                    self.status_var.set(
                        f"{'Cancelled with' if cancelled else 'Loaded'} {len(loaded)} live messages."
                    )
                elif event[0] == "error":
                    self.load_progress.stop()
                    self.account_status[self.account_mode] = "Connection error"
                    self._update_account_banner()
                    messagebox.showerror("Mailbox loading failed", str(event[1]))
                    self.status_var.set("Mailbox loading failed.")
        except queue.Empty:
            pass
        if self.loader_thread and self.loader_thread.is_alive():
            self.root.after(100, self._poll_load_events)

    def pause_loading(self) -> None:
        if self.loader_thread and self.loader_thread.is_alive():
            self.load_pause.set()
            self.status_var.set("Mailbox loading paused.")

    def resume_loading(self) -> None:
        if self.loader_thread and self.loader_thread.is_alive():
            self.load_pause.clear()
            self.status_var.set("Mailbox loading resumed.")

    def cancel_loading(self) -> None:
        self.load_cancel.set()
        self.load_pause.clear()
        if self.loader_thread and self.loader_thread.is_alive():
            self.status_var.set("Cancelling mailbox loading...")

    def load_demo(self) -> None:
        self.account_mode = "Demo"
        self.account_var.set("Demo")
        self.account_status["Demo"] = "Connected"
        self.account_email["Demo"] = "Offline demo"
        self.messages = load_demo_messages()
        self._set_messages("offline demo")
        self._update_account_banner()

    def import_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Email evidence CSV", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            loaded = load_messages_from_csv(path)
        except (OSError, ValueError) as error:
            messagebox.showerror("Import failed", str(error))
            return
        self.account_mode = "CSV Import"
        self.account_var.set("CSV Import")
        self.account_status["CSV Import"] = "Connected"
        self.account_email["CSV Import"] = path
        self.messages = loaded
        self._set_messages(path)
        self._update_account_banner()

    def _set_messages(self, source_label: str) -> None:
        self.message_index = {item.message_key: item for item in self.messages}
        self.selection_state.clear_selection()
        self.clear_preview()
        self.status_var.set(f"Loaded {len(self.messages)} messages from {source_label}.")
        self._refresh_groups()
        self._refresh_folders()
        self.apply_filters(clear_preview=True)

    def _refresh_groups(self) -> None:
        selected_names = self._selected_group_names() if hasattr(self, "group_list") else []
        self.group_list.delete(0, tk.END)
        self.group_list.insert(tk.END, "All senders")
        for key, group in group_by_sender(self.messages).items():
            self.group_list.insert(tk.END, f"{group.sender_name} <{key}> ({group.count})")
        self.group_list.selection_clear(0, tk.END)
        selected_indexes = []
        for index in range(1, self.group_list.size()):
            group_name = self.group_list.get(index).rsplit(" <", 1)[-1].split("> (", 1)[0]
            if group_name in selected_names:
                selected_indexes.append(index)
        if selected_indexes:
            for index in selected_indexes:
                self.group_list.selection_set(index)
        else:
            self.group_list.selection_set(0)

    def _refresh_folders(self) -> None:
        values = ["All folders", *sorted({message.folder for message in self.messages})]
        self.folder_selector.configure(values=values)
        if self.folder_var.get() not in values:
            self.folder_var.set("All folders")

    def _selected_group_name(self) -> str:
        selected = self.group_list.curselection()
        if not selected:
            return "All senders"
        value = self.group_list.get(selected[0])
        if value == "All senders":
            return value
        return value.rsplit(" <", 1)[-1].split("> (", 1)[0]

    def _selected_group_names(self) -> list[str]:
        names = []
        for index in self.group_list.curselection():
            value = self.group_list.get(index)
            if value != "All senders":
                names.append(value.rsplit(" <", 1)[-1].split("> (", 1)[0])
        return names

    def apply_filters(self, clear_preview: bool) -> None:
        self.visible_messages = filter_messages(
            self.messages,
            self._selected_group_name(),
            self.search_var.get(),
            folder=self.folder_var.get(),
            read_status=self.read_var.get(),
            attachments=self.attachment_var.get(),
        )
        self._populate_message_table()
        self.summary_var.set(
            f"{len(self.visible_messages)} visible message(s), {len(self.messages)} total, "
            f"{len(group_by_sender(self.messages))} sender group(s)"
        )
        self._update_selection_label()
        if clear_preview:
            self.clear_preview()

    def _populate_message_table(self) -> None:
        self.message_table.delete(*self.message_table.get_children())
        for item in self.visible_messages:
            self.message_table.insert(
                "", tk.END, iid=item.message_key,
                values=(
                    "✓" if item.message_key in self.selection_state.selected_keys else "",
                    "CSV import" if item.source == "csv" else ("Live" if item.is_live else "Demo"),
                    item.folder, f"{item.sender_name} <{item.sender_email}>", item.subject,
                    item.date_text, "Read" if item.is_read else "Unread",
                ),
            )

    def _on_message_focus(self, _event: tk.Event) -> None:
        selected = self.message_table.selection()
        message = self.message_index.get(selected[0]) if selected else None
        if not message:
            self.clear_preview()
            return
        self.selection_state.set_preview(message)
        self.preview_subject_var.set(f"Subject: {message.subject}")
        self.preview_sender_var.set(
            f"From: {message.sender_name} <{message.sender_email}> | To: {message.to_value or '-'} | "
            f"Cc: {message.cc_value or '-'}"
        )
        self.preview_meta_var.set(
            f"Account: {message.account} | Folder: {message.folder} | Date: {message.date_text} | "
            f"Message ID: {message.message_id or message.message_key}"
        )

    def _on_message_selection(self, event: tk.Event) -> None:
        self._on_message_focus(event)
        visible_keys = {message.message_key for message in self.visible_messages}
        selected_keys = set(self.message_table.selection())
        self.selection_state.selected_keys.difference_update(visible_keys - selected_keys)
        self.selection_state.selected_keys.update(selected_keys)
        self._update_selection_label()

    def clear_preview(self) -> None:
        self.selection_state.clear_preview()
        self.preview_subject_var.set("")
        self.preview_sender_var.set("")
        self.preview_meta_var.set("")

    def select_all_visible(self) -> None:
        self.selection_state.select_visible(self.visible_messages)
        self._populate_message_table()
        self._update_selection_label()

    def select_sender_group(self) -> None:
        group_names = self._selected_group_names()
        if not group_names:
            self.selection_state.select_visible(self.visible_messages)
        else:
            groups = group_by_sender(self.messages)
            for group_name in group_names:
                group = groups.get(group_name)
                if group:
                    self.selection_state.select_visible(list(group.messages))
        self._populate_message_table()
        self._update_selection_label()

    def clear_selection(self) -> None:
        self.selection_state.clear_selection()
        self._populate_message_table()
        self._update_selection_label()

    def _update_selection_label(self) -> None:
        total, visible, hidden = self.selection_state.counts(self.visible_messages)
        self.selection_label.configure(text=f"Selected: {total} | Visible: {visible} | Hidden: {hidden}")

    def _selected_messages(self) -> list[MessageRecord]:
        return [self.message_index[key] for key in self.selection_state.selected_keys if key in self.message_index]

    def _selected_action(self) -> tuple[str, str]:
        label = self.action_var.get()
        return next((action for action in MAIL_ACTIONS if action[0] == label), MAIL_ACTIONS[0])

    def review_selection(self) -> None:
        selected = self._selected_messages()
        if not selected:
            messagebox.showinfo("Review selection", "No messages are selected.")
            return
        senders = ", ".join(sorted({message.sender_email for message in selected}))
        folders = ", ".join(sorted({message.folder for message in selected}))
        messagebox.showinfo(
            "Review selection",
            f"{len(selected)} email(s)\nSenders: {senders}\nFolders: {folders}\n"
            "CSV and Demo records are simulation-only." if not any(item.is_live for item in selected)
            else "Live mailbox messages will be changed only after confirmation.",
        )

    def apply_selected_action(self) -> None:
        selected = self._selected_messages()
        if not selected:
            messagebox.showinfo("Bulk action", "Select one or more emails first.")
            return
        label, action = self._selected_action()
        if action == "trash":
            destination = {
            "Gmail": "Gmail Trash",
            "iCloud": "iCloud Trash / Deleted Messages",
            "Outlook": "Outlook Deleted Items",
            }.get(self.account_mode, "simulated Trash")
        else:
            destination = label
        if len(selected) > 100 and not messagebox.askyesno(
            "Large bulk action",
            f"This will move {len(selected)} messages. Continue?",
        ):
            return
        if not messagebox.askyesno(
            "Confirm bulk action",
            f"{label} for {len(selected)} email(s)?\n"
            f"Senders: {', '.join(sorted({m.sender_email for m in selected}))}\n"
            f"Folders: {', '.join(sorted({m.folder for m in selected}))}",
        ):
            return
        if any(message.is_live for message in selected):
            provider = self.providers.get(self.account_mode)
            if not provider:
                messagebox.showerror("Move failed", "The active account is no longer connected.")
                return
            succeeded, failed = [], []
            for message in selected:
                try:
                    if action == "trash":
                        provider.move_to_trash(message)
                    else:
                        provider.apply_action(action, message)
                    succeeded.append(message)
                except Exception:
                    failed.append(message)
            if action == "trash":
                self.recently_trashed.update({message.message_key: message for message in succeeded})
                self.last_live_moved = [message.message_key for message in succeeded]
            ActionLog().append(succeeded, action, "success")
            ActionLog().append(failed, action, "failure")
            if failed:
                messagebox.showwarning(
                    "Partial move",
                    f"{len(succeeded)} moved successfully; {len(failed)} failed. "
                    "Reconnect and retry the failed messages.",
                )
            status = f"Applied {label} to {len(succeeded)} live message(s)."
            if failed:
                status += f" {len(failed)} failed."
            self.status_var.set(status)
        else:
            if action == "trash":
                self.trash_store.move_to_trash(selected)
                self.recently_trashed.update({message.message_key: message for message in selected})
                self.last_live_moved = []
            ActionLog().append(selected, action, "simulated")
            self.status_var.set(
                f"Simulated {label.lower()} for {len(selected)} email(s); no real email was changed."
            )
        if action in {"trash", "archive"}:
            self.messages = [
                message for message in self.messages
                if message.message_key not in self.selection_state.selected_keys
            ]
        elif action == "mark-read":
            self.messages = [
                replace(message, is_read=True) if message.message_key in self.selection_state.selected_keys else message
                for message in self.messages
            ]
        self._set_messages(f"after {label.lower()}")

    def restore_selected(self) -> None:
        self._restore_keys(list(self.selection_state.selected_keys))

    def _restore_keys(self, keys: list[str]) -> None:
        restored = self.trash_store.restore(keys)
        live_restored = []
        provider = self.providers.get(self.account_mode)
        if provider:
            for key in keys:
                message = self.recently_trashed.get(key)
                if message and message.is_live:
                    try:
                        provider.restore(message)
                        live_restored.append(message)
                        ActionLog().append([message], "restore", "success")
                    except Exception:
                        ActionLog().append([message], "restore", "failure")
        restored.extend(live_restored)
        if not restored:
            messagebox.showinfo("Restore", "Select recently trashed emails first.")
            return
        for message in restored:
            self.recently_trashed.pop(message.message_key, None)
        self.messages.extend(restored)
        self._set_messages("offline data after restore")
        self.status_var.set(f"Restored {len(restored)} email(s) from simulated Trash.")

    def undo_last_action(self) -> None:
        restored = self.trash_store.undo()
        provider = self.providers.get(self.account_mode)
        if provider:
            for key in self.last_live_moved:
                message = self.recently_trashed.get(key)
                if message:
                    try:
                        provider.restore(message)
                        restored.append(message)
                        ActionLog().append([message], "undo", "success")
                    except Exception:
                        ActionLog().append([message], "undo", "failure")
            self.last_live_moved = []
        if not restored:
            messagebox.showinfo("Undo", "There is no simulated Trash action to undo.")
            return
        self.messages.extend(restored)
        for message in restored:
            self.recently_trashed.pop(message.message_key, None)
        self._set_messages("offline data after Undo")
        self.status_var.set(f"Undid simulated Trash for {len(restored)} email(s).")

    def show_recently_trashed(self) -> None:
        if not self.trash_store.trashed:
            messages = list(self.recently_trashed.values())
        else:
            messages = list({**self.recently_trashed, **self.trash_store.trashed}.values())
        if not messages:
            messagebox.showinfo("Recently trashed", "No emails have been moved to Trash.")
            return
        window = tk.Toplevel(self.root)
        window.title("Recently trashed")
        window.geometry("900x420")
        table = ttk.Treeview(window, columns=("sender", "subject", "folder", "account"), show="headings")
        for column, width in (("sender", 240), ("subject", 360), ("folder", 120), ("account", 180)):
            table.heading(column, text=column.capitalize())
            table.column(column, width=width, anchor="w")
        table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        for message in messages:
            table.insert(
                "", tk.END, iid=message.message_key,
                values=(message.sender_email, message.subject, message.folder, message.account),
            )
        ttk.Button(
            window,
            text="Restore selected",
            command=lambda: self._restore_recent_window(table, window),
        ).pack(pady=(0, 8))

    def _restore_recent_window(self, table: ttk.Treeview, window: tk.Toplevel) -> None:
        keys = list(table.selection())
        if not keys:
            messagebox.showinfo("Restore", "Select one or more recently trashed emails.", parent=window)
            return
        self._restore_keys(keys)
        window.destroy()


def run_app() -> None:
    root = tk.Tk()
    MailReviewApp(root)
    root.mainloop()

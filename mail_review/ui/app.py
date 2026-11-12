from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from mail_review.models import MessageRecord
from mail_review.services.csv_importer import load_messages_from_csv
from mail_review.services.demo_data import load_demo_messages
from mail_review.services.grouping import filter_messages, group_by_sender_domain
from mail_review.state import MessageSelectionState


class MailReviewApp:
    """Milestone 1 desktop UI for safe offline review and selection."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Mail Review - Milestone 1")
        self.root.geometry("1280x760")
        self.root.minsize(1024, 640)

        self.selection_state = MessageSelectionState()
        self.messages: list[MessageRecord] = []
        self.visible_messages: list[MessageRecord] = []
        self.message_index: dict[str, MessageRecord] = {}

        self.group_var = tk.StringVar(value="All sender domains")
        self.search_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Load demo data or import Email_evidence.csv to begin.")
        self.summary_var = tk.StringVar(value="No messages loaded")
        self.preview_subject_var = tk.StringVar(value="")
        self.preview_sender_var = tk.StringVar(value="")
        self.preview_meta_var = tk.StringVar(value="")

        self._build_layout()
        self._bind_events()
        self.load_demo()

    def _build_layout(self) -> None:
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)

        main_frame = ttk.Frame(self.root, padding=8)
        main_frame.grid(row=0, column=0, sticky="nsew")
        main_frame.rowconfigure(1, weight=1)
        main_frame.columnconfigure(1, weight=1)

        top_controls = ttk.Frame(main_frame)
        top_controls.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        top_controls.columnconfigure(2, weight=1)

        ttk.Button(top_controls, text="Load Offline Demo", command=self.load_demo).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(top_controls, text="Import CSV", command=self.import_csv).grid(row=0, column=1, padx=(0, 6))

        ttk.Label(top_controls, text="Search").grid(row=0, column=2, sticky="e")
        search_entry = ttk.Entry(top_controls, textvariable=self.search_var)
        search_entry.grid(row=0, column=3, sticky="ew", padx=(6, 0))
        top_controls.columnconfigure(3, weight=1)

        splitter = ttk.Panedwindow(main_frame, orient=tk.HORIZONTAL)
        splitter.grid(row=1, column=0, columnspan=2, sticky="nsew")

        sidebar = ttk.Frame(splitter, padding=(0, 0, 8, 0))
        sidebar.rowconfigure(1, weight=1)
        sidebar.columnconfigure(0, weight=1)

        ttk.Label(sidebar, text="Sender groups").grid(row=0, column=0, sticky="w")
        self.group_list = tk.Listbox(sidebar, exportselection=False, activestyle="none")
        self.group_list.grid(row=1, column=0, sticky="nsew")

        main_panel = ttk.Frame(splitter)
        main_panel.rowconfigure(1, weight=1)
        main_panel.columnconfigure(0, weight=1)

        ttk.Label(main_panel, textvariable=self.summary_var).grid(row=0, column=0, sticky="w", pady=(0, 4))

        columns = ("selected", "provider", "account", "folder", "sender", "subject", "date")
        self.message_table = ttk.Treeview(main_panel, columns=columns, show="headings", selectmode="browse")
        for col, width in (
            ("selected", 70),
            ("provider", 85),
            ("account", 170),
            ("folder", 100),
            ("sender", 220),
            ("subject", 360),
            ("date", 150),
        ):
            self.message_table.heading(col, text=col.capitalize())
            self.message_table.column(col, width=width, anchor="w")

        table_scroll = ttk.Scrollbar(main_panel, orient=tk.VERTICAL, command=self.message_table.yview)
        self.message_table.configure(yscrollcommand=table_scroll.set)
        self.message_table.grid(row=1, column=0, sticky="nsew")
        table_scroll.grid(row=1, column=1, sticky="ns")

        details_panel = ttk.LabelFrame(main_panel, text="Message details", padding=8)
        details_panel.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        details_panel.columnconfigure(0, weight=1)

        ttk.Label(details_panel, textvariable=self.preview_subject_var, wraplength=820).grid(row=0, column=0, sticky="w")
        ttk.Label(details_panel, textvariable=self.preview_sender_var, wraplength=820).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(details_panel, textvariable=self.preview_meta_var, wraplength=820).grid(row=2, column=0, sticky="w", pady=(4, 0))

        splitter.add(sidebar, weight=1)
        splitter.add(main_panel, weight=4)

        action_bar = ttk.Frame(self.root, padding=(10, 8))
        action_bar.grid(row=1, column=0, sticky="ew")
        action_bar.columnconfigure(0, weight=1)

        self.selection_label = ttk.Label(action_bar, text="Selected: 0 | Visible: 0 | Hidden: 0")
        self.selection_label.grid(row=0, column=0, sticky="w")

        ttk.Button(action_bar, text="Select all visible", command=self.select_all_visible).grid(row=0, column=1, padx=4)
        ttk.Button(action_bar, text="Clear selection", command=self.clear_selection).grid(row=0, column=2, padx=4)
        ttk.Button(action_bar, text="Review selection", command=self.review_selection).grid(row=0, column=3, padx=4)
        ttk.Button(action_bar, text="Move selected to Bin (disabled)", state=tk.DISABLED).grid(row=0, column=4, padx=(6, 0))

        status_bar = ttk.Label(self.root, textvariable=self.status_var, anchor="w", relief=tk.SUNKEN)
        status_bar.grid(row=2, column=0, sticky="ew")

    def _bind_events(self) -> None:
        self.search_var.trace_add("write", lambda *_: self.apply_filters(clear_preview=True))
        self.group_list.bind("<<ListboxSelect>>", self._on_group_change)
        self.message_table.bind("<<TreeviewSelect>>", self._on_message_focus)
        self.message_table.bind("<Double-1>", self._toggle_selected_row)

    def load_demo(self) -> None:
        self.messages = load_demo_messages()
        self._set_messages(source_label="offline demo")

    def import_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Email evidence CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            loaded = load_messages_from_csv(path)
        except OSError as error:
            messagebox.showerror("Import failed", str(error))
            return

        self.messages = loaded
        self._set_messages(source_label=path)

    def _set_messages(self, source_label: str) -> None:
        self.message_index = {item.message_key: item for item in self.messages}
        self.selection_state.clear_selection()
        self.clear_preview()
        self.status_var.set(f"Loaded {len(self.messages)} messages from {source_label}.")
        self._refresh_groups()
        self.apply_filters(clear_preview=True)

    def _refresh_groups(self) -> None:
        grouped = group_by_sender_domain(self.messages)
        self.group_list.delete(0, tk.END)
        self.group_list.insert(tk.END, "All sender domains")
        for domain, records in grouped.items():
            self.group_list.insert(tk.END, f"{domain} ({len(records)})")
        self.group_list.selection_clear(0, tk.END)
        self.group_list.selection_set(0)

    def _on_group_change(self, _event: tk.Event) -> None:
        self.apply_filters(clear_preview=True)

    def _selected_group_name(self) -> str:
        selected = self.group_list.curselection()
        if not selected:
            return "All sender domains"
        raw = self.group_list.get(selected[0])
        if raw == "All sender domains":
            return raw
        return raw.split(" (", 1)[0]

    def apply_filters(self, clear_preview: bool) -> None:
        group_name = self._selected_group_name()
        self.visible_messages = filter_messages(self.messages, group_name, self.search_var.get())
        self._populate_message_table()
        total_groups = len(group_by_sender_domain(self.messages))
        self.summary_var.set(
            f"{len(self.visible_messages)} visible message(s), {len(self.messages)} total, {total_groups} sender domain group(s)"
        )
        self._update_selection_label()
        if clear_preview:
            self.clear_preview()

    def _populate_message_table(self) -> None:
        self.message_table.delete(*self.message_table.get_children())
        for item in self.visible_messages:
            marker = "✓" if item.message_key in self.selection_state.selected_keys else ""
            self.message_table.insert(
                "",
                tk.END,
                iid=item.message_key,
                values=(
                    marker,
                    item.provider,
                    item.account,
                    item.folder,
                    f"{item.sender_name} <{item.sender_email}>",
                    item.subject,
                    item.date_text,
                ),
            )

    def _on_message_focus(self, _event: tk.Event) -> None:
        selected = self.message_table.selection()
        if not selected:
            self.clear_preview()
            return
        key = selected[0]
        message = self.message_index.get(key)
        if not message:
            self.clear_preview()
            return
        self.selection_state.set_preview(message)
        self.preview_subject_var.set(f"Subject: {message.subject}")
        self.preview_sender_var.set(
            f"From: {message.sender_name} <{message.sender_email}> | To: {message.to_value or '-'} | Cc: {message.cc_value or '-'}"
        )
        self.preview_meta_var.set(
            f"Provider: {message.provider} | Account: {message.account} | Folder: {message.folder} | Date: {message.date_text}"
        )

    def clear_preview(self) -> None:
        self.selection_state.clear_preview()
        self.preview_subject_var.set("")
        self.preview_sender_var.set("")
        self.preview_meta_var.set("")

    def _toggle_selected_row(self, _event: tk.Event) -> None:
        selected = self.message_table.selection()
        if not selected:
            return
        key = selected[0]
        message = self.message_index.get(key)
        if not message:
            return
        self.selection_state.toggle_message(message)
        self._populate_message_table()
        self._update_selection_label()

    def select_all_visible(self) -> None:
        self.selection_state.select_visible(self.visible_messages)
        self._populate_message_table()
        self._update_selection_label()

    def clear_selection(self) -> None:
        self.selection_state.clear_selection()
        self._populate_message_table()
        self._update_selection_label()

    def _update_selection_label(self) -> None:
        total, visible, hidden = self.selection_state.counts(self.visible_messages)
        self.selection_label.configure(text=f"Selected: {total} | Visible: {visible} | Hidden: {hidden}")

    def review_selection(self) -> None:
        selected_messages = [
            self.message_index[key]
            for key in self.selection_state.selected_keys
            if key in self.message_index
        ]
        if not selected_messages:
            messagebox.showinfo("Review selection", "No messages are selected.")
            return

        window = tk.Toplevel(self.root)
        window.title("Review selected messages")
        window.geometry("980x520")

        columns = ("provider", "account", "folder", "sender", "subject", "date")
        table = ttk.Treeview(window, columns=columns, show="headings")
        for col, width in (
            ("provider", 90),
            ("account", 160),
            ("folder", 100),
            ("sender", 220),
            ("subject", 300),
            ("date", 140),
        ):
            table.heading(col, text=col.capitalize())
            table.column(col, width=width, anchor="w")

        scrollbar = ttk.Scrollbar(window, orient=tk.VERTICAL, command=table.yview)
        table.configure(yscrollcommand=scrollbar.set)

        table.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        for item in selected_messages:
            table.insert(
                "",
                tk.END,
                values=(item.provider, item.account, item.folder, item.sender_email, item.subject, item.date_text),
            )


def run_app() -> None:
    root = tk.Tk()
    MailReviewApp(root)
    root.mainloop()

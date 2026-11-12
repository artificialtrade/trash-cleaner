# Mail Review (Milestone 1) - Windows Setup

This repository now includes a separate Python desktop prototype named **Mail Review** for safe offline email review.

## 1) Put the project in a folder

Example path:

`C:\Users\<YourUser>\Documents\trash-cleaner`

## 2) Open PowerShell in that folder

```powershell
cd C:\Users\<YourUser>\Documents\trash-cleaner
```

## 3) Create and activate a virtual environment

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, run this once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Then activate again.

## 4) Install Python test dependency

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements-mail-review.txt
```

## 5) Run offline demo mode

```powershell
python mail_review_app.py
```

The app starts with synthetic Gmail/iCloud/Outlook data.

## 6) Import your existing CSV

Inside the app:
1. Click **Import CSV**.
2. Select your `Email_evidence.csv`.
3. Review sender-domain groups on the left.

## 7) Selection and review flow

1. Use double-click on a row to toggle selection.
2. Use **Select all visible** for the current filtered rows only.
3. Click **Review selection** to open a confirmation list.
4. **Move selected to Bin** is intentionally disabled in Milestone 1.

## 8) Run Python tests

```powershell
pytest test_mail_review -q
```

## 9) What Milestone 1 includes

- Responsive Tkinter desktop layout.
- Persistent bottom action bar.
- Stale detail panel clearing when filters/groups change.
- Offline demo dataset.
- CSV import with UTF-8 BOM support.
- Sender-domain grouping and search.
- Selection counters for total/visible/hidden.

## 10) Not yet implemented in Milestone 1

- Live mailbox authentication and sync.
- Safe provider-specific move-to-trash execution.
- Background sync jobs and local SQLite cache.
- OAuth registration workflows in-app.


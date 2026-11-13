# Mail Review - Windows Setup

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

## 4) Install Python dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements-mail-review.txt
```

## 5) Configure live sign-in

The app never asks for a normal Gmail, Microsoft, or Apple password.

### Gmail OAuth

1. In Google Cloud Console, enable the Gmail API.
2. Create an OAuth client ID for a **Desktop app** and download its JSON file.
3. Copy it to `%LOCALAPPDATA%\TrashCleaner\mail-review\gmail-client-secret.json`, or set
   `TRASH_CLEANER_GMAIL_CLIENT_SECRET` to its path.
4. Choose **Gmail** and click **Connect Account**. A Google browser sign-in window opens.

### Outlook OAuth

1. Register a public-client desktop application in Microsoft Entra ID.
2. Enable public client flows and grant delegated `User.Read` and `Mail.ReadWrite`.
3. Set the application ID before launching:

```powershell
$env:TRASH_CLEANER_OUTLOOK_CLIENT_ID = "your-application-id"
```

4. Choose **Outlook** and click **Connect Account**. Microsoft sign-in opens in the browser.

### iCloud IMAP

1. Turn on two-factor authentication for your Apple Account.
2. Visit `https://appleid.apple.com` → **Sign-In and Security** → **App-Specific Passwords**.
3. Generate a password for Mail Review.
4. Choose **iCloud** and click **Connect Account**. Enter the iCloud email and the generated
   app-specific password. Do not enter your normal Apple ID password.

OAuth tokens and the iCloud app-specific password are stored through the operating system
credential manager using `keyring`; they are not written to the project folder.

## 6) Run offline demo mode

```powershell
python mail_review_app.py
```

The app starts with synthetic Gmail/iCloud/Outlook data.

## 7) Import your existing CSV

Inside the app:
1. Click **Import CSV**.
2. Select your `Email_evidence.csv`.
3. Review sender-domain groups on the left.

## 8) Selection, Trash, and restore

1. Use double-click on a row to toggle selection.
2. Use **Select all visible** for the current filtered rows only.
3. Use **Select sender group** to select the complete sender group.
4. Click **Review selection**, then **Move selected to Trash**.
5. Confirm the sender, folder, and message count summary. Live mail moves to the provider's
   Trash/Deleted Items folder; Demo and CSV records only simulate the move.
6. Use **Undo**, **Restore**, or **Recently trashed** immediately after a simulated move.

## 9) Run Python tests

```powershell
pytest test_mail_review -q
```

## 10) What the app includes

- Responsive Tkinter desktop layout.
- Persistent bottom action bar.
- Stale detail panel clearing when filters/groups change.
- Offline demo dataset.
- CSV import with UTF-8 BOM support.
- Sender-domain grouping and search.
- Selection counters for total/visible/hidden.
- Gmail, iCloud, Outlook, Demo, and CSV Import account selector.
- Account-scoped selection state and active-account banner.
- Sender-email groups, folder/read/attachment filters, and CSV-import labels.
- Confirmation, simulated Trash, restore/Undo, Recently trashed, and external action log.
- Gmail OAuth, Microsoft OAuth, and iCloud IMAP app-specific-password sign-in.
- Background mailbox loading with pause, resume, and cancel controls.

Demo and CSV actions never change a real email account. Action history is stored under the user's application data
directory (`%LOCALAPPDATA%\\TrashCleaner\\mail-review` on Windows).


# Photo Organizer — Dev & Release Guide

## Folder structure
```
photo-organizer/
├── photo_organizer.py     # Main app
├── build.bat              # Build script (EXE + installer)
├── installer.iss          # Inno Setup config
├── version.json           # Hosted on GitHub, read by app for updates
└── dist/                  # Created by PyInstaller
    └── Photo Organizer.exe
```

---

## One-time setup

### 1. Python
Download from https://python.org — check "Add to PATH" during install.

### 2. Inno Setup (for installer)
Download from https://jrsoftware.org/isinfo.php and install.

### 3. GitHub repo
- Create a new repo called `photo-organizer` (or whatever you want)
- Upload `version.json` to the root of the repo
- Update the `UPDATE_URL` line in `photo_organizer.py` to point to your repo:
  ```
  UPDATE_URL = "https://raw.githubusercontent.com/YOUR_USERNAME/photo-organizer/main/version.json"
  ```
- Update `DOWNLOAD_PAGE` similarly

---

## Building a release

1. Run `build.bat`
2. It produces:
   - `dist/Photo Organizer.exe` — standalone, no install needed
   - `installer_output/PhotoOrganizer_Setup_v1.0.0.exe` — proper Windows installer

The **installer** is what you ship. Customers double-click it, click Next twice, done.
It creates a Start Menu entry, optional desktop shortcut, and an uninstaller in Add/Remove Programs.

---

## Pushing an update to customers

1. Make your changes in `photo_organizer.py`
2. Bump `APP_VERSION` in the file (e.g. `"1.0.1"`)
3. Bump the version in `installer.iss` too (`#define AppVersion`)
4. Run `build.bat`
5. Go to GitHub → your repo → Releases → "Draft a new release"
6. Tag it `v1.0.1`, upload `PhotoOrganizer_Setup_v1.0.1.exe` as the release asset
7. Update `version.json` in your repo:
   ```json
   {
     "version": "1.0.1",
     "notes": "Fixed XMP matching on networked drives",
     "download_url": "https://github.com/YOUR_USERNAME/photo-organizer/releases/latest"
   }
   ```
8. Commit and push `version.json`

Next time any customer opens the app, it checks that file, sees 1.0.1 > 1.0.0,
and shows a green update banner at the top with a "Download Update" button.
They click it, download the new installer, run it — done.

---

## Selling it (Gumroad)

1. Go to https://gumroad.com and create a free account
2. Create a product → upload `PhotoOrganizer_Setup_v1.0.0.exe`
3. Set your price
4. Publish — you get a link you can share anywhere
5. Gumroad handles payment, delivery, and receipts automatically
6. When you release updates, upload the new installer to the same Gumroad product
   so new buyers always get the latest. Existing buyers get a redownload link via email.

No server required. No backend. No code. Just update `version.json` on GitHub
and upload a new file to Gumroad.

---

## License key system (optional, future)
If you want to lock the app to paying customers only, the flow would be:
- Gumroad generates a unique license key per purchase
- App prompts for the key on first launch, validates it against a simple API
- Simple APIs for this: Gumroad has a built-in license key API at no extra cost

This can be added later without changing the core app much.

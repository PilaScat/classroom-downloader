# Classroom Downloader

Automatically downloads all materials from Google Classroom and keeps them in sync.  
Google Workspace files are exported in both PDF and the corresponding Office format.

## Export formats

| Google type | Output files |
|---|---|
| Google Doc | `.pdf` + `.docx` |
| Google Sheet | `.pdf` + `.xlsx` |
| Google Slides | `.pdf` + `.pptx` |
| Google Drawing | `.pdf` |
| Binary files (PDF, images, …) | direct download |

## Download structure

```
downloads/
├── file_non_scaricati.txt   ← auto-generated if any files could not be downloaded
└── Course Name/
    ├── Materiali/
    │   └── Material Title/
    │       ├── file.pdf
    │       └── file.docx
    ├── Compiti/
    │   └── Assignment Title/
    │       └── file.pdf
    └── Annunci/
        └── file.pdf
```

---

## Setup

### 1. Create a Google Cloud project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or use an existing one)
3. Enable the following APIs:
   - **Google Classroom API**
   - **Google Drive API**
4. Go to **APIs & Services → Credentials**
5. Create credentials → **OAuth 2.0 Client ID**
   - Application type: **Desktop app**
6. Download the JSON file and rename it `credentials.json`
7. Place it in the `data/` folder:

```bash
mkdir data
mv ~/Downloads/credentials.json data/credentials.json
```

### 2. Create the virtual environment and install dependencies

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 3. Configure (optional)

```bash
cp .env.example .env
```

Edit `.env` if you want to change the sync interval or directory paths.

### 4. Authenticate (once only)

```bash
.venv/bin/python src/main.py auth
```

A URL will be printed — open it in your browser and authorize the app with your Google account.  
The token is saved automatically to `data/token.pickle`.

### 5. Run the downloader

```bash
.venv/bin/python src/main.py
```

To run it in the background:

```bash
nohup .venv/bin/python src/main.py &
```

---

## Configuration

Edit `.env` (copied from `.env.example`):

```env
SYNC_INTERVAL_MINUTES=60   # sync frequency in minutes

# Only download files of these MIME types (leave empty for everything)
ALLOWED_MIME_TYPES=application/pdf
```

Google Workspace files (Docs, Sheets, Slides) are always exported to PDF/Office regardless of this filter.

Common MIME types:

| Type | MIME |
|------|------|
| PDF | `application/pdf` |
| Video MP4 | `video/mp4` |
| Image JPEG | `image/jpeg` |
| Image PNG | `image/png` |

---

## Useful commands

| Command | Description |
|---------|-------------|
| `.venv/bin/python src/main.py` | Start the sync daemon |
| `.venv/bin/python src/main.py auth` | Re-authenticate |
| `nohup .venv/bin/python src/main.py &` | Run in background |

To force a full re-download of all files, delete `data/state.json`.

---

## How it works

1. On first start, performs an immediate full sync
2. Every `SYNC_INTERVAL_MINUTES` minutes, checks for new materials
3. Tracks already-downloaded files in `data/state.json`
4. If a local file is deleted, it will be re-downloaded on the next cycle
5. Google Workspace files are exported to PDF and the corresponding Office format via the Drive API
6. On rate limit or transient errors, retries automatically up to 5 times with exponential backoff
7. Files that cannot be downloaded (e.g. owner-restricted) are listed in `downloads/file_non_scaricati.txt` with a direct Drive link

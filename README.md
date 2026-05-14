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

### 2. First-time authentication (once only)

Authentication must be run **directly on the host** (not inside Docker) because it requires a local browser.

```bash
# Create a virtualenv and install dependencies
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Run authentication
DATA_DIR=./data .venv/bin/python src/main.py auth
```

A URL will be printed — open it in your browser and authorize the app with your Google account.  
The token is saved automatically to `data/token.pickle` and used by Docker on every sync.

### 3. Start the downloader

```bash
docker compose up -d
```

### 4. Check logs

```bash
docker compose logs -f
```

---

## Configuration

Copy `.env.example` to `.env` and edit as needed:

```env
SYNC_INTERVAL_MINUTES=60   # sync frequency in minutes
```

---

## Useful commands

| Command | Description |
|---------|-------------|
| `docker compose up -d` | Start in background |
| `docker compose down` | Stop |
| `docker compose logs -f` | Follow logs |
| `DATA_DIR=./data .venv/bin/python src/main.py auth` | Re-authenticate |

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

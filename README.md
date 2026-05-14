# Classroom Downloader

Scarica automaticamente tutto il materiale da Google Classroom e lo mantiene sincronizzato.  
I file Google Workspace vengono esportati sia in PDF che nel formato Office corrispondente.

## Formati di esportazione

| Tipo Google | File prodotti |
|---|---|
| Google Doc | `.pdf` + `.docx` |
| Google Sheet | `.pdf` + `.xlsx` |
| Google Slides | `.pdf` + `.pptx` |
| Google Drawing | `.pdf` |
| File binari (PDF, immagini, …) | download diretto |

## Struttura dei download

```
downloads/
├── file_non_scaricati.txt   ← generato automaticamente se ci sono errori
└── Nome Corso/
    ├── Materiali/
    │   └── Titolo Materiale/
    │       ├── file.pdf
    │       └── file.docx
    ├── Compiti/
    │   └── Titolo Compito/
    │       └── file.pdf
    └── Annunci/
        └── file.pdf
```

---

## Setup

### 1. Crea il progetto Google Cloud

1. Vai su [Google Cloud Console](https://console.cloud.google.com/)
2. Crea un nuovo progetto (o usa uno esistente)
3. Abilita le API:
   - **Google Classroom API**
   - **Google Drive API**
4. Vai su **APIs & Services → Credentials**
5. Crea credenziali → **OAuth 2.0 Client ID**
   - Application type: **Desktop app**
6. Scarica il file JSON e rinominalo `credentials.json`
7. Mettilo nella cartella `data/`:

```bash
mkdir data
mv ~/Downloads/credentials.json data/credentials.json
```

### 2. Prima autenticazione (una volta sola)

L'autenticazione va eseguita **direttamente sull'host** (non dentro Docker) perché richiede un browser locale.

```bash
# Crea un virtualenv e installa le dipendenze
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Esegui l'autenticazione
DATA_DIR=./data .venv/bin/python src/main.py auth
```

Verrà stampato un URL — aprilo nel browser, autorizza l'app con il tuo account Google.  
Il token viene salvato automaticamente in `data/token.pickle` e usato da Docker a ogni sync.

### 3. Avvia il downloader

```bash
docker compose up -d
```

### 4. Controlla i log

```bash
docker compose logs -f
```

---

## Configurazione

Copia `.env.example` in `.env` e modifica:

```env
SYNC_INTERVAL_MINUTES=60   # frequenza di sincronizzazione
```

---

## Comandi utili

| Comando | Descrizione |
|---------|-------------|
| `docker compose up -d` | Avvia in background |
| `docker compose down` | Ferma |
| `docker compose logs -f` | Segui i log |
| `DATA_DIR=./data .venv/bin/python src/main.py auth` | Ri-autentica |

Per forzare il re-download di tutti i file, elimina `data/state.json`.

---

## Come funziona

1. Al primo avvio esegue subito una sincronizzazione completa
2. Ogni `SYNC_INTERVAL_MINUTES` minuti controlla se ci sono nuovi materiali
3. Tiene traccia dei file già scaricati in `data/state.json`
4. Se un file locale viene eliminato, viene riscaricato al prossimo ciclo
5. I file Google Workspace vengono esportati in PDF e nel formato Office corrispondente tramite la Drive API
6. In caso di rate limit o errori transitori, riprova automaticamente fino a 5 volte con backoff esponenziale
7. I file non scaricabili (es. con restrizioni del proprietario) vengono elencati in `downloads/file_non_scaricati.txt` con il link Drive diretto

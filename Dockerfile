FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ .

# /data  → token.pickle, credentials.json, state.json (mount as volume)
# /downloads → downloaded files (mount as volume)
VOLUME ["/data", "/downloads"]

ENV DATA_DIR=/data \
    DOWNLOADS_DIR=/downloads \
    SYNC_INTERVAL_MINUTES=60

CMD ["python", "main.py"]

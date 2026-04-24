# TALK Deployment Guide

This document covers three supported deployment styles:

- Docker Compose: recommended for most home users
- systemd: good for a Linux NAS or old mini PC without Docker
- Bare metal: manual process for debugging or simple single-user setups

## 1. Common planning

### Port plan

- Default app port: `8000`
- Web UI: `http://<host>:8000`
- API docs: `http://<host>:8000/docs`
- Health check: `http://<host>:8000/healthz`

If you will expose TALK through a reverse proxy, keep the app on `127.0.0.1:8000` or another private port and publish only the proxy.

### Files that must persist

- `talk.db`: SQLite database
- `storage/`: uploaded files
- `logs/`: JSON logs
- `backups/`: backup snapshots
- `config.toml`: runtime config

### Before you start

Edit `config.toml` and set:

- `[server].public_url` to the real LAN or domain URL
- `[server].host` if you run without Docker and need direct LAN access
- `[server].port` if `8000` is already used

## 2. Docker Compose

### Start

From the project root:

```bash
docker compose up -d --build
```

This project ships with:

- `Dockerfile`
- `docker-compose.yml`
- persistent bind mounts for `storage`, `talk.db`, `logs`, `backups`, and `config.toml`

On a brand-new checkout, create the writable paths first:

```bash
mkdir -p storage logs backups
touch talk.db
```

### Stop

```bash
docker compose down
```

### Verify

```bash
docker compose ps
docker compose logs -f talk
curl http://127.0.0.1:8000/healthz
```

### Trigger a backup

```bash
docker compose exec talk python scripts/backup_db.py
```

### Create the first administrator

After the container starts, either use the Web UI first-run form or run:

```bash
docker compose exec talk python scripts/create_admin.py --id human:home --name "Home" --key "change-this-to-a-long-random-string"
```

With no arguments, the script runs in interactive mode:

```bash
docker compose exec talk python scripts/create_admin.py
```

### Persistence check

1. Start TALK.
2. Log in and send one message.
3. Upload one file.
4. Run a backup.
5. Stop and start again:

```bash
docker compose down
docker compose up -d
```

6. Confirm:
   - the message is still visible
   - the uploaded file is still downloadable
   - `logs/` still contains log files
   - `backups/` still contains backup snapshots

## 3. systemd on Linux

### Install

```bash
sudo useradd --system --create-home --home-dir /opt/talk --shell /usr/sbin/nologin talk
sudo mkdir -p /opt/talk
sudo chown -R talk:talk /opt/talk
sudo -u talk git clone <your-repo-url> /opt/talk
cd /opt/talk
sudo -u talk mkdir -p /opt/talk/storage /opt/talk/logs /opt/talk/backups
sudo -u talk touch /opt/talk/talk.db
sudo -u talk python3 -m venv /opt/talk/.venv
sudo -u talk /opt/talk/.venv/bin/pip install -r requirements.txt
```

Edit `/opt/talk/config.toml` before first start.

### Service file

Use [deploy/talk.service](../deploy/talk.service) as the template:

```bash
sudo cp deploy/talk.service /etc/systemd/system/talk.service
sudo systemctl daemon-reload
sudo systemctl enable --now talk
```

### Verify

```bash
sudo systemctl status talk
journalctl -u talk -f
curl http://127.0.0.1:8000/healthz
```

### Restart after config changes

```bash
sudo systemctl restart talk
```

### Create the first administrator

After the service is up, either use the Web UI first-run form or run:

```bash
python scripts/create_admin.py --id human:home --name "Home" --key "change-this-to-a-long-random-string"
```

## 4. Bare metal

Use this when you want the simplest possible manual run.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
```

If you want auto-restart, use `tmux`, `screen`, `supervisord`, or preferably `systemd`.

To create the first administrator without the Web UI guide:

```bash
python scripts/create_admin.py --id human:home --name "Home" --key "change-this-to-a-long-random-string"
```

## 5. Reverse proxy examples

## Nginx

```nginx
server {
    listen 80;
    server_name talk.lan;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /ws {
        proxy_pass http://127.0.0.1:8000/ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

## Caddy

```caddy
talk.lan {
    reverse_proxy 127.0.0.1:8000
}
```

For TLS on a private LAN, use local CA tooling or a DNS name Caddy can issue certificates for.

## 6. Backup and restore

### Create a backup

Docker:

```bash
docker compose exec talk python scripts/backup_db.py
```

systemd or bare metal:

```bash
python scripts/backup_db.py
```

### Restore from backup

The full restore sequence is:

1. Stop TALK.
2. Replace `talk.db` with the backup file.
3. Start TALK.
4. Verify messages and file access.

Docker:

```bash
docker compose down
cp backups/backup_YYYY-MM-DD.db talk.db
docker compose up -d
curl http://127.0.0.1:8000/healthz
```

systemd:

```bash
sudo systemctl stop talk
cp /opt/talk/backups/backup_YYYY-MM-DD.db /opt/talk/talk.db
sudo systemctl start talk
curl http://127.0.0.1:8000/healthz
```

Bare metal:

```bash
pkill -f "uvicorn server.main:app"
cp backups/backup_YYYY-MM-DD.db talk.db
python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
```

### What restore does not do

- It restores the SQLite database only.
- It does not recreate deleted files in `storage/`.
- For a full recovery, back up both `talk.db` and `storage/`.

## 7. Recommended home setup

For most families:

- Use Docker Compose
- Keep TALK on a fixed LAN IP
- Put Nginx or Caddy in front only if you need a stable hostname
- Run `scripts/backup_db.py` daily with cron or the NAS scheduler
- Back up `storage/` together with `talk.db`

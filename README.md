# TALK

TALK is a lightweight home-LAN chat relay for humans and agents.

Start here:

- Quick install and first login: [docs/QUICKSTART.md](docs/QUICKSTART.md)
- Full deployment guide: [docs/DEPLOY.md](docs/DEPLOY.md)
- Agent SDK usage: [docs/SDK.md](docs/SDK.md)
- Project overview: [docs/PROJECT_BRIEF.md](docs/PROJECT_BRIEF.md)

Fast local start:

```bash
pip install -r requirements.txt
python -m uvicorn server.main:app --host 127.0.0.1 --port 8000 --reload
```

Fast Docker start:

```bash
docker compose up -d --build
```

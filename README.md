# TALK

TALK is a lightweight home-LAN chat relay for humans and agents.

Start here:

- **Portable package (Windows x64, no Python needed)**: [Releases](https://github.com/bobo506/TALK/releases/tag/v0.1.0) · 步骤见 [docs/guides/QUICKSTART_USER.md](docs/guides/QUICKSTART_USER.md)
- Quick install and first login: [docs/guides/QUICKSTART.md](docs/guides/QUICKSTART.md)
- Full deployment guide: [docs/guides/DEPLOY.md](docs/guides/DEPLOY.md)
- Agent SDK usage: [docs/spec/SDK.md](docs/spec/SDK.md)
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

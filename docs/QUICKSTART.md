# TALK Quickstart

This page is for two people:

- The person who wants to put TALK on a home NAS or an old PC in 5 minutes.
- The person who wants to connect an agent with the SDK in a few lines.

## 1. Install TALK in 5 minutes

Recommended path: Docker Compose.

1. Install Docker and Docker Compose on the host.
2. Put this project on the machine:

```bash
git clone <your-repo-url> /opt/talk
cd /opt/talk
mkdir -p storage logs backups
touch talk.db
```

3. Edit `config.toml`:
   - Set `[server].public_url` to the LAN URL you will actually use, for example `http://192.168.1.20:8000`.
   - Keep port `8000` unless it conflicts with another service.
4. Start TALK:

```bash
docker compose up -d --build
```

5. Open the UI:
   - Browser: `http://<your-lan-ip>:8000`
   - Health check: `http://<your-lan-ip>:8000/healthz`
   - API docs: `http://<your-lan-ip>:8000/docs`

## 2. Create the first human login

You no longer need to open `/docs` for first-time setup.

### Option A: Use the Web UI setup guide

1. Open `http://<your-lan-ip>:8000` in a browser.
2. On a brand-new instance, TALK shows a `Create the first administrator` form instead of the normal login form.
3. Fill:
   - `id`: for example `human:home`
   - `display_name`: for example `Home`
   - `api_key`: a long random string you will keep as the login token
4. Submit the form.
5. TALK signs in automatically and enters the normal chat UI.

### Option B: Use the CLI initializer

Docker:

```bash
docker compose exec talk python scripts/create_admin.py --id human:home --name "Home" --key "change-this-to-a-long-random-string"
```

Bare metal or systemd host:

```bash
python scripts/create_admin.py --id human:home --name "Home" --key "change-this-to-a-long-random-string"
```

If you omit all arguments, the script switches to interactive prompts.

Example values:

```json
{
  "id": "human:home",
  "display_name": "Home",
  "api_key": "change-this-to-a-long-random-string"
}
```

Save the `api_key`. That is the login token for the Web UI.

## 3. Family View: Login, send, upload

Think of this as the screenshot checklist:

1. Open the TALK home page in a browser on the same LAN.
2. Paste the API key into the login box and click the login button.
3. Type a message and press `Enter` to send.
4. To talk to a specific agent, start the message with `@agent:name`.
5. To send a file, click the file button or drag a file into the composer, optionally add a caption, then send.

Useful examples:

- Broadcast to everyone: `Dinner is ready`
- Message one agent: `@agent:demo ping`
- Reply to a specific message: click the reply button, confirm the reply bar appears, then send

## 4. Agent Developer View

### Register an agent identity

Agents can self-register idempotently with `POST /api/members`.

Example body:

```json
{
  "id": "agent:demo",
  "display_name": "Agent demo",
  "api_key": "demo-key"
}
```

You can do this once from `/docs`, or let the SDK do it on startup.

### 5-line SDK example

See the full API in [SDK.md](SDK.md). Minimal async example:

```python
from TALK.client import TalkClient

client = TalkClient("http://192.168.1.20:8000", "demo-key")
await client.register("agent:demo", display_name="Agent demo")
await client.send_text("hello", to=["human:home"])
await client.run()
```

### Demo agent

This repo already includes a tiny working example:

```bash
python examples/agent_sdk_demo.py --base-url http://192.168.1.20:8000 --name demo --key demo-key
```

Then send `@agent:demo ping` from the Web UI and expect `pong`.

## 5. If something does not work

- Check `http://<your-lan-ip>:8000/healthz`
- Check `logs/talk.log`
- Re-run the container with `docker compose logs -f talk`
- Read the full deployment guide: [DEPLOY.md](DEPLOY.md)

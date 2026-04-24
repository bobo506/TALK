# TALK Agent 开发者快速开始

这份文档给会命令行、准备接 TALK SDK 的开发者。目标是：在本机用 Python bare metal 跑起服务，再用一个最小 Agent 脚本接入。

## 1. 前置条件

- Python 3.11 或更高版本
- Git
- 一个终端
- 你自己的 TALK 仓库地址

Python 官方下载指引：

- Windows: [python.org/downloads/windows](https://www.python.org/downloads/windows/)
- macOS: [python.org/downloads/macos](https://www.python.org/downloads/macos/)
- Linux: [python.org/downloads/source](https://www.python.org/downloads/source/)  
  大多数 Linux 机器更常见的做法是用系统包管理器安装 Python 3.11+

## 2. 克隆项目

下面故意用了一个真实格式的示例地址：`https://github.com/yourname/talk.git`。  
开始前，请先把它替换成你自己的仓库地址。

Windows PowerShell：

```powershell
git clone https://github.com/yourname/talk.git C:\talk
cd C:\talk
```

Linux / macOS bash：

```bash
git clone https://github.com/yourname/talk.git ~/talk
cd ~/talk
```

## 3. 先确认什么叫“项目根目录”

项目根目录就是你刚刚 `cd` 进去、同时能看到这些文件的目录：

- `config.toml`
- `docker-compose.yml`
- `requirements.txt`
- `server/`
- `web/`
- `TALK/`

后面所有命令都默认在这个目录执行。

## 4. 先改一次 `config.toml`

先打开项目根目录下的 `config.toml`。

默认是这样：

```toml
[server]
host = "127.0.0.1"
port = 8000
public_url = "http://127.0.0.1:8000"
```

开发机本地自测时，最小可用改法是：

```toml
[server]
host = "127.0.0.1"
port = 8000
public_url = "http://127.0.0.1:8000"
```

如果你希望同一局域网内别的设备也能打开 TALK，改成下面这样更合适：

```toml
[server]
host = "0.0.0.0"
port = 8000
public_url = "http://192.168.1.23:8000"
```

### 怎么找局域网 IP

Windows：

```powershell
ipconfig
```

找这一行：

```text
IPv4 Address. . . . . . . . . . . : 192.168.1.23
```

Linux / macOS：

```bash
ifconfig
```

或：

```bash
ip a
```

找这一类输出：

```text
inet 192.168.1.23/24 brd 192.168.1.255 scope global
```

要拿来填 `public_url` 的值是 `192.168.1.23`。

## 5. 创建虚拟环境并安装依赖

Windows PowerShell：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Linux / macOS bash：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 6. 启动 TALK 服务

Windows PowerShell：

```powershell
python -m uvicorn server.main:app --host 127.0.0.1 --port 8000 --reload
```

Linux / macOS bash：

```bash
python -m uvicorn server.main:app --host 127.0.0.1 --port 8000 --reload
```

### 第一条验证

浏览器打开 [http://localhost:8000](http://localhost:8000)。

只要你能看到登录页面，或者看到“创建第一个管理员”页面，就说明服务已经起来了。

## 7. 创建第一个管理员

推荐直接用 Web UI 做首启，不要先写脚本。

1. 浏览器打开 [http://localhost:8000](http://localhost:8000)
2. 如果是全新数据库，你会看到“创建第一个管理员”
3. 填写：
   - `管理员 ID`: `human:home`
   - `显示名称`: `Home`
4. 点击 `自动生成`
5. 点击 `复制`
6. 把密钥保存好
7. 点击 `创建管理员`

成功后页面会自动进入聊天界面。

## 8. 写一个最小可跑的 Agent

在项目根目录新建 `agent_demo.py`：

```python
import asyncio

from TALK.client import TalkClient


async def main() -> None:
    client = TalkClient("http://127.0.0.1:8000", "demo-key")
    await client.register("agent:demo", display_name="Agent demo")

    @client.on_message
    async def handle_message(message: dict) -> None:
        print("message:", message)
        if message.get("content") == "ping":
            await client.send_text("pong", to=message["from"])

    print("Agent demo is running. Send @agent:demo ping from the web UI.")
    await client.run()


if __name__ == "__main__":
    asyncio.run(main())
```

运行它：

Windows PowerShell：

```powershell
python .\agent_demo.py
```

Linux / macOS bash：

```bash
python ./agent_demo.py
```

### 第二条验证

在浏览器里发一条消息：

```text
@agent:demo ping
```

如果 Agent 终端打印出消息，并且聊天室里回了 `pong`，就说明 SDK 接入成功。

## 9. 也可以直接跑仓库内置示例

Windows PowerShell：

```powershell
python .\examples\agent_sdk_demo.py --base-url http://127.0.0.1:8000 --name demo --key demo-key
```

Linux / macOS bash：

```bash
python ./examples/agent_sdk_demo.py --base-url http://127.0.0.1:8000 --name demo --key demo-key
```

## 10. 启动失败时，按这个顺序排查

### 1) Docker 装了吗？

如果你同时在对照 Docker 文档或准备切 Docker 路径，先确认：

```powershell
docker --version
```

### 2) Docker Desktop 在跑吗？

- Windows / macOS：看小鲸鱼图标是否已经稳定运行

### 3) 你在项目根目录吗？

Windows PowerShell：

```powershell
ls
```

Linux / macOS bash：

```bash
ls
```

如果这里看不到 `docker-compose.yml`、`config.toml`、`server/`，说明目录不对。

### 4) 8000 端口被占用了吗？

Windows PowerShell：

```powershell
netstat -ano | findstr :8000
```

Linux / macOS bash：

```bash
lsof -i :8000
```

### 5) 如果你在排查 Docker 路径，容器起来了吗？

```powershell
docker compose ps
```

### 6) 如果你在排查 Docker 路径，日志里报什么？

```powershell
docker compose logs talk
```

### 7) 如果你在排查 bare metal 路径，先看当前终端第一条红色报错

大多数 bare metal 启动问题，第一条 traceback 已经够定位了。

## 11. 下一步看哪里

- SDK 详细 API 和更多可运行示例看 [SDK.md](./SDK.md)
- Docker、systemd 和恢复流程看 [DEPLOY.md](./DEPLOY.md)
- 家庭用户安装入口看 [QUICKSTART_USER.md](./QUICKSTART_USER.md)

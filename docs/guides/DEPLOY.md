# TALK Deployment Guide

本文覆盖 3 种部署路径：

- Docker Compose：最适合家庭用户和大多数自部署场景
- systemd：适合 Linux 小主机、NAS 或长期常驻服务
- Bare metal：适合调试和本地开发

## 1. 通用准备

### 端口规划

- 默认端口：`8000`
- Web UI：`http://<host>:8000`
- API 文档：`http://<host>:8000/docs`
- 健康检查：`http://<host>:8000/healthz`

如果前面还有反向代理，建议 TALK 只监听私有地址，再由反向代理对外暴露。

### 必须持久化的文件

- `talk.db`
- `storage/`
- `logs/`
- `backups/`
- `config.toml`

### 开始前先改 `config.toml`

- `[server].public_url`：改成实际访问 TALK 的地址
- `[server].host`：非 Docker 直连局域网时，通常改成 `0.0.0.0`
- `[server].port`：如果 `8000` 已占用，再改它

## 2. Docker Compose

### 前置条件

你需要先装好这些东西：

- Docker Desktop，或 Linux 上的 Docker Engine + Compose 插件
- 一个包含 `docker-compose.yml` 的 TALK 项目根目录
- 本机 `8000` 端口未被其它程序占用

### 启动

在项目根目录执行：

```bash
docker compose up -d --build
```

本项目自带：

- `Dockerfile`
- `docker-compose.yml`
- `storage`、`talk.db`、`logs`、`backups`、`config.toml` 的持久化挂载

### 停止

```bash
docker compose down
```

### 验证

```bash
docker compose ps
docker compose logs -f talk
curl http://127.0.0.1:8000/healthz
```

### 创建第一个管理员

容器启动后，优先使用 Web UI 首启向导。  
如果你更想走命令行，也可以：

```bash
docker compose exec talk python scripts/create_admin.py --id human:home --name "Home" --key "change-this-to-a-long-random-string"
```

### 触发备份

```bash
docker compose exec talk python scripts/backup_db.py
```

## 3. systemd on Linux

### 前置条件

你需要先装好这些东西：

- 一台带 `systemd` 的 Linux 主机
- `python3.11` 或更高版本
- `git`
- `python3-venv`
- 一个可运行服务的 Linux 用户

### 安装

```bash
sudo useradd --system --create-home --home-dir /opt/talk --shell /usr/sbin/nologin talk
sudo mkdir -p /opt/talk
sudo chown -R talk:talk /opt/talk
sudo -u talk git clone https://github.com/yourname/talk.git /opt/talk
cd /opt/talk
sudo -u talk mkdir -p /opt/talk/storage /opt/talk/logs /opt/talk/backups
sudo -u talk touch /opt/talk/talk.db
sudo -u talk python3 -m venv /opt/talk/.venv
sudo -u talk /opt/talk/.venv/bin/pip install -r requirements.txt
```

启动前先编辑 `/opt/talk/config.toml`。

### 安装服务

使用 [deploy/talk.service](../../deploy/talk.service) 作为模板：

```bash
sudo cp deploy/talk.service /etc/systemd/system/talk.service
sudo systemctl daemon-reload
sudo systemctl enable --now talk
```

### 验证

```bash
sudo systemctl status talk
journalctl -u talk -f
curl http://127.0.0.1:8000/healthz
```

### 配置修改后重启

```bash
sudo systemctl restart talk
```

### 创建第一个管理员

服务起来后，优先使用 Web UI 首启向导。  
如果你要命令行创建：

```bash
python scripts/create_admin.py --id human:home --name "Home" --key "change-this-to-a-long-random-string"
```

## 4. Bare metal

### 前置条件

你需要先装好这些东西：

- Python 3.11+
- `pip`
- 一个终端
- 已经切到 TALK 项目根目录

### 启动

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
```

如果你需要自动拉起和守护，优先用 `systemd`，不要长期依赖手工终端。

### 创建第一个管理员

优先使用 Web UI 首启向导。  
如果你要命令行创建：

```bash
python scripts/create_admin.py --id human:home --name "Home" --key "change-this-to-a-long-random-string"
```

## 5. Reverse Proxy Examples

### Nginx

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

### Caddy

```caddy
talk.lan {
    reverse_proxy 127.0.0.1:8000
}
```

## 6. Backup and Restore

### 创建备份

Docker：

```bash
docker compose exec talk python scripts/backup_db.py
```

systemd 或 bare metal：

```bash
python scripts/backup_db.py
```

### 恢复备份

标准流程：

1. 停服务
2. 用备份文件替换 `talk.db`
3. 启服务
4. 验证消息和文件是否正常

Docker：

```bash
docker compose down
cp backups/backup_YYYY-MM-DD.db talk.db
docker compose up -d
curl http://127.0.0.1:8000/healthz
```

systemd：

```bash
sudo systemctl stop talk
cp /opt/talk/backups/backup_YYYY-MM-DD.db /opt/talk/talk.db
sudo systemctl start talk
curl http://127.0.0.1:8000/healthz
```

Bare metal：

```bash
pkill -f "uvicorn server.main:app"
cp backups/backup_YYYY-MM-DD.db talk.db
python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
```

### 恢复不会做什么

- 它只恢复 SQLite 数据库
- 它不会自动补回已经丢失的 `storage/` 文件实体
- 想完整恢复，必须一起备份 `talk.db` 和 `storage/`

## 7. 家庭部署建议

大多数家庭场景建议：

- 首选 Docker Compose
- 给运行 TALK 的设备一个固定局域网 IP
- 只有在你需要稳定域名时，再加 Nginx 或 Caddy
- 定期运行 `scripts/backup_db.py`
- `storage/` 和 `talk.db` 一起备份

# TALK 家庭用户快速开始

这份文档给第一次接触 TALK 的家庭用户。目标只有一个：用 Docker Desktop 把 TALK 跑起来，然后在浏览器里看到可用界面。

## 1. 先准备好这 4 样东西

- 一台 Windows 或 macOS 电脑
- 一个现代浏览器：Chrome、Edge、Safari 都可以
- Docker Desktop：
  [Docker Desktop 官方下载](https://www.docker.com/products/docker-desktop/)
- TALK 项目文件夹：
  你可以从仓库网页点 `Code` -> `Download ZIP` 下载压缩包，再解压到桌面；也可以让会电脑的人直接把整个 `TALK` 文件夹发给你

## 2. 先确认什么叫“项目根目录”

后面所有操作都要在“项目根目录”里进行。

你打开 `TALK` 文件夹后，如果能同时看到这些文件，就说明你已经到了项目根目录：

- `docker-compose.yml`
- `config.toml`
- `Dockerfile`
- `server/`
- `web/`

## 3. 先改一次 `config.toml`

1. 在项目根目录里双击打开 `config.toml`
2. 找到这一段：

```toml
[server]
host = "127.0.0.1"
port = 8000
public_url = "http://127.0.0.1:8000"
```

3. 先不要改 `port`
4. 只把 `public_url` 改成你这台电脑在局域网里的地址

改之前：

```toml
public_url = "http://127.0.0.1:8000"
```

改之后示例：

```toml
public_url = "http://192.168.1.23:8000"
```

### 怎么找你电脑的局域网 IP

Windows：

1. 按 `Win + R`
2. 输入 `cmd`
3. 回车
4. 输入：

```powershell
ipconfig
```

你要找的是 `IPv4 Address` 那一行，例如：

```text
Wireless LAN adapter Wi-Fi:

   IPv4 Address. . . . . . . . . . . : 192.168.1.23
```

这里要填进 `config.toml` 的值就是 `192.168.1.23`。

macOS / Linux：

在终端输入下面任意一条：

```bash
ifconfig
```

或：

```bash
ip a
```

你要找的是类似下面这一行：

```text
inet 192.168.1.23/24 brd 192.168.1.255 scope global
```

这里要填进 `config.toml` 的值就是 `192.168.1.23`。

## 4. 启动 TALK

主流程里你只需要输入这一条命令。

### Windows

1. 用资源管理器打开项目根目录
2. 点击窗口最上面的地址栏
3. 输入 `powershell`
4. 回车
5. 在弹出的 PowerShell 窗口里输入：

```powershell
docker compose up -d
```

### macOS

1. 打开“终端”
2. 把项目根目录拖进终端窗口
3. 输入 `cd ` 后把文件夹拖进去，再回车
4. 输入：

```bash
docker compose up -d
```

### 什么画面算成功

- 命令执行完后没有红色报错
- Docker Desktop 左侧 `Containers` 页面里能看到一个叫 `talk` 的容器
- 它的状态是绿色的 `Running`

## 5. 打开浏览器验证

1. 浏览器打开 [http://localhost:8000](http://localhost:8000)
2. 如果你能看到登录页面或“创建第一个管理员”页面，就说明启动成功了

这是第一步验证，必须先过。

如果你还想让家里别的设备访问，再在手机或别的电脑上打开：

- `http://你的局域网IP:8000`
- 例如 [http://192.168.1.23:8000](http://192.168.1.23:8000)

## 6. 第一次创建管理员

如果这是全新的 TALK，你会看到“创建第一个管理员”页面。

按下面顺序做：

1. `管理员 ID` 填：`human:home`
2. `显示名称` 填：`Home`
3. 在 `登录密钥` 这一行，点击 `自动生成`
4. 再点击 `复制`
5. 把复制出来的密钥记到密码管理器、备忘录或其它可靠的地方
6. 点击 `创建管理员`

### 什么画面算成功

- 页面自动进入聊天界面
- 右上角能看到你刚创建的账号
- 以后登录时，填的就是刚才保存下来的那串密钥

## 7. 第二次打开时会看到什么

- 如果浏览器还保留当前会话，你可能会直接进入 TALK
- 如果没有自动登录，看到普通登录框也正常
- 把刚才保存的登录密钥贴进去，点登录即可

## 8. 启动失败时，按这个顺序排查

如果你自己不想排查，也可以把下面每一步的结果截图发给会技术的人。

### 1) Docker 装了吗？

```powershell
docker --version
```

成功时会看到类似：

```text
Docker version 27.x.x, build ...
```

### 2) Docker Desktop 在跑吗？

- Windows：看任务栏右下角有没有小鲸鱼图标
- macOS：看菜单栏有没有 Docker 小鲸鱼图标
- 如果图标还在转圈，请等它变成稳定状态再继续

### 3) 你在项目根目录吗？

在当前窗口执行：

```powershell
ls
```

如果看不到 `docker-compose.yml`，说明你不在项目根目录。

### 4) 8000 端口被别的软件占用了吗？

Windows：

```powershell
netstat -ano | findstr :8000
```

macOS / Linux：

```bash
lsof -i :8000
```

如果这里已经有别的程序占用了 `8000`，先关掉它，或者让懂技术的人帮你改 `config.toml` 里的端口。

### 5) 容器起来了吗？

```powershell
docker compose ps
```

你要看到 `talk` 这一行，而且状态应该是 `running`。

### 6) 容器日志里报什么？

```powershell
docker compose logs talk
```

直接把最后几十行复制给帮你排查的人，最有用。

## 9. 你现在应该已经能做什么

- 在浏览器里打开 TALK
- 用刚生成并保存的登录密钥登录
- 在局域网里把这个地址发给家人或别的设备

更完整的部署说明看 [DEPLOY.md](./DEPLOY.md)，Agent 开发者入口看 [QUICKSTART_AGENT.md](./QUICKSTART_AGENT.md)。

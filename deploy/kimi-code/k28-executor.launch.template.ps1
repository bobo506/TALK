# Kimi Code + K2.8 Preview 独立执行入口启动模板（PowerShell）。
#
# 这是模板，不会被任何程序自动读取。它本身不含任何密钥：
# 只把“仓库外的密钥文件路径”交给 scripts/kimi_k28_executor.py，
# 由脚本解析后在本进程内注入现有 bridges/kimi_bridge.py。
#
# 使用前：
#   1. 让新成员 agent:kimi-code-k28-preview 在 TALK 注册并取得**本人**的 API Key；
#      本入口不会自动首次注册，未注册的 Key 会在只读身份核验阶段被拒绝。
#   2. 把该 Key 写到仓库外的文件（默认 ~/.talk/agent-kimi-code-k28-preview.key）；
#      不要复用 agent:kimi 的 Key，也不要把 Key 正文写进本仓库。
#   3. 先跑离线检查，再启动。
#
# 本模板不修改全局 default_model，不执行官方 CLI 的登录/登出/更新。
#
# launch 的安全顺序（全部在 bridge 的 client.register 之前）：
#   固定受控命令 kimi --output-format stream-json -p（忽略 TALK_KIMI_COMMAND）
#   → 固定执行分级 --decision-tier execution（本地 .talk/groups.yaml 的 decision 不生效）
#   → 本次实际 native config.toml 的 alias/provider/model/tool_use 与项目绑定
#   → 只读 GET /api/members/me + 项目名册（本人 / kind=agent / dev / execution）
#   → 之后才进入既有 bridge。
# 身份说明：TALK 身份是**独立 TALK Key**（本人密钥，仓库外文件或 TALK_K28_KEY）；
# 官方 native managed 登录凭据由官方 CLI 自行读取，本入口不读取、不复制。

$ErrorActionPreference = 'Stop'
$repo = 'D:\claude-test\TALK'
$keyFile = Join-Path $env:USERPROFILE '.talk\agent-kimi-code-k28-preview.key'
# 只读预检与实际 bridge argv 使用同一个地址；非默认端口时改这里，不要只改一处。
$baseUrl = 'http://127.0.0.1:8000'
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { $python = 'python' }

# 1) 离线检查：固定身份 / 受控固定命令 / 固定执行分级 / native 模型 alias 与绑定 / 模型锁 / 工具档 / 项目绑定 / 凭据来源
#    如需同时做只读在线身份核验，加 --online-identity（需要可解析的 Key）。
& $python (Join-Path $repo 'scripts\kimi_k28_executor.py') check --key-file $keyFile --require-key --base-url $baseUrl
if ($LASTEXITCODE -ne 0) { throw "K28 执行入口离线检查未通过（exit $LASTEXITCODE）" }

# 2) 启动：密钥只由脚本从仓库外文件读取，不进入命令行、日志或仓库；
#    启动前会再做一次配置门禁与只读在线身份核验，失败即退出、不注册、不调用模型。
& $python (Join-Path $repo 'scripts\kimi_k28_executor.py') launch --key-file $keyFile --base-url $baseUrl

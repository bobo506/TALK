# TALK 常驻进程内存泄漏诊断（2026-10-31）

> 状态：**P0 已实施（2026-11-01 凌晨），待 4–6 小时生产观察；P1–P3 未开工**。
> 触发事件：2026-10-31 凌晨 TALK 服务失去响应，整机鼠标卡顿、浏览器假死，09:04 重启后恢复。

## 1. 结论摘要

1. **TALK 长时间运行确实存在稳定内存泄漏，且不是网页/API 进程**，而是 7 个常驻后台进程共用的「私有权限文件发布」路径：
   `talk_runtime serve` 1 个 + 角色宿主（role service host）6 个。
2. 实测增速：runtime 约 **8.9 MB/分钟**，每个宿主约 **3.1 MB/分钟**，合计约 **27 MB/分钟 ≈ 1.6 GB/小时**。
   2026-10-31 09:07 启动，到 13:39（4 小时 31 分）TALK 私有提交合计已约 **7.6 GB**。
3. 泄漏机制：每次写健康文件都会**重新定义 ctypes `Structure` 类、重新 `WinDLL()` 加载系统 DLL、重设函数原型**，
   并且 `ConvertStringSidToSidW` / `ConvertSidToStringSidW` 返回的 SID 没有 `LocalFree`。
   这些类型对象与原型对象不会被回收，按调用次数线性累积。
4. `talk_api`（HTTP 服务）本身平稳：09:08 启动至 13:39 维持在 113–125 MB、7–10 线程，**不是泄漏源**。
   它在事故中是受害者（分配失败 → `MemoryError` / `can't start new thread`）。
5. 这台机器只有 **8 GB 物理内存**，系统托管页面文件。按 1.6 GB/小时推算，TALK 常驻进程约 5 小时即可把整机提交内存推到临界；
   昨晚 03:00–04:11 的表现（多进程同时分配失败）与此吻合。

## 2. 现场实测

采集方式：`Get-Process -Id <pid> | Select PrivateMemorySize64`（与任务管理器「提交大小」同口径）。

| 时间 | TALK 运行时长 | `talk_runtime` | 6 个宿主（每个） | `talk_api` | TALK 合计 |
|---|---|---|---|---|---|
| 11:00 | 1h53m | 1051 MB | ~350 MB | 114 MB | ≈ 3.2 GB |
| 12:21 | 3h14m | 1769 MB | ~600 MB | 125 MB | ≈ 5.4 GB |
| 12:25 | 3h18m | 1805 MB | ~613 MB | 122 MB | ≈ 5.5 GB |
| 13:39 | 4h31m | 2464 MB | ~853 MB | 124 MB | ≈ 7.6 GB |

8 分钟连续采样（11:06:34–11:13:34）验证线性：runtime 1090 → 1147 MB（+57 MB / 8 分钟 = 7.1 MB/分钟）；
同一窗口内 `talk_api` 114 → 111 MB，无增长。

13:39 整机状态：空闲物理内存 **165 MB**，已处于临界。

15:14 后台被正常重启（runtime 3928 / api 15212，非崩溃：14:44:41 页面 WS 正常断开、无异常日志）。
重启后 17 分钟（15:31）实测：runtime **197 MB**、7 个宿主各 **71–72 MB**、api **115 MB**，合计约 **740 MB** —— 这就是「基线」。
从基线重新按原速率增长，再次印证 55 KB/次的发布成本：runtime 17 分钟约 +150 MB，与 8.9 MB/分钟一致。

## 3. 泄漏机制与代码位置

调用链（7 个进程共用）：

```
talk_runtime._serve() 每 2 秒 3 次 health()
  └─ health() 写 health.json + api-service/health.json
       └─ role_service_host._publish_private_bytes()      scripts/role_service_host.py:511
            └─ role_provision._windows_publish_temp_file() scripts/role_provision.py:1440
                 ├─ _windows_build_private_security_attributes()  :1155  （每次建 ctypes 类 + 加载 advapi32 + 6 个原型）
                 ├─ _windows_create_file_with_private_acl()       :1219  （每次加载 kernel32 + 5 个原型）
                 └─ _windows_verify_private_acl()                 :1289  （每次建 2 个类 + 加载 advapi32/kernel32 + 7 个原型）
                      └─ _windows_current_user_sid()              :1091  （每次建 2 个类 + 加载 2 个 DLL + 4 个原型）
```

宿主进程走同一条链（`role_service_host._publish_private_bytes` 写 `manager-health.json`），
因此**角色越多、泄漏越快**，符合「越跑越大」的体感。

### 3.1 Python 堆分解（tracemalloc，300 次发布）

总计 +15.5 MB（约 52 KB/次），Top 泄漏点全部指向「每次重新定义 ctypes 类/原型」：

| 行 | 增量 | 对象数 | 说明 |
|---|---|---|---|
| `role_provision.py:1118` | +4169 KB | 21007 | `_SidAndAttributes` 每次调用重新定义（约 70 个对象/次） |
| `role_provision.py:1139` | +3912 KB | 19530 | 函数原型绑定 |
| `role_provision.py:1121` | +3898 KB | 19506 | `_TokenUser` 每次调用重新定义 |
| `role_provision.py:1333` | +1673 KB | 9005 | `_AceHeader` 每次调用重新定义 |
| `role_provision.py:1368` | +1508 KB | 7811 | ACE 解析路径 |

### 3.2 A/B 实验（同进程、同文件、交替运行）

| 版本 | 每次调用增长 |
|---|---|
| 原实现 | 55.5 KB/次 |
| 仅把 `_windows_current_user_sid` 内部的 ctypes 定义提到模块级 | **11.5 KB/次**（−79%） |
| 改回原实现 | 56.5 KB/次（立刻恢复） |

说明增长与「每次调用重建类型」强相关，可以复现、可以还原，不是测量噪声或系统缓存。
剩余 11.5 KB/次来自另外两处（`:1155`、`:1289`）与未释放的 SID；全部提级并释放后预计降到 1 KB/次量级。

换算校核：runtime 每 2 秒 3 次 `health()`、每次约 2 次发布 → 约 2.5 次/秒 × 55 KB ≈ 8.3 MB/分钟，与实测 8.9 MB/分钟一致。

## 4. 昨晚事故时间线（日志与事件证据）

| 时间 | 事实 | 证据 |
|---|---|---|
| 10-30 15:38:39 | API 启动，整夜未重启 | `logs/talk.log.2026-10-30` 第 16715 行 |
| 10-31 03:00:22 | `ChatGPT.exe` 崩溃（应用错误 1000） | Windows 应用事件日志 |
| 03:04:55 | runtime 启动 `talk-provision` 线程失败 `MemoryError` | `~/.talk/role-service-host/runtime/launcher.err` |
| 03:05:03 | API 日志留存线程 `MemoryError` | `logs/talk.log:144970` |
| 04:11:10 | 同上再次 `MemoryError` | `logs/talk.log:189106` |
| 04:11:28 | 普通 `GET /role-services` 抛 `RuntimeError: can't start new thread`，API 不再服务 | `logs/talk.log:189292` |
| 07:46 / 09:03 | Chrome、Kimi Code 先后「无响应」 | Windows 应用事件日志 |
| 09:04:36 | 整机重启 | `Win32_OperatingSystem.LastBootUpTime` |

结论：03:00 前后整机「提交内存」被打满，多个进程先后分配失败；TALK 的 API 因此失去服务能力，属受害者。
按当时 runtime 已运行 11.5 小时、约 8 MB/分钟计算，仅 runtime 一个进程就约占 5 GB，另有 6 个宿主同速增长。

## 5. 环境背景

- 物理内存 **7.8 GB**（8 GB 规格），页面文件系统托管（当前 24 GB，已用约 6.4 GB）。
- 日常常驻：6 个角色宿主 + 6 个 bridge + 5 个桌面客户端（ChatGPT / Kimi Code / WorkBuddy / DSH / Chrome）+ API。
- 除泄漏外还有两个放大因素：
  1. 6 个宿主各按 **1 秒**间隔拉取整项目 `GET /projects/{id}/role-services`（`scripts/role_service_host.py:144`），
     API 单核占用实测 44–46%，单次 30–250 ms；
  2. 日志双写：`logs/talk.log` 与 `runtime/api.err` 同内容各写一份（2.5 小时 17.8 MB）。

## 6. 修复（P0 已实施；P1/P2/P3 仍为建议）

### 6.0 结论口径（按 2026-10-31 Codex 复核意见修正）

本文定位的是**一个可复现、且量级足以造成严重内存压力的 TALK 泄漏**；它是否为 03:00 那次整机提交内存耗尽的
**首发原因**，现有证据无法证明（缺少逐进程历史采样，见 §7）。修复它的依据是可复现性、影响面（7 个常驻进程）
与量级（1.6 GB/小时），而不是「已证明是唯一根因」。

### P0 修泄漏（已实施，7 个进程共用，一次覆盖）

改动文件与做法：

- `scripts/role_provision.py`：`Structure` 类在 import 时建一次；`WinDLL` 与 `argtypes/restype` 收进
  `_win()` **惰性单例**（首次使用时建一次，之后复用；保留 `ctypes.WinDLL` 可替换性，G4 中断用例不受影响）。
  `ConvertStringSidToSidW` / `ConvertSidToStringSidW` 返回的 SID/字符串一律 `LocalFree`：
  成功、中途失败（`BaseException`）、提前 `return` 三条路径都覆盖，`_WindowsPrivateSecurity.close()` 幂等。
- `scripts/role_service_host.py`：`process_creation_time` 的 DLL/原型/`_FileTime` 提到模块级（`WinDLL` 仍在
  import 时建，本模块无「导入后再替换」的测试依赖）；`_windows_create_dir_with_private_acl` 改用新的
  security 对象并在 `finally` 关闭。
- `scripts/talk_runtime.py`：`process_parents()` 的 `Entry` 类、`WinDLL`、原型提到模块级。
- 不变项：文件格式、ACL 语义、错误码、发布原子性、调用频率全部不变；共享的只有 DLL/原型/Structure 类，
  每次调用的句柄、缓冲区、指针、`SECURITY_ATTRIBUTES` 仍各自独立创建。

实施后实测（2026-11-01 00:35，本机）：

| 指标 | 修复前 | 修复后 |
|---|---|---|
| `_publish_private_bytes` 每次增长 | 55.5 KB | **0.000 KB**（预热 200 次后连续 3×1000 次） |
| `process_parents()` 每次增长 | 7.5 KB | **0.00 KB**（预热 200 次后 1500 次） |
| 相关测试 | — | 346 项全绿；关联 137 项中 2 项失败，`git stash` 还原基线后同样失败（既有环境问题） |

验收口径（按复核意见细化）：

1. **快速验收**：预热 200 次后，连续多批（3×1000 次）发布 `≤ 1 KB/次`；本次实测 0.000 KB/次。
2. **进程级指标**：逐进程采样（`talk_runtime`、每个宿主、`talk_api` 分别记），同时给出合计值；
   8 分钟只作快速筛查，**最终以一轮 4–6 小时连续运行**确认曲线趋平（而不是「增长变慢」）。
   目标是每个常驻进程 `< 0.2 MB/分钟`（修复前：runtime 8.9、每个宿主 3.1、合计约 1.6 GB/小时）。
3. **健康文件不比字节**：时间戳、PID、心跳本来就会变；改为核对字段集合与业务含义、ACL 私有性
   （`_windows_verify_private_acl` 通过）、以及「临时文件 + `os.replace`」的原子发布行为不变。
4. 相关测试套件全绿（`test_role_provision*`、`test_role_service_host*`、`test_talk_runtime`、
   `test_role_delete_local`）。

### P1 降载

- 宿主轮询 1s → 5s（或只读本角色那一行）；页面 `role-services` 2s → 5s（`web/workspace.js:1642`）。
- 验收：API 单核占用从 44–46% 降到 10% 以下，`role-services` 请求量下降约 80%。

### P2 观测与取证

- `health.json` 增加 `rss_private_mb` / `threads` 字段；
- 增加每 5 分钟记录 top-10 私有提交的小脚本，下次整机异常时可直接定位首发进程。

### P3 环境

- 8 GB 机器上限制同时在线角色数（当前 6 个宿主 + 5 个桌面客户端），或增加物理内存。

### 6.5 为什么「定时清空缓存」不成立（2026-10-31 实测）

结论：**没有可清的缓存；清理动作对这一类增长无效**。三种常见做法逐一实测：

| 手段 | 实测结果 | 结论 |
|---|---|---|
| `gc.collect()` | 300 次发布后提交 35.0 MB / 工作集 42.4 MB；collect 后仍是 **35.0 / 42.4** | 无变化。增长的不是「不可达垃圾」，而是 ctypes 反复创建、仍被引用的类型/原型对象；另有原生 SID 分配 Python GC 看不见 |
| `EmptyWorkingSet`（清工作集） | 工作集 42.4 → **0.8 MB**，提交量仍 **35.0 MB** | 只是把页换到页面文件，整机提交压力不变，再访问全部缺页、更慢 |
| 重启进程 | 15:14 重启后从 7.6 GB 回到约 **740 MB** 基线 | 唯一真正清零的手段，但会断开 7 个宿主与 bridge，可能打断任务/会话 |

按 1.6–1.8 GB/小时与这台机器的余量折算，「定时重启」大约每 4–5 小时一次才安全
（09:07 启动 → 14:45 已 7.6 GB），属于**兜底手段**而非修复：可以接受「每天凌晨一次 + 超阈值触发」，不能替代 P0。
TALK 代码里也没有随请求增长的业务缓存可清——`talk_api` 全程 113–125 MB 平稳即为反证。

**「角色任务完成后释放内存」同样无效**：泄漏发生在 `health()` 心跳写入里（runtime 1–3 次/秒、宿主约 0.8 次/秒），与任务执行无关。
15:14 重启后 23 分钟内没有任何任务执行，实测 runtime 197 → 250 MB（+8.8 MB/分钟）、7 个宿主 72 → 89 MB（+2.8 MB/分钟·个），
`talk_api` 114 MB 不变——空闲也照涨。且 `talk_runtime` 本身不接任务，却是漏得最快的进程。
进程内也没有可调用的「释放」接口：相关对象仍被引用，`gc` 不回收（实测 0 变化），Windows 无 `malloc_trim`，
Python 3.12 在 Windows 上不会把空闲 arena 归还系统。唯一能清零的仍是重启进程。
若确需生命周期回收，正确形态是「时间/阈值 + 任务空闲守卫」（例如每 4 小时或总提交超 5 GB、且无 in-flight 任务时滚动重启），属兜底而非修复。

## 7. 未验证与已知边界

- **无法证明昨晚 03:00 的第一触发者**：没有逐进程历史采样，只能证明「整机提交被耗尽」以及 TALK 进程的线性增长可复现。
- `talk_api` 长周期行为只观察到 4.5 小时平稳，未做 12 小时以上验证。
- 页面/浏览器侧内存未测量；本次未做前端性能采样。
- 修复后的实际斜率需按 P0 验收标准复测，本文档不预先宣称「归零」。
- 本文档所有数据来自 2026-10-31 本机实测，不代表其它机器或其它版本的结论。

## 8. 复现方法

```powershell
# 1) 现场斜率（挑 8 分钟，每 60 秒一次）
1..8 | ForEach-Object {
  $t=Get-Date -Format HH:mm:ss
  $a=(Get-Process -Id <runtime_pid>).PrivateMemorySize64/1MB
  $b=(Get-Process -Id <api_pid>).PrivateMemorySize64/1MB
  "$t runtime={0:N0}MB api={1:N0}MB" -f $a,$b
  Start-Sleep -Seconds 60
}
```

```python
# 2) 单次发布成本（真实导入产品代码，交替 A/B）
from scripts import role_service_host as rsh
for _ in range(300):
    rsh._publish_private_bytes(path, b"x"*200)   # 前后取 PrivateMemorySize64 差值 / 300
```

```python
# 3) 泄漏点分解
import tracemalloc
tracemalloc.start(8); s1 = tracemalloc.take_snapshot()
for _ in range(300): rsh._publish_private_bytes(path, b"x"*200)
s2 = tracemalloc.take_snapshot()
for stat in s2.compare_to(s1, "lineno")[:10]: print(stat)
```

# G-terra 启动预检修复与实机验收

日期：2026-10-29（Asia/Shanghai）。用户授权 Codex 本人处理，不派发任务；另明确授权 G-terra 宿主定向正常排空、重新加载及启停验收。Git/GitHub 操作仍交 DeepSeek，本轮不执行、不另派任务。

## 问题与修正

真实页面确认官方授权和模型准备完成，绑定为 `gpt-6.1-terra / low`，启动失败为 `cli_incompatible`。`CodexRoleHost.build_entry_argv` 生成 `python -B -X utf8 -m bridges.codex_bridge`，而公共 `verify_runtime_entry` 及 `parse_unit_count` 固定按 `python -m <module>` 识别。错误发生在真实入口 parser 之前，与已完成的官方授权无关。

仅将 Codex bridge 启动前缀改为公共入口合同；不放宽公共验证器、不改模型、角色权限、CLI 路径、原生凭据或超时。宿主自身启动前缀不变。回归同时检查 review/tools、默认86400秒/显式123秒、真实 parser 及诊断解析。

## 证据与验证

- 隔离根 `.tmp/g-terra-start-fix-20261029/`，256份源码快照及 SHA256 清单；保留原宿主源码、原失败日志。仅集成 `scripts/codex_role_host.py` 与 `tests/test_codex_new_role_host.py`，集成前核对两份生产源无漂移。
- 新反例在修正前 review/tools 两个场景均复现 `cli_incompatible`；修正后通过。
- 关联标准 unittest：`tests.test_codex_new_role_host tests.test_codex_role_setup tests.test_talk_runtime`，46项通过。首次运行9项失败均为 Windows `ADMINI~1` 与长路径断言差异，保留 `related-after.txt`；设置本片独立 TEMP/TMP 后原断言不变，46项全过，见 `related-longpath-after.txt`。
- 实际 G-terra 宿主16440经正常 drain退出、健康状态stopped后移除本次自建请求；既有runtime自动重建宿主1784。runtime13920与其他宿主4748/8340/16388/16424/16464/16476保持，不重启API、不强杀、不清锁、不解除所有权。
- 浏览器实际点击启动后页面显示成功，实例 `ins_c5c3d8333359` / PID18308为idle；正常关闭后页面为已关闭、实例offline、PID18308退出；随后再次启动成功，实例`ins_e28faeceedf8`/PID11340为idle，保持运行。截图位于`.tmp/g-terra-start-fix-20261029/evidence/terra-running.png`。

## 验收范围与限制

入口为 TALK → 角色 → G-terra；账号使用原TALK网页登录，官方设备授权已完成，无需重新获取或复制Key。启动应显示成功，关闭应显示已关闭，之后允许重新启动。

本次不派发任务，因此没有运行真实模型任务、未验证任务执行/续窗/忙时停止、未运行全仓库测试，也没有他人独立复核。不得将服务启动成功写成完整模型任务验收通过。用户手册的原启停流程保持有效，无需改变用户操作步骤。

348的两个DSH凭据拒绝边界不在本片；先前补Codex运行配置与本片修复均不能作为348通过依据。

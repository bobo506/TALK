# 角色配置基础：使用与验收（R1-2）

> 2026-10-11：配置作业/脚本及固定分级迁移已独立复核通过；页面一键配置、启停/删除尚在 R1-3/R1-4。
> 协议见 [配置合同](../spec/ROLE_PROVISION_CONTRACT.md)。

## 启动与入口

项目根使用现有环境启动：

```powershell
.venv/Scripts/python.exe -m uvicorn server.main:app --host 127.0.0.1 --port 8000
```

已有服务按自己的方式加载新代码，本轮未操作生产重载/迁移。页面 `http://127.0.0.1:8000`，API 文档 `http://127.0.0.1:8000/docs`。刷新角色页，主显示不再有“决策/执行”；发起者主动/被动设置保留。

## 无真实凭据的隔离验收

仓库运行重点回归，测试自行创建临时数据库、假 Key 与受控文件/进程：

```powershell
.venv/Scripts/python.exe -X utf8 -m unittest tests.test_role_provision tests.test_role_provision_followup tests.test_role_provision_rework tests.test_role_provision_lock_recovery
```

#222 本机独立为143项通过，零失败/错误/跳过。涵盖重复配置、旧凭据/迟到ACK、未知409拒绝、档案/绑定、锁崩溃恢复、真实junction零外部副作用；无需测试账号或生产 Key。

离线计划（替换标识与仓库外目录）：

```powershell
.venv/Scripts/python.exe -X utf8 scripts/role_provision.py --project "<项目ID>" --member "<角色member_id>" --operation-key "<原创建operation_key>" --project-root "D:/claude-test/TALK" --key-root "D:/TALK-private/keys" --json
```

默认不联网、不写文件，不证明已配置；没有 `--dry-run` 参数。

## 操作者配置检查

1. 使用 R1-1 角色创建 API 选择已适配的 runner/model，保存实际 `member_id/operation_key`；只有首次创建或人工轮换一次返回角色 Key，作业查询不返回。
2. 使用自己的 **human** Key 调配置 API，agent 无权。角色 Key 保存在仓库外输入文件；operator 通过 `TALK_OPERATOR_KEY_FILE` 或 `TALK_OPERATOR_API_KEY` 提供。沿用现有人类账号管理，无内置验收账号。
3. 核对计划后在原三元组命令追加 `--apply --key-input-file "<仓库外角色Key输入文件>"`。检查本人三档/私有Key/精确绑定预检与完整作业三步 ACK；脚本不代登录订阅账号、不启动运行器。
4. 重跑相同三元组确认身份不重复、人工档案保留；失败纠正后用 `--apply --resume --steps "<失败步骤>"` 恢复。轮换后必须续跑重新核验，旧文件由人工确认，脚本不覆盖。
5. 同runner/model的多个角色分别使用各自创建操作、member_id、档案和Key，确认互不覆盖。

`applied/succeeded` 只表示配置步骤成功。原生登录、真实模型/额度/隔离、服务启停/退出在后续验收。文件symlink因本机权限未运行，junction及静态拒绝已测；不承诺防御恶意并发路径替换。

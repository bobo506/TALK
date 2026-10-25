# 项目自启动：333新增MF-1R边界修正（2026-10-25）

333已正常正式交付2979（task succeeded/submitted，业务conclusion=partial，独立review verdict=failed），UTC06:19:59.605967核验后收取completed。原332仍failed/2978不收取、不改写。333实际new_no_candidate新窗/count1，末次326345/1000000=32.6345%，不是复用旧tainted窗。正式消息与本地delivery逐字段相同，29份210648字节原始报告/探针/日志在fix2/coordination/333-original-review按manifest逐项归档，原材料不改。

## 为什么还需这次必要补正

原MF-2/MF-3及原四条失败断言已独立通过，MF-1可信旧API、新APIpending、声明支持但404/403/409和未知schema的主路径也通过。333新反例发现：startup路径key虽然存在，但value是Reference、断链Reference、null或get-only时，仍被误判unsupported，从而零POST并提前开放宿主。实际FastAPI文档是内联POST，没有证据表明生产触发过这个反例；它仍违反“路径确缺才放行、未知结构保持门控”的本片合同，因此需要在加载前修正。无需重做整片或把非阻断项另开任务。

## 最小实施与验收

- 只改scripts/talk_runtime.py能力探测：可信原roles GET存在且startup路径key确实不在paths中，才unsupported。路径存在但不含可识别的本地POST时保持未知，沿原限次POST/退避与宿主门控，不解析或跟随Reference。
- tests/test_project_startup_compatibility.py补四个正式回归，要求Reference-with-POST、断链Reference、null、get-only均不标unsupported，执行8轮POST并保持原门控；旧API确缺路径及时放行和新APIpending直到complete的正向对照保留。
- Codex只重跑受影响兼容/runtime组及333原MF-1探针，不重跑MF-2/MF-3/整片历史数字。333原4失败断言不改；原223/228/58Node与沙箱限制保留，不把自检称独立通过。
- 新发现的必须修正项允许一次极小范围独立复验，唯一写fix2/review；只核MF-1R反例及旧API/newAPIpending对照，不再全面首审。Codex修正和自检完成、Git推送与新冻结后交DeepSeek，随后暂停产品与正式测试，默认用户通知完成再取件。

## 保持的事实与权限

本次不生产启停/加载/配置/自动勾选，不读生产配置/清单/Key/DB/private state/HOME/native session/log；前次元数据只读和定向恢复的许可已经用完，不沿用或授给复核者。原63/116冻结和332/333原材料不改。新代码未加载；当前API仍旧、runtime11280仍初版，不能把代码提交当成实际可用。

任务250原failed/2767、286 queued/accepted/paused及五角色绑定保持。修正后仍先完成独立复验，再给出具体正常加载方案并确认；不自动开启下一无关片，不声称真实断电/模型/浏览器验收通过。

## 本轮自检结果

原run_isolated.py在合成根下执行：16项正式runtime/兼容测试（含4项新增）及10项333原MF-1独立探针直接加载新源，全过，无失败/错误/跳过，共26个不同用例。原探针断言未改，四类原失败反例现通过。日志fix2/isolated/formal-runtime-compat.log和original333-mf1-probes.log、checks-result.json保留；未追加plain-publish替代。产品只1份、正式测试只1份，不扩大到其它模块。

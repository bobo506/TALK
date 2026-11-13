# Project Progress

## 当前快照（2026-11-13 16:30，15a 工作区切换验收完成）

- **15a 完成（用户人工验收）**：临时项目 B `prj_97c2a3ffe849` 创建→切 B/刷新/切回 A→删除 204/404；A 的 Terra `ins_b8a390d9a761`/`13592`、K2.8 `ins_2eb973afae92`/`15664` 全程 running/ready，instance/pid 未变；DOM 测试 4/4；真实浏览器仅有用户口头“通过”，无截图。
- **复核**：K2.8 731 结论 partial；API/证据链 12 项 pass，唯浏览器四步仅用户声明，不记为独立验证；730/731 已收取，`submitted=[]`。
- **范围**：13 关闭（仅 CLI）；14 免安装文件夹分发；17 ACP 与会议关闭；宿主生命周期改为“周期内用过的角色保留宿主，runtime 重启后只拉起勾选随项目自动启动的角色”（设计待做）。
- **已知残余**：15b 退出/重开未做；K2.8 3 条历史 idle 实例（`ins_3deacebf9459`/11208、`ins_f3b7ddd2419e`/15648、`ins_87aad513bfac`/772，pid 已不存在）未清理；P2 长任务 kill 未做；浏览器无自动化工具。
- **运行态**：runtime `6664`，7 宿主 `serving`；Terra gen82、K2.8 gen80 running/ready/idle。
- **提交**：此前 `59f5406`/`b650567`/`1e2cd0b`/`055c24d`/`c660c33`/`bb5724f`/`5277d9c`/`0b45f60`/`25925bc`；本次 15a 记录另提交。
- **恢复**：说“继续项目”；详情见 [PROGRESS_HISTORY.md](PROGRESS_HISTORY.md) 顶部。

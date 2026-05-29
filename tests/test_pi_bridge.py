import unittest
import shlex

from bridges import pi_bridge


class PiBridgeTests(unittest.TestCase):
    def test_parser_defaults_to_pi_identity_and_argv_transport(self):
        args = pi_bridge.build_parser().parse_args(["--key", "pi-key"])

        self.assertEqual(args.name, "pi")
        self.assertEqual(args.runtime, "pi")
        self.assertEqual(args.bridge_label, "pi bridge")
        self.assertEqual(args.prompt_transport, "argv")
        command_args = shlex.split(args.pi_command, posix=True)
        self.assertEqual(command_args[:4], ["pi", "--print", "--mode", "text"])
        self.assertIn("--no-context-files", command_args)
        self.assertIn("--no-tools", command_args)
        self.assertIn("--no-session", command_args)
        self.assertIn("--thinking", command_args)
        self.assertIn("off", command_args)
        self.assertIn("--system-prompt", command_args)
        system_prompt = command_args[command_args.index("--system-prompt") + 1]
        self.assertIn("TALK Group Hall", system_prompt)
        self.assertIn("群聊参与者", system_prompt)
        self.assertIn("按用户语言自然回复", system_prompt)
        self.assertIn("默认讨论模式", system_prompt)
        self.assertIn("安全行协议", system_prompt)
        self.assertIn("TALK_ACTION", system_prompt)
        self.assertIn("final_to_human", system_prompt)
        self.assertNotIn("talk-action", system_prompt)
        # 5.3 P0 修复：禁止 system prompt 里出现任何具体人名硬编码
        # （之前 to=human:bobo 导致 pi 把"bobo"幻觉成群里的人类）
        self.assertNotIn("human:bobo", system_prompt)
        self.assertNotIn("human:qa", system_prompt)
        self.assertNotIn("agent:codex", system_prompt)
        # 5.3 P0 修复：禁止 system prompt 自封业务角色
        # （之前"评审方案"让 pi 把自己定位成"方案评审者"主动招揽工作）
        self.assertNotIn("评审方案", system_prompt)
        # 5.3 P0 修复：必须强调"只能提及清单内成员"与"回复克制"
        self.assertIn("成员清单", system_prompt)
        self.assertIn("不得", system_prompt)  # "不得称呼或 @ 清单外的任何名字"
        self.assertIn("回复克制", system_prompt)
        # 5.3 热修第二弹：用场景类型描述替代 A/B/C 关键词匹配。
        # 上一轮采用 A/B/C 标签 + 关键词清单的方式，结果 pi 把"A 类。"当话术输出（#431 铁证），
        # 而且关键词"去和"不在清单里导致"你去和 codex 打个招呼"被误判为 A 类不执行 TALK_ACTION。
        # 本轮改成场景描述 + "意图焦点"语义判断 + "拿不准优先按信使处理"兜底。
        self.assertIn("信使场景", system_prompt)
        self.assertIn("意图焦点", system_prompt)
        self.assertIn("必须用 TALK_ACTION send_message", system_prompt)
        # 防止误简化：必须出现"先承接用户再 TALK_ACTION"的顺序约束
        self.assertIn("先简短承接用户一句", system_prompt)
        # 兜底：拿不准优先按信使处理，避免不执行任务
        self.assertIn("拿不准时优先按信使处理", system_prompt)
        # 场景 9 自我介绍修复：被问"介绍下你自己"时必须说出 member_id 和角色状态
        self.assertIn("自身询问场景", system_prompt)
        self.assertIn("member_id", system_prompt)
        self.assertIn("本群没有给我分配特定业务角色", system_prompt)
        # 防 #431 那种"A 类。"开头泄漏：必须显式禁止输出场景标签
        self.assertIn("不要在回复里写出", system_prompt)
        # 旧的 A/B/C 字母标签必须从行为指令中去掉
        # 注意：上面"不要在回复里写出"那条本身可能提到 'A 类' 作为反例，
        # 所以只检查 A 类是否作为指令性章节标题出现（用 "A 类——" 这种破折号结构判定）
        self.assertNotIn("A 类——", system_prompt)
        self.assertNotIn("B 类——", system_prompt)
        self.assertNotIn("C 类——", system_prompt)
        for metachar in ("|", "/", "<", ">", "&"):
            self.assertNotIn(metachar, system_prompt)

    def test_parser_can_enable_pi_tools_profile_with_default_command(self):
        args = pi_bridge.build_parser().parse_args(["--key", "pi-key", "--pi-execution-profile", "tools"])

        self.assertEqual(args.pi_execution_profile, "tools")
        self.assertEqual(args.pi_command, pi_bridge.DEFAULT_PI_COMMAND)
        args.pi_command = pi_bridge.DEFAULT_PI_TOOLS_COMMAND
        command_args = shlex.split(args.pi_command, posix=True)
        self.assertIn("--tools", command_args)
        self.assertIn("read,grep,find,ls,bash,edit,write", command_args)
        self.assertNotIn("--no-tools", command_args)

    def test_parser_accepts_custom_pi_command(self):
        args = pi_bridge.build_parser().parse_args([
            "--key",
            "pi-key",
            "--pi-command",
            "pi --provider deepseek --print --mode text",
        ])

        self.assertEqual(args.pi_command, "pi --provider deepseek --print --mode text")


if __name__ == "__main__":
    unittest.main()

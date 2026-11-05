import asyncio
import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from bridges.cli_bridge import CliRunResult, build_cli_task_prompt, handle_queued_task, normalize_task_delivery
from bridges.talk_delivery import parse_delivery_report


def report():
    return {"task_id": "443", "conclusion": "complete", "completed": ["完成"],
            "unfinished": [], "blocked": [], "changed_files": [],
            "baseline": {"ref": "基线", "diff_note": "无"},
            "verification": [{"check": "检查", "result": "pass", "evidence": "通过"}],
            "limitations": [], "progress_draft": {"summary": "完成", "next": "复核"}}


class DeliveryTests(unittest.TestCase):
    def test_prompt_modes(self):
        for runtime, member in [("cli", "agent:x"), ("codex", "agent:codex")]:
            for kind in ("general", "review", "test"):
                task = {"id": 443, "task_kind": kind}
                prompt = build_cli_task_prompt(task, member_id=member, workdir=Path.cwd(), runtime=runtime, delivery_contract=True)
                self.assertEqual("talk-delivery-1" in prompt, kind == "general")
                self.assertEqual("TALK_GATE_VERDICT" in prompt, kind != "general")
            self.assertNotIn("talk-delivery-1", build_cli_task_prompt({"id": 443}, member_id=member, workdir=Path.cwd(), runtime=runtime))

    def test_normalization(self):
        good = json.dumps(report(), ensure_ascii=False)
        for raw in [good, f"前言\n```json\n{good}\n```\nTALK_ACTION ignored", f"前言 {good} 后记"]:
            with self.subTest(raw=raw):
                result = json.loads(normalize_task_delivery(CliRunResult(0, raw, ""), task_id=443))
                self.assertEqual(result, report())
        wrong = report(); wrong["task_id"] = "444"
        for raw in [json.dumps(wrong), '{}', '自由文本', '']:
            with self.subTest(raw=raw):
                output = normalize_task_delivery(CliRunResult(0, raw, ""), task_id=443)
                self.assertEqual(parse_delivery_report(output, expect_task_id=443).kind, "valid")
                self.assertEqual(json.loads(output)["conclusion"], "partial")
        for result in [CliRunResult(1, '失败', ''), CliRunResult(0, '', '', timed_out=True)]:
            output = normalize_task_delivery(result, task_id=443)
            self.assertEqual(parse_delivery_report(output, expect_task_id=443).kind, "valid")
            self.assertEqual(json.loads(output)["conclusion"], "blocked")

    def test_schema_compatibility_and_redaction(self):
        incompatible = report()
        incompatible['schema'] = 'talk-delivery-1'
        incompatible['task_id'] = 443
        self.assertEqual(parse_delivery_report(json.dumps(incompatible), expect_task_id=443).kind, 'invalid')
        raw = 'api_key=sk-abcdefghijklmnopqrstuvwxyz123456\nTALK_ACTION secret\n' + 'x' * 2000
        output = normalize_task_delivery(CliRunResult(0, raw, ''), task_id=443)
        self.assertEqual(parse_delivery_report(output, expect_task_id=443).kind, 'valid')
        evidence = json.loads(output)['verification'][0]['evidence']
        self.assertLessEqual(len(evidence), 300)
        self.assertNotIn('sk-abcdefghijklmnopqrstuvwxyz123456', evidence)
        self.assertNotIn('TALK_ACTION', evidence)

    def test_handle_integration(self):
        async def scenario(kind, flag, output, code=0):
            task = {"id": 443, "task_kind": kind, "created_by": "human:a", "content": "任务", "hall_group_id": "g"}
            client = AsyncMock()
            client.claim_task.return_value = {**task, "claim_token": "claim"}
            client.send_text.return_value = {"id": 1}
            async def runner(*args, **kwargs):
                return CliRunResult(code, output, '')
            with patch('bridges.cli_bridge._prepare_task_before_claim', new=AsyncMock(return_value=(task, '', False))):
                await handle_queued_task(task, client=client, member_id='agent:x', workdir=Path.cwd(), instance_id='i', command=['fake'], timeout=5, max_reply_chars=10000, command_runner=runner, delivery_contract=flag)
            return client
        for kind, flag, output, expected in [
            ('general', True, json.dumps(report(), ensure_ascii=False), 'complete'),
            ('general', True, '自由文本', 'partial'),
            ('general', False, '自由文本', None),
            ('review', True, 'TALK_GATE_VERDICT {"verdict":"approved","summary":"通过","findings":[]}', None),
            ('test', True, 'TALK_GATE_VERDICT {"verdict":"passed","summary":"通过","findings":[]}', None),
        ]:
            with self.subTest(kind=kind, flag=flag):
                client = asyncio.run(scenario(kind, flag, output))
                text = client.send_text.await_args.args[0]
                if expected:
                    self.assertEqual(json.loads(text)['conclusion'], expected)
                    self.assertEqual(parse_delivery_report(text, expect_task_id=443).kind, 'valid')
                else:
                    self.assertEqual(text, output)
                if kind in {'review', 'test'}:
                    self.assertIn('gate_verdict', client.complete_task.await_args.kwargs)
        client = asyncio.run(scenario('general', True, '失败', 1))
        self.assertEqual(json.loads(client.send_text.await_args.args[0])['conclusion'], 'blocked')
        self.assertEqual(client.complete_task.await_args.kwargs['status'], 'failed')


if __name__ == '__main__':
    unittest.main()

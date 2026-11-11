"""One-turn WorkBuddy desktop CDP stdin/stdout adapter."""
import argparse
import json
import sys
from bridges.workbuddy_cdp import CdpError, prompt_once
from scripts.workbuddy_acp_prompt import has_valid_delivery


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True)
    parser.add_argument('--mode', choices=('chat', 'plan', 'task'), required=True)
    parser.add_argument('--project-root', required=True)
    parser.add_argument('--effort')
    parser.add_argument('--timeout', type=float, default=600)
    parser.add_argument('--endpoint')
    parser.add_argument('--delivery-contract', action='store_true')
    parser.add_argument('--expect-task-id', type=int)
    args = parser.parse_args(argv)
    try:
        text = sys.stdin.buffer.read().decode('utf-8')
        model = args.model.removeprefix('workbuddy-cdp:')
        options = {}
        if args.delivery_contract and args.expect_task_id is not None:
            task_id = args.expect_task_id
            options['repair_validator'] = lambda output: has_valid_delivery(output, task_id)
            options['repair_prompt'] = (
                '不要再执行工具或改文件；只重发完整、紧凑的 JSON 本体，无解释、无 ``` 围栏、无 TALK_ACTION。'
                '所有字符串单行且不超过200字符；completed、unfinished、blocked、changed_files、limitations 各不超过10项，'
                'verification 不超过5项；总长不超过4000字符；task_id 为字符串 "' + str(task_id) + '"。'
            )
        result = prompt_once(model, text, mode=args.mode, project_root=args.project_root,
                             effort=args.effort, timeout=args.timeout, endpoint=args.endpoint, **options)
        sys.stdout.buffer.write((result['text'].rstrip('\n') + '\n').encode('utf-8'))
        diagnostic = {'model': model, 'effort': args.effort, 'elapsed': round(result['elapsed'], 2)}
        sys.stderr.buffer.write(('[workbuddy-cdp] ' + json.dumps(diagnostic, ensure_ascii=False) + '\n').encode('utf-8'))
        return 0
    except CdpError as exc:
        sys.stderr.buffer.write(('[workbuddy-cdp] ' + json.dumps({'error': exc.code}) + '\n').encode('utf-8'))
        return 3 if exc.code in {'workbuddy_cdp_config_failed', 'workbuddy_cdp_prompt_failed'} else 2
    except (OSError, ValueError, UnicodeError):
        sys.stderr.buffer.write(b'[workbuddy-cdp] {"error":"workbuddy_cdp_invalid_input"}\n')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

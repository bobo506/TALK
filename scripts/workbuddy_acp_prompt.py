"""One-turn WorkBuddy ACP stdin/stdout adapter."""
import argparse
import json
import re
import sys
from bridges.talk_delivery import parse_delivery_report
from bridges.workbuddy_acp import AcpError, is_acp_alias, parse_acp_alias, prompt_once

def has_valid_delivery(output, task_id):
    """Match cli_bridge's full-text and embedded delivery candidate rules."""
    candidates = [(0, output.strip())]
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", output):
        try:
            obj, end = decoder.raw_decode(output, match.start())
        except (ValueError, RecursionError):
            continue
        if isinstance(obj, dict):
            candidate = output[match.start():end]
            if 'talk-delivery-1' in candidate or '"conclusion"' in candidate:
                candidates.append((match.start(), candidate))
    return any(
        parse_delivery_report(candidate, expect_task_id=task_id).kind == 'valid'
        for _, candidate in sorted(candidates, key=lambda item: item[0], reverse=True)
    )


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True)
    parser.add_argument('--mode', choices=('chat','plan','task'), required=True)
    parser.add_argument('--project-root', required=True)
    parser.add_argument('--effort')
    parser.add_argument('--timeout', type=float, default=600)
    parser.add_argument('--endpoint')
    parser.add_argument('--delivery-contract', action='store_true')
    parser.add_argument('--expect-task-id', type=int)
    args = parser.parse_args(argv)
    try:
        text = sys.stdin.buffer.read().decode("utf-8")
        model = parse_acp_alias(args.model) if is_acp_alias(args.model) else args.model
        options = {}
        if args.delivery_contract and args.expect_task_id is not None:
            task_id = args.expect_task_id
            options['repair_validator'] = lambda output: has_valid_delivery(output, task_id)
            options['repair_prompt'] = (
                '不要再执行工具或改文件；只重发完整、紧凑的 JSON 本体，无解释、无 ``` 围栏、无 TALK_ACTION。'
                '所有字符串单行且不超过200字符；completed、unfinished、blocked、changed_files、limitations 各不超过10项，'
                'verification 不超过5项；总长不超过4000字符；task_id 为字符串 "' + str(task_id) + '"。'
            )
        result = prompt_once(model, text, mode=args.mode, project_root=args.project_root, effort=args.effort, timeout=args.timeout, endpoint=args.endpoint, **options)
        sys.stdout.buffer.write((result['text'].rstrip('\n') + '\n').encode('utf-8'))
        sys.stderr.buffer.write(('[workbuddy-acp] ' + json.dumps({'model':model,'elapsed':round(result['elapsed'],2),'usage':result['usage']}, ensure_ascii=False) + '\n').encode('utf-8'))
        return 0
    except AcpError as exc:
        sys.stderr.buffer.write(('[workbuddy-acp] ' + exc.code + '\n').encode('utf-8'))
        return 3 if exc.code in {'workbuddy_acp_prompt_failed','workbuddy_acp_model_not_applied','workbuddy_acp_mode_not_applied','workbuddy_acp_thought_level_not_applied'} else 2
    except (OSError, ValueError, UnicodeError):
        sys.stderr.buffer.write(b'[workbuddy-acp] workbuddy_acp_invalid_input\n')
        return 2

if __name__ == '__main__':
    raise SystemExit(main())

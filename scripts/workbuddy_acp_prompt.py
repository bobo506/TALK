"""One-turn WorkBuddy ACP stdin/stdout adapter."""
import argparse
import json
import sys
from bridges.workbuddy_acp import AcpError, is_acp_alias, parse_acp_alias, prompt_once

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True)
    parser.add_argument('--mode', choices=('chat','plan','task'), required=True)
    parser.add_argument('--project-root', required=True)
    parser.add_argument('--effort')
    parser.add_argument('--timeout', type=float, default=600)
    parser.add_argument('--endpoint')
    args = parser.parse_args(argv)
    try:
        text = sys.stdin.buffer.read().decode("utf-8")
        model = parse_acp_alias(args.model) if is_acp_alias(args.model) else args.model
        result = prompt_once(model, text, mode=args.mode, project_root=args.project_root, effort=args.effort, timeout=args.timeout, endpoint=args.endpoint)
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

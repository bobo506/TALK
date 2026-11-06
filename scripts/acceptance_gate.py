"""Mechanical acceptance evidence checks; does not execute project tests."""
import argparse
import ast
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

from scripts.talk_workflow import validate_report


GENERATED_UNTRACKED_PATTERNS = (
    "Microsoft/", ".tmp-tests/", ".tmp/", "__pycache__/",
    "*.pyc", "*.log", "*.db-wal", "*.db-shm", ".pytest_cache/",
)


def is_generated_untracked(name):
    parts = name.replace("\\", "/").split("/")
    return any(
        pattern[:-1] in parts[:-1] if pattern.endswith("/")
        else fnmatch.fnmatchcase(parts[-1], pattern)
        for pattern in GENERATED_UNTRACKED_PATTERNS
    )


class ConfigurationError(Exception):
    pass


def load_json(path):
    try:
        with open(path, encoding="utf-8") as stream:
            data = json.load(stream)
    except (OSError, UnicodeError, ValueError) as exc:
        raise ConfigurationError(f"无法读取 JSON {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigurationError(f"{path}: 顶层必须是对象")
    return data


def git(root, *args):
    proc = subprocess.run(["git", "-C", str(root), *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode:
        raise ConfigurationError(f"git {args[0]} ({root}): {proc.stderr.decode('utf-8', 'replace').strip()}")
    return proc.stdout


def require(obj, key, typ, label):
    value = obj.get(key)
    if not isinstance(value, typ) or (typ is int and isinstance(value, bool)):
        raise ConfigurationError(f"{label}.{key} 缺失或类型错误，应为 {typ.__name__}")
    return value


def path_list(obj, key, label):
    values = require(obj, key, list, label)
    if any(not isinstance(v, str) or not v.strip() for v in values) or len(values) != len(set(values)):
        raise ConfigurationError(f"{label}.{key} 必须是无重复的非空字符串数组")
    return values


def task(value):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ConfigurationError("task_id 必须是整数或字符串")
    value = str(value).strip().removeprefix('#')
    if not value.isdigit():
        raise ConfigurationError("task_id 必须是数字")
    return str(int(value))


def relative(root, name):
    p = Path(name)
    if p.is_absolute() or '..' in p.parts or not p.parts:
        raise ConfigurationError(f"候选相对路径非法: {name}")
    target = (root / p).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ConfigurationError(f"候选路径越界: {name}")
    return target


def referenced_statements(source, symbol):
    tree = ast.parse(source)
    # Compare the smallest statements mentioning the symbol, including nested mutation calls.
    return sorted(ast.dump(node, include_attributes=False) for node in ast.walk(tree)
                  if isinstance(node, ast.stmt)
                  and any(isinstance(n, ast.Name) and n.id == symbol for n in ast.walk(node)))


def check(manifest_path):
    m = load_json(manifest_path)
    if m.get('schema') != 'talk-acceptance-gate-1':
        raise ConfigurationError('manifest.schema 必须为 talk-acceptance-gate-1')
    profile = require(m, 'profile', str, 'manifest')
    if profile not in ('code', 'doc'):
        raise ConfigurationError(f'manifest.profile 非法: {profile}')
    tid = task(m.get('task_id'))
    root = Path(require(m, 'project_root', str, 'manifest'))
    candidate = Path(require(m, 'candidate', str, 'manifest'))
    baseline_ref = require(m, 'baseline_ref', str, 'manifest')
    blob = require(m, 'tracked_diff_blob', str, 'manifest')
    if not baseline_ref or not re.fullmatch(r'[0-9a-fA-F]{40}|[0-9a-fA-F]{64}', blob):
        raise ConfigurationError('manifest.baseline_ref 或 tracked_diff_blob 无效')
    untracked = path_list(m, 'untracked_files', 'manifest')
    allowed = path_list(m, 'allowed_untracked', 'manifest')
    docs = path_list(m, 'changed_docs', 'manifest')
    mutations = path_list(m, 'authorized_mutations', 'manifest')
    logs = path_list(m, 'logs', 'manifest')
    for name in untracked + allowed + docs:
        relative(candidate, name)
    d = load_json(require(m, 'delivery', str, 'manifest'))
    r = load_json(require(m, 'review', str, 'manifest'))
    if d.get('schema', 'talk-delivery-1') != 'talk-delivery-1' or r.get('schema') != 'talk-review-gate-1':
        raise ConfigurationError('delivery.schema 或 review.schema 不匹配')
    if task(d.get('task_id')) != tid or task(r.get('task_id')) != tid:
        raise ConfigurationError('manifest、delivery、review 的 task_id 不一致')
    verification = require(d, 'verification', list, 'delivery')
    unfinished = require(d, 'unfinished', list, 'delivery')
    blocked = require(d, 'blocked', list, 'delivery')
    rc = require(r, 'candidate', dict, 'review')
    rb = require(r, 'baseline', dict, 'review')
    names = path_list(r, 'baseline_failure_names', 'review')
    for side, obj in [('candidate', rc), ('baseline', rb)]:
        require(obj, 'log', str, 'review.' + side)
        for field in ('failures', 'errors') if profile == 'doc' else ('tests', 'failures', 'errors', 'skipped'):
            n = require(obj, field, int, 'review.' + side)
            if n < 0:
                raise ConfigurationError(f'review.{side}.{field} 不能为负数')
    require(rb, 'ref', str, 'review.baseline')
    new_failures = require(r, 'new_failures', int, 'review')
    if new_failures < 0:
        raise ConfigurationError('review.new_failures 不能为负数')
    results = []
    def record(name, ok, detail):
        results.append({'check': name, 'result': 'pass' if ok else 'fail', 'detail': detail})
    delivery_fields = {k: v for k, v in d.items() if k != 'schema'}
    validation = validate_report(delivery_fields, expect_task_id=tid)
    record('delivery.schema', validation.ok, '; '.join(f'{x.field}: {x.message}' for x in validation.errors) or 'talk-delivery-1')
    record('delivery.conclusion', d.get('conclusion') == 'complete', f"conclusion={d.get('conclusion')!r}")
    record('delivery.verification', bool(verification) and all(isinstance(v, dict) and v.get('result') == 'pass' for v in verification), f'verification={verification!r}')
    record('delivery.unfinished/blocked', not unfinished and not blocked, f'unfinished={unfinished!r}, blocked={blocked!r}')
    status = git(candidate, 'status', '--porcelain=v1', '-z', '--untracked-files=all').split(b'\0')
    found = []
    staged = []
    for entry in status:
        if not entry:
            continue
        line = entry.decode('utf-8', 'surrogateescape')
        if line.startswith('?' * 2 + ' '):
            found.append(line[3:].replace('\\', '/'))
        elif len(line) >= 3 and line[0] != ' ':
            staged.append(line)
    expected_untracked = [x.replace('\\', '/') for x in untracked]
    expected_allowed = [x.replace('\\', '/') for x in allowed]
    expected = sorted(expected_untracked + expected_allowed)
    invalid_allowed = [x for x in allowed if not is_generated_untracked(x)]
    record('candidate.allowed_untracked', not invalid_allowed, f'非生成物 allowed_untracked: {invalid_allowed!r}' if invalid_allowed else 'allowed_untracked 均为生成物')
    record('candidate.untracked_files', sorted(found) == expected and not set(expected_untracked) & set(expected_allowed), f'实际={sorted(found)!r}; 期望={expected!r}')
    record('candidate.staged', not staged, f'暂存变更={staged!r}; tracked_diff_blob 仅覆盖未暂存 diff')
    diff = git(candidate, 'diff', '--no-ext-diff', '--no-textconv')
    actual_blob = subprocess.run(['git', '-C', str(candidate), 'hash-object', '--stdin'], input=diff, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if actual_blob.returncode:
        raise ConfigurationError('git hash-object --stdin 失败: ' + actual_blob.stderr.decode('utf-8', 'replace'))
    actual = actual_blob.stdout.decode('ascii').strip()
    record('candidate.tracked_diff_blob', actual == blob.lower(), f'实际={actual}, manifest={blob}')
    head = git(candidate, 'rev-parse', 'HEAD^{commit}').strip()
    base = git(candidate, 'rev-parse', baseline_ref + '^{commit}').strip()
    review_base = git(candidate, 'rev-parse', rb['ref'] + '^{commit}').strip()
    record('baseline.ref', head == base == review_base, f'HEAD={head.decode()}, manifest={base.decode()}, review={review_base.decode()}')
    proc = subprocess.run(['git', '-C', str(candidate), 'diff', '--check'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    record('candidate.diff_check', proc.returncode == 0, (proc.stdout + proc.stderr).decode('utf-8', 'replace').strip() or '无空白错误')
    for path in logs + [rc['log'], rb['log']]:
        record('log', bool(path) and Path(path).is_file(), f'{path!r} {"存在" if path and Path(path).is_file() else "不存在"}')
    record('changed_docs', profile != 'doc' or bool(docs), f'profile={profile}, changed_docs={docs!r}')
    for name in docs:
        try:
            content = relative(candidate, name).read_text(encoding='utf-8', errors='strict')
            bad = [str(i) for i, line in enumerate(content.splitlines(), 1) if re.search(r'\?{2,}|\ufffd', line)]
            record('doc.encoding', not bad, f'{name}: ' + ('异常行 ' + ', '.join(bad) if bad else 'UTF-8 正常'))
        except (OSError, UnicodeError) as exc:
            record('doc.encoding', False, f'{name}: {exc}')
    record('review.verdict', r.get('verdict') == 'approved', f"verdict={r.get('verdict')!r}")
    record('review.new_failures', new_failures == 0, f'new_failures={new_failures}')
    record('review.candidate', rc['failures'] == 0 and rc['errors'] == 0, f"failures={rc['failures']}, errors={rc['errors']}")
    record('review.baseline_failure_names', rb['failures'] == len(names), f"baseline.failures={rb['failures']}, 名称数={len(names)}")
    for name in ('bridges/talk_task_tools.py', 'bridges/initiator_followup.py'):
        if name.encode() not in git(candidate, 'diff', '--name-only', '-z') .split(b'\0'):
            continue
        try:
            before = git(candidate, 'show', baseline_ref + ':' + name).decode('utf-8')
            after = relative(candidate, name).read_text(encoding='utf-8')
            for symbol in ('TOOL_SCHEMAS', 'PROJECT_TOOL_NAMES'):
                touched = referenced_statements(before, symbol) != referenced_statements(after, symbol)
                record('authorized_mutations', not touched or symbol in mutations, f'{name}: {symbol} {"已变更" if touched else "未变更"}, 授权={symbol in mutations}')
        except (OSError, UnicodeError, SyntaxError) as exc:
            record('authorized_mutations', False, f'{name}: 无法比较常量: {exc}')
    main_status = git(root, 'status', '--porcelain', '--untracked-files=no')
    record('project_root.clean', not main_status, main_status.decode('utf-8', 'replace').strip() or 'tracked 工作树干净')
    return results


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8')
        except (AttributeError, OSError, ValueError):
            pass
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    cmd = sub.add_parser('check')
    cmd.add_argument('--manifest', required=True)
    cmd.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    try:
        checks = check(args.manifest)
    except ConfigurationError as exc:
        if args.json:
            print(json.dumps({'status': 'error', 'error': str(exc)}, ensure_ascii=False))
        else:
            print(f'配置错误: {exc}', file=sys.stderr)
        return 2
    failed = sum(x['result'] == 'fail' for x in checks)
    if args.json:
        print(json.dumps({'status': 'fail' if failed else 'pass', 'checks': checks, 'summary': {'total': len(checks), 'failed': failed}}, ensure_ascii=False))
    else:
        for item in checks:
            print(f"{item['result'].upper()} {item['check']}: {item['detail']}")
        print(f'总结: {len(checks)} 项，失败 {failed} 项')
    return int(bool(failed))


if __name__ == '__main__':
    sys.exit(main())


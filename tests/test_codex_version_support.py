from types import SimpleNamespace
from unittest.mock import patch
import pytest

from bridges.codex_execution_native import (CodexNativeError, check_codex,
    detect_capabilities, parse_codex_version)

ROOT = '''Commands:\n  exec  Run non-interactively\nOptions:\n      --strict-config\n'''
EXEC = '''Arguments:\n  [PROMPT]\n    If `-` is used, instructions are read from stdin.\n\nOptions:\n  -c, --config <value>\n      --disable <feature>\n  -s, --sandbox <mode>\n  -m, --model <model>\n      --skip-git-repo-check\n      --ignore-rules\n'''

def fake_cli(version, root=ROOT, help_text=EXEC):
    def run(args, **kwargs):
        return SimpleNamespace(stdout={'--version': 'codex-cli '+version, '--help': root,
            'exec': help_text}[args[1]])
    return run

@pytest.mark.parametrize('text,expected', [('codex-cli 0.169.0', (0,169,0)), ('codex 0.164.0', (0,164,0))])
def test_parse(text, expected):
    assert parse_codex_version(text) == expected

def test_unparseable():
    with pytest.raises(CodexNativeError, match='codex_version_unparseable'):
        parse_codex_version('codex unknown')

def probe(version, root=ROOT, help_text=EXEC):
    def run(args, **kwargs):
        return SimpleNamespace(stdout={'--version': 'codex-cli '+version, '--help': root,
            'exec': help_text}[args[1]])
    with patch('bridges.codex_execution_native.subprocess.run', side_effect=run):
        return check_codex('synthetic')

def test_old_version_rejected():
    with pytest.raises(CodexNativeError, match=r'codex_version_unsupported.*0.162.9.*0.163.0'):
        probe('0.162.9')

@pytest.mark.parametrize('version', ['0.163.0', '0.164.0', '0.169.0'])
def test_supported(version):
    result = probe(version)
    assert result['allowed'] and result['warning'] is None
    assert all(result['capabilities'].values())

def test_newer_warning():
    assert probe('0.170.0')['warning'] == 'codex_version_untested'

def test_capabilities_and_missing():
    assert all(detect_capabilities(ROOT, EXEC).values())
    with pytest.raises(CodexNativeError, match=r'codex_capability_missing:--ignore-rules.*0.169.0'):
        probe('0.169.0', help_text=EXEC.replace('      --ignore-rules', '      --ignore-rules-extra'))

def test_prose_is_not_a_flag():
    assert not detect_capabilities(ROOT, EXEC.replace('  -m, --model <model>', '    mentions --model here'))['--model']

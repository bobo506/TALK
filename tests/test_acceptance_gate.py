import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import acceptance_gate


class AcceptanceGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.git('init', '-q')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'user.name', 'Test')
        (self.root / 'bridges').mkdir()
        (self.root / 'bridges/talk_task_tools.py').write_text('PROJECT_TOOL_NAMES = ["a"]\n', encoding='utf-8')
        (self.root / 'readme.txt').write_text('original\n', encoding='utf-8')
        self.git('add', '.')
        self.git('commit', '-qm', 'baseline')
        self.ref = self.git('rev-parse', 'HEAD').decode().strip()
        self.project = self.root / 'project'
        self.project.mkdir()
        subprocess.run(['git', '-C', str(self.project), 'init', '-q'], check=True)
        self.evidence = self.root.parent / (self.root.name + '-evidence')
        self.evidence.mkdir()
        self.addCleanup(lambda: __import__('shutil').rmtree(self.evidence))
        self.log = self.evidence / 'run.log'
        self.log.write_text('evidence', encoding='utf-8')
        self.delivery = {'task_id': '470', 'conclusion': 'complete', 'verification': [{'check': 'test', 'result': 'pass', 'evidence': 'log'}], 'unfinished': [], 'blocked': [], 'completed': ['done'], 'changed_files': [], 'baseline': {'ref': self.ref, 'diff_note': 'test'}, 'limitations': [], 'progress_draft': {'summary': 'done', 'next': 'review'}}
        self.review = {'schema': 'talk-review-gate-1', 'task_id': 470, 'verdict': 'approved', 'candidate': {'tests': 2, 'failures': 0, 'errors': 0, 'skipped': 0, 'log': str(self.log)}, 'baseline': {'ref': self.ref, 'tests': 2, 'failures': 1, 'errors': 0, 'skipped': 0, 'log': str(self.log)}, 'baseline_failure_names': ['known'], 'new_failures': 0}
        self.manifest = {'schema': 'talk-acceptance-gate-1', 'profile': 'code', 'task_id': 470, 'project_root': str(self.project), 'candidate': str(self.root), 'baseline_ref': self.ref, 'tracked_diff_blob': self.blob(), 'untracked_files': ['project/'], 'allowed_untracked': [], 'delivery': str(self.evidence / 'delivery.json'), 'review': str(self.evidence / 'review.json'), 'changed_docs': [], 'authorized_mutations': [], 'logs': [str(self.log)]}
        # Nested repository appears as one untracked entry.

    def git(self, *args, input=None):
        return subprocess.run(['git', '-C', str(self.root), *args], input=input, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout

    def blob(self):
        return self.git('hash-object', '--stdin', input=self.git('diff')).decode().strip()

    def run_gate(self):
        for name, obj in [('manifest', self.manifest), ('delivery', self.delivery), ('review', self.review)]:
            (self.evidence / (name + '.json')).write_text(json.dumps(obj), encoding='utf-8')
        return acceptance_gate.check(self.evidence / 'manifest.json')

    def failures(self):
        return [x['check'] for x in self.run_gate() if x['result'] == 'fail']

    def test_good_code(self):
        self.assertEqual([], self.failures())

    def test_partial(self):
        self.delivery['conclusion'] = 'partial'
        self.assertIn('delivery.conclusion', self.failures())

    def test_untracked_file_hash_is_not_diff_hash(self):
        (self.root / 'new.txt').write_text('new', encoding='utf-8')
        self.manifest['untracked_files'].append('new.txt')
        self.manifest['tracked_diff_blob'] = self.git('hash-object', 'new.txt').decode().strip()
        self.assertIn('candidate.tracked_diff_blob', self.failures())

    def test_new_failures(self):
        self.review['new_failures'] = 1
        self.assertIn('review.new_failures', self.failures())

    def test_bad_docs(self):
        for content in ('bad ?? line', 'bad \ufffd line', b'\xff'):
            with self.subTest(content=content):
                p = self.root / 'doc.md'
                p.write_bytes(content if isinstance(content, bytes) else content.encode('utf-8'))
                self.manifest['untracked_files'] = ['doc.md', 'project/']
                self.manifest['changed_docs'] = ['doc.md']
                self.assertIn('doc.encoding', self.failures())

    def test_script_passes_its_own_doc_encoding_check(self):
        script = self.root / 'acceptance_gate.py'
        script.write_bytes(Path(acceptance_gate.__file__).read_bytes())
        self.manifest['untracked_files'].append('acceptance_gate.py')
        self.manifest['changed_docs'] = ['acceptance_gate.py']
        self.assertNotIn('doc.encoding', self.failures())

    def test_constant_unauthorized(self):
        (self.root / 'bridges/talk_task_tools.py').write_text('PROJECT_TOOL_NAMES = ["a", "b"]\n', encoding='utf-8')
        self.manifest['tracked_diff_blob'] = self.blob()
        self.assertIn('authorized_mutations', self.failures())
        self.manifest['authorized_mutations'] = ['PROJECT_TOOL_NAMES']
        self.assertNotIn('authorized_mutations', self.failures())

    def test_allowed_untracked_requires_generated_pattern(self):
        (self.root / 'scripts').mkdir()
        (self.root / 'scripts/evil.py').write_text('x', encoding='utf-8')
        self.manifest['allowed_untracked'] = ['scripts/evil.py']
        failures = [x for x in self.run_gate() if x['result'] == 'fail']
        self.assertEqual(['candidate.allowed_untracked'], [x['check'] for x in failures])
        self.assertIn('非生成物 allowed_untracked', failures[0]['detail'])

    def test_cli_json_utf8_redirect_pass(self):
        self.run_gate()
        output = self.evidence / 'output.json'
        env = dict(os.environ, PYTHONIOENCODING='cp936')
        with output.open('wb') as stream:
            result = subprocess.run([sys.executable, '-m', 'scripts.acceptance_gate', 'check', '--manifest', str(self.evidence / 'manifest.json'), '--json'], stdout=stream, stderr=subprocess.PIPE, env=env)
        self.assertEqual(0, result.returncode, result.stderr)
        with output.open(encoding='utf-8') as stream:
            data = json.load(stream)
        self.assertEqual('pass', data['status'])
        self.assertEqual(0, data['summary']['failed'])

    def test_cli_partial_exit_one(self):
        self.delivery['conclusion'] = 'partial'
        self.run_gate()
        result = subprocess.run([sys.executable, '-m', 'scripts.acceptance_gate', 'check', '--manifest', str(self.evidence / 'manifest.json'), '--json'], capture_output=True)
        self.assertEqual(1, result.returncode, result.stderr)
        data = json.loads(result.stdout.decode('utf-8'))
        self.assertEqual('fail', data['status'])
        self.assertIn('delivery.conclusion', [x['check'] for x in data['checks'] if x['result'] == 'fail'])

    def test_generated_untracked_and_overlap(self):
        (self.root / 'Microsoft').mkdir()
        (self.root / 'Microsoft/generated.txt').write_text('x', encoding='utf-8')
        (self.root / 'run.log').write_text('x', encoding='utf-8')
        self.manifest['allowed_untracked'] = ['Microsoft/generated.txt', 'run.log']
        self.assertEqual([], self.failures())
        self.manifest['untracked_files'].append('run.log')
        self.assertIn('candidate.untracked_files', self.failures())

    def test_constant_comment_does_not_require_authorization(self):
        path = self.root / 'bridges/talk_task_tools.py'
        path.write_text('# TOOL_SCHEMAS and PROJECT_TOOL_NAMES\nPROJECT_TOOL_NAMES = ["a"]\n', encoding='utf-8')
        self.manifest['tracked_diff_blob'] = self.blob()
        self.assertEqual([], self.failures())

    def test_untracked_and_baseline_evidence(self):
        (self.root / 'surprise').write_text('x', encoding='utf-8')
        self.review['baseline_failure_names'] = []
        self.review['candidate']['log'] = str(self.evidence / 'missing')
        errors = self.failures()
        self.assertIn('candidate.untracked_files', errors)
        self.assertIn('review.baseline_failure_names', errors)
        self.assertIn('log', errors)

    def test_doc_profile_and_cli_configuration(self):
        self.manifest['profile'] = 'doc'
        self.assertIn('changed_docs', self.failures())
        self.manifest['schema'] = 'wrong'
        (self.evidence / 'manifest.json').write_text(json.dumps(self.manifest), encoding='utf-8')
        result = subprocess.run([sys.executable, '-m', 'scripts.acceptance_gate', 'check', '--manifest', str(self.evidence / 'manifest.json'), '--json'], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(2, result.returncode)
        self.assertEqual('error', json.loads(result.stdout)['status'])


if __name__ == '__main__':
    unittest.main()

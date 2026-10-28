"""Codex preparation contracts using synthetic homes, database, CLI and RPC."""
import asyncio
from contextlib import closing
import io
import json
import os
from pathlib import Path
import sqlite3
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import codex_role_setup as setup
from scripts import codex_role_host as host
from tests import test_kimi_role_setup as fixtures


class CodexSetupTests(unittest.TestCase):
    def setUp(self):
        fixtures.SetupTests.setUp(self)
        self.addCleanup(self.temp.cleanup)
        self.exe = self.base / 'codex.exe'
        self.exe.write_bytes(b'synthetic native executable, never executed')
        pointer = json.loads((self.root / '.talk/runtime.local.json').read_text('utf-8'))
        self.runtime = Path(pointer['config_file'])
        config = json.loads(self.runtime.read_text('utf-8'))
        config['codex'] = {'enabled': True, 'executable': str(self.exe)}
        self.runtime.write_text(json.dumps(config),encoding='utf-8')
        with closing(sqlite3.connect(self.dbpath)) as db, db:
            db.execute("UPDATE runner_registry SET runtime='codex'")
            db.execute("UPDATE project_role_bindings SET model_alias='public-selected-alias', model_id='selected-exact-model', provider_id='openai', connection_ref='native-codex-chatgpt-login'")

    def begin(self, event_log=None):
        events = event_log if event_log is not None else []
        def spawn(home, project, member, lock, callback, **kwargs):
            self.assertEqual(kwargs, {'lock_name':'codex-role-setup'})
            events.append('spawn')
            process = callback(0)
            return process, None
        def popen(argv, **kwargs):
            self.assertEqual(argv,[str(self.exe),'login','--device-auth'])
            env = kwargs['env']
            self.assertNotIn('OPENAI_API_KEY', env)
            self.assertEqual(env['CODEX_HOME'],str(self.state / 'native/prj_1/agent_one/.codex'))
            self.assertNotEqual(env['CODEX_HOME'],str(self.manual))
            self.assertEqual(kwargs['stdin'],setup.subprocess.DEVNULL)
            return SimpleNamespace(poll=lambda:0, stdout=io.StringIO())
        with patch.object(setup,'require_version'), \
             patch.object(setup.native_setup_process,'stop_previous',side_effect=lambda *args:events.append('stop_old')), \
             patch.object(setup.native_setup_process,'spawn_recorded',side_effect=spawn), \
             patch.dict(os.environ,{'CODEX_HOME':str(self.manual),'OPENAI_API_KEY':'NEVER_COPY'}):
            attempt = setup.begin_native_login('prj_1','agent:one',root=self.root,popen=popen)
        self.addCleanup(setup.release_native_login,attempt)
        return attempt

    def test_independent_home_selected_model_file_store_and_stop_before_spawn(self):
        events=[]
        attempt=self.begin(events)
        self.assertEqual(events,['stop_old','spawn'])
        value=setup.read_config(attempt.native_home/'config.toml')
        self.assertEqual(value['model'],'selected-exact-model')
        self.assertEqual(value['cli_auth_credentials_store'],'file')
        self.assertEqual(value['forced_login_method'],'chatgpt')
        self.assertFalse((attempt.native_home/'auth.json').exists())
        self.assertNotIn('DO_NOT_COPY_SOURCE',(attempt.native_home/'config.toml').read_text('utf-8'))

    def test_unknown_old_process_blocks_before_new_spawn_and_config_write(self):
        with patch.object(setup.native_setup_process,'stop_previous',side_effect=RuntimeError('native_previous_process_unverified')), \
             patch.object(setup.native_setup_process,'spawn_recorded') as spawn:
            with self.assertRaisesRegex(RuntimeError,'native_previous_process_unverified'):
                setup.begin_native_login('prj_1','agent:one',root=self.root)
        spawn.assert_not_called()
        self.assertFalse((self.state/'native/prj_1/agent_one/.codex/config.toml').exists())

    def test_version_mismatch_blocks_device_authorization(self):
        result=SimpleNamespace(stdout='codex-cli 0.999.0')
        with patch.object(setup.subprocess,'run',return_value=result):
            with self.assertRaisesRegex(setup.SetupError,'native_cli_version_unsupported'):
                setup.require_version(str(self.exe),self.root,{})

    def test_version_gate_accepts_current_0_164_and_legacy_0_163(self):
        for version in ('0.163.0','0.164.0'):
            with self.subTest(version=version), patch.object(setup.subprocess,'run',
                    return_value=SimpleNamespace(stdout='codex-cli '+version+'\n')):
                self.assertEqual(setup.require_version(str(self.exe),self.root,{}),version)

    def test_terra_uses_official_low_instead_of_prior_xhigh(self):
        with closing(sqlite3.connect(self.dbpath)) as db, db:
            db.execute("UPDATE project_role_bindings SET model_id='gpt-6.1-terra', model_alias='gpt-6.1-terra'")
        attempt=self.begin()
        path=attempt.native_home/'config.toml'
        setup.write_config(path,dict(setup.read_config(path),model_reasoning_effort='xhigh'))
        async def low(_attempt): return 'low'
        with patch.object(setup,'_model_effort',low):
            setup.finish_native_login(attempt)
        value=setup.read_config(path)
        self.assertEqual(value['model'],'gpt-6.1-terra')
        self.assertEqual(value['model_reasoning_effort'],'low')

    def test_successful_metadata_check_writes_exact_model_and_returned_effort(self):
        attempt=self.begin()
        path=attempt.native_home/'config.toml'
        setup.write_config(path,dict(setup.read_config(path),model_reasoning_effort='xhigh'))
        calls=[]
        class RPC:
            def __init__(self,spec,root):
                self.spec=spec
            async def open(self):calls.append('initialize')
            async def rpc(self,method,params):
                calls.append(method)
                if method=='account/read':return {'account':{'type':'chatgpt','email':'not-retained'}}
                return {'data':[{'model':'selected-exact-model','defaultReasoningEffort':'high',
                    'supportedReasoningEfforts':[{'reasoningEffort':'high'}]}],'nextCursor':None}
            async def close(self):calls.append('close')
        with patch.object(setup,'CodexNative',RPC):
            setup.finish_native_login(attempt)
        self.assertEqual(calls,['initialize','account/read','model/list','close'])
        value=setup.read_config(attempt.native_home/'config.toml')
        self.assertEqual(value['model'],'selected-exact-model')
        self.assertEqual(value['model_reasoning_effort'],'high')
        self.assertNotIn('not-retained',(attempt.native_home/'config.toml').read_text('utf-8'))

    def metadata(self, attempt, pages, account='chatgpt'):
        queue=iter(pages)
        class RPC:
            def __init__(self,*args):pass
            async def open(self):pass
            async def rpc(self,method,params):
                if method=='account/read':return {'account':{'type':account}}
                return next(queue)
            async def close(self):pass
        with patch.object(setup,'CodexNative',RPC):
            return asyncio.run(setup._model_effort(attempt))

    def test_missing_selected_model_refuses_substitution_and_closes_rpc(self):
        attempt=self.begin()
        with self.assertRaisesRegex(setup.SetupError,'native_selected_model_unavailable'):
            self.metadata(attempt,[{'data':[{'model':'other-model'}],'nextCursor':None}])
        self.assertEqual(setup.read_config(attempt.native_home/'config.toml')['model'],'selected-exact-model')

    def test_wrong_auth_type_fails_without_falling_back_to_global_key(self):
        attempt=self.begin()
        with self.assertRaisesRegex(setup.SetupError,'native_authorization_failed'):
            self.metadata(attempt,[],account='apiKey')

    def test_pagination_uses_official_default_instead_of_previous_xhigh(self):
        attempt=self.begin()
        value=setup.read_config(attempt.native_home/'config.toml')
        setup.write_config(attempt.native_home/'config.toml',dict(value,model_reasoning_effort='xhigh'))
        self.assertEqual(self.metadata(attempt,[{'data':[],'nextCursor':'next'},
            {'data':[{'model':'selected-exact-model','defaultReasoningEffort':'medium',
                'supportedReasoningEfforts':[{'reasoningEffort':'medium'},{'reasoningEffort':'xhigh'}]}], 'nextCursor':None}]),'medium')

    def test_missing_official_default_does_not_fall_back_to_local_xhigh(self):
        attempt=self.begin()
        path=attempt.native_home/'config.toml'
        setup.write_config(path,dict(setup.read_config(path),model_reasoning_effort='xhigh'))
        with self.assertRaisesRegex(setup.SetupError,'native_model_configuration_required'):
            self.metadata(attempt,[{'data':[{'model':'selected-exact-model',
                'supportedReasoningEfforts':[{'reasoningEffort':'xhigh'}]}],'nextCursor':None}])

    def test_official_default_must_be_supported_by_catalog_and_native_adapter(self):
        attempt=self.begin()
        for default,supported in [('high',['medium']),('ultra',['ultra'])]:
            with self.subTest(default=default),self.assertRaisesRegex(setup.SetupError,'native_model_configuration_required'):
                self.metadata(attempt,[{'data':[{'model':'selected-exact-model','defaultReasoningEffort':default,
                    'supportedReasoningEfforts':[{'reasoningEffort':effort} for effort in supported]}],'nextCursor':None}])

    def test_binding_change_after_login_prevents_model_configuration_write(self):
        attempt=self.begin()
        with closing(sqlite3.connect(self.dbpath)) as db, db:
            db.execute("UPDATE project_role_bindings SET model_id='changed-model'")
        with patch.object(setup,'_model_effort',return_value=self._effort()):
            with self.assertRaisesRegex(setup.SetupError,'native_model_selection_changed'):
                setup.finish_native_login(attempt)
        self.assertNotIn('model_reasoning_effort',setup.read_config(attempt.native_home/'config.toml'))

    async def _effort(self):return 'high'

    def test_unrecognized_existing_config_is_never_overwritten(self):
        native=self.state/'native/prj_1/agent_one/.codex'
        native.mkdir(parents=True)
        path=native/'config.toml'
        path.write_text('cli_auth_credentials_store="keyring"\nmodel="some-other"\n',encoding='utf-8')
        before=path.read_bytes()
        with patch.object(setup.native_setup_process,'stop_previous'):
            with self.assertRaisesRegex(setup.SetupError,'native_model_configuration_required'):
                setup.begin_native_login('prj_1','agent:one',root=self.root)
        self.assertEqual(path.read_bytes(),before)


class CodexCommandTests(unittest.TestCase):
    def test_host_command_preserves_exact_model_safe_default_profile_and_role_home(self):
        import tempfile, shlex
        from scripts import role_service_host as rsh
        with tempfile.TemporaryDirectory() as name:
            root=Path(name)
            manager=host.CodexRoleHost(SimpleNamespace(),project='p',member='agent:new',display_name='New',
                task_profile='review',private=root/'manager',codex_executable=str(root/'codex.exe'),
                state_dir=root/'state',project_root=root)
            config={'model':'exact-selected-model','model_reasoning_effort':'xhigh'}
            with patch.object(manager,'_configuration',return_value=config), \
                 patch.object(setup,'require_version'),patch('cli.profiles.load_profile',return_value={}), \
                 patch('cli.profiles.compose_system_prompt',side_effect=lambda prompt,profile:prompt):
                argv,_,_=manager.build_entry_argv('codex','public-alias')
            command=shlex.split(argv[argv.index('--codex-task-command')+1])
            self.assertEqual(command[command.index('--model')+1],'exact-selected-model')
            self.assertEqual(command[command.index('--sandbox')+1],'read-only')
            self.assertEqual(command[1:4],['-a','never','--strict-config'])
            self.assertFalse(any('bypass' in a for a in command))
            env=manager.child_environment('p','agent:new')
            self.assertEqual(Path(env['CODEX_HOME']),manager.store.native_home_dir('p','agent:new')/'.codex')
            # Validate the produced command against the existing strict native adapter,
            # rather than merely checking how this builder spells the arguments.
            from bridges import codex_execution_native as native
            (root/'codex.exe').write_bytes(b'synthetic, never executed')
            setup.host.ensure_private_dir(Path(env['CODEX_HOME']))
            setup.write_config(Path(env['CODEX_HOME'])/'config.toml',dict(setup.BASE_CONFIG,**config))
            binding=dict(runtime='codex',runner_id='runner:synthetic',provider_id='openai',
                model_id='exact-selected-model',binding_fingerprint='synthetic-fingerprint')
            with patch.dict(os.environ,env),patch.object(native.subprocess,'run',return_value=SimpleNamespace(stdout='codex-cli 0.163.0')):
                launch=native.resolve_launch(command,root,binding)
            self.assertEqual((launch.model,launch.effort,launch.sandbox),('exact-selected-model','xhigh','read-only'))

    def test_native_adapter_negotiates_0_164_and_rejects_unlisted_versions(self):
        import tempfile, shlex
        from bridges import codex_execution_native as native
        from scripts import codex_role_host as codex_host
        with tempfile.TemporaryDirectory() as name:
            root=Path(name)
            (root/'codex.exe').write_bytes(b'synthetic, never executed')
            manager=codex_host.CodexRoleHost(SimpleNamespace(),project='p',member='agent:new',display_name='New',
                task_profile='review',private=root/'manager',codex_executable=str(root/'codex.exe'),
                state_dir=root/'state',project_root=root)
            config={'model':'gpt-6.1-terra','model_reasoning_effort':'low'}
            with patch.object(manager,'_configuration',return_value=config), \
                 patch.object(setup,'require_version'),patch('cli.profiles.load_profile',return_value={}), \
                 patch('cli.profiles.compose_system_prompt',side_effect=lambda prompt,profile:prompt):
                argv,_,_=manager.build_entry_argv('codex','gpt-6.1-terra')
            command=shlex.split(argv[argv.index('--codex-task-command')+1])
            env=manager.child_environment('p','agent:new')
            setup.host.ensure_private_dir(Path(env['CODEX_HOME']))
            setup.write_config(Path(env['CODEX_HOME'])/'config.toml',dict(setup.BASE_CONFIG,**config))
            binding=dict(runtime='codex',runner_id='runner:synthetic',provider_id='openai',
                model_id='gpt-6.1-terra',binding_fingerprint='synthetic-fingerprint')
            with patch.dict(os.environ,env),patch.object(native.subprocess,'run',
                    return_value=SimpleNamespace(stdout='codex-cli 0.164.0')):
                launch=native.resolve_launch(command,root,binding)
            self.assertEqual((launch.version,launch.effort),('0.164.0','low'))
            with patch.dict(os.environ,env),patch.object(native.subprocess,'run',
                    return_value=SimpleNamespace(stdout='codex-cli 0.165.0')):
                with self.assertRaisesRegex(native.CodexNativeError,'version_unsupported'):
                    native.resolve_launch(command,root,binding)

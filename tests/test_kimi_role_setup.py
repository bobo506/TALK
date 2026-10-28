import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from scripts import kimi_role_setup as setup
from scripts import kimi_role_host


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / 'repo'
        self.root.mkdir()
        (self.root / '.talk').mkdir()
        self.state = self.base / 'state'
        self.state.mkdir()
        self.dbpath = self.base / 'synthetic.db'
        db = sqlite3.connect(self.dbpath)
        db.executescript('''
            CREATE TABLE project_roles(project_id TEXT, member_id TEXT, archived_at TEXT);
            CREATE TABLE project_role_bindings(project_id TEXT, member_id TEXT, runner_id TEXT,
                 model_alias TEXT, model_id TEXT, provider_id TEXT, model_source TEXT, connection_ref TEXT);
            CREATE TABLE runner_registry(runner_id TEXT, runtime TEXT, control_kind TEXT);
            CREATE TABLE role_service_state(project_id TEXT, member_id TEXT, desired_state TEXT,
                 observed_state TEXT, owner_host TEXT, process_launch_id TEXT);
            INSERT INTO project_roles VALUES('prj_1','agent:one',NULL);
            INSERT INTO runner_registry VALUES('r','kimi-code','managed_cli');
            INSERT INTO project_role_bindings VALUES('prj_1','agent:one','r',
                 'kimi-code/k3.1-pro','k3.1-pro','managed:kimi-code','builtin','native-kimi-code-managed-login');
            INSERT INTO role_service_state VALUES('prj_1','agent:one','stopped','stopped',NULL,NULL);
        ''')
        db.commit(); db.close()
        runtime = self.base / 'runtime.json'
        runtime.write_text(json.dumps({'schema':'talk-runtime-config-1','project_id':'prj_1',
                                      'project_root':str(self.root), 'state_dir':str(self.state)}), encoding='utf-8')
        (self.root / '.talk/runtime.local.json').write_text(json.dumps({'schema':'talk-local-runtime-1',
              'config_file':str(runtime), 'database_file':str(self.dbpath)}), encoding='utf-8')
        self.manual = self.base / 'manual'
        self.manual.mkdir()
        (self.manual / 'config.toml').write_text('''
[providers."managed:kimi-code"]
api_key = "DO_NOT_COPY_SOURCE"
[models."kimi-code/k3.1-pro"]
provider = "managed:kimi-code"
model = "k3.1-pro"
max_context_size = 1000000
capabilities = ["thinking"]
support_efforts = ["medium", "high"]
default_effort = "high"
display_name = "K3.1 Pro"
''', encoding='utf-8')

    def tearDown(self):
        self.temp.cleanup()

    def private_dir(self, p):
        p.mkdir(parents=True, exist_ok=True)
        return p

    def login(self, argv, cwd, env, check):
        self.assertEqual(argv, ['fake-kimi', 'login'])
        self.assertNotEqual(env['KIMI_CODE_HOME'], str(self.manual))
        self.assertEqual(env['HOME'], env['USERPROFILE'])
        self.assertNotIn('KIMI_MODEL_API_KEY', env)
        target = Path(env['KIMI_CODE_HOME']) / 'config.toml'
        target.write_text('[providers."managed:kimi-code"]\ntoken="DESTINATION_SECRET"\n', encoding='utf-8')
        return type('Result', (), {'returncode': 0})()

    def run_setup(self, login=None):
        with patch.dict(os.environ, {'KIMI_CODE_HOME':str(self.manual), 'KIMI_MODEL_API_KEY':'BAD'}), \
             patch.object(setup.shutil, 'which', return_value='fake-kimi'), \
             patch.object(setup.host, 'ensure_private_dir', side_effect=self.private_dir), \
             patch.object(setup, 'acquire_lock', return_value={'token':'synthetic'}), \
             patch.object(setup, 'release_lock', return_value=True):
            setup.setup('prj_1','agent:one',root=self.root,run=login or self.login)

    def binding_client(self, binding=None):
        binding = binding or {'runtime':'kimi-code','model_alias':'kimi-code/k3.1-pro','model_id':'k3.1-pro','provider_id':'managed:kimi-code'}
        return type('Client',(),{'request':lambda self,*args: {'data':[{'member_id':'agent:one','binding_state':'bound','binding':binding}]}})()

    def test_login_uses_role_home_and_copies_only_public_selected_model(self):
        self.run_setup()
        target = self.state / 'native/prj_1/agent_one/.kimi-code/config.toml'
        text = target.read_text(encoding='utf-8')
        self.assertIn('DESTINATION_SECRET', text)
        self.assertNotIn('DO_NOT_COPY_SOURCE', text)
        with target.open('rb') as stream:
            parsed = setup.tomllib.load(stream)
        self.assertEqual(parsed['models']['kimi-code/k3.1-pro']['max_context_size'], 1000000)
        self.assertEqual(parsed['models']['kimi-code/k3.1-pro']['model'], 'k3.1-pro')
        self.assertEqual(parsed['models']['kimi-code/k3.1-pro']['default_effort'], 'high')
        self.assertEqual(parsed['models']['kimi-code/k3.1-pro']['support_efforts'], ['medium', 'high'])
        self.assertFalse((self.state/'kimi-dynamic/prj_1/agent_one/task-profile.json').exists())

    def test_login_model_can_be_used_without_manual_user_model_config(self):
        (self.manual / 'config.toml').unlink()
        def login_with_model(argv, cwd, env, check):
            target = Path(env['KIMI_CODE_HOME']) / 'config.toml'
            target.write_text('[providers."managed:kimi-code"]\n[models."kimi-code/k3.1-pro"]\nprovider="managed:kimi-code"\nmodel="k3.1-pro"\n',encoding='utf-8')
            return type('Result', (), {'returncode':0})()
        self.run_setup(login_with_model)
        self.assertTrue((self.state/'native/prj_1/agent_one/.kimi-code/config.toml').is_file())

    def test_login_catalog_model_works_when_manual_config_has_no_selected_alias(self):
        (self.manual / 'config.toml').write_text('[models."kimi-code/k3"]\nprovider="managed:kimi-code"\nmodel="k3"\n',encoding='utf-8')
        def login_with_model(argv, cwd, env, check):
            target = Path(env['KIMI_CODE_HOME']) / 'config.toml'
            target.write_text('[providers."managed:kimi-code"]\n[models."kimi-code/k3.1-pro"]\nprovider="managed:kimi-code"\nmodel="k3.1-pro"\n',encoding='utf-8')
            return type('Result', (), {'returncode':0})()
        self.run_setup(login_with_model)
        self.assertTrue((self.state/'native/prj_1/agent_one/.kimi-code/config.toml').is_file())

    def test_page_login_begin_finish_isolates_environment_and_public_model(self):
        from scripts import native_setup_process
        process = type('Process', (), {})()
        def popen(argv, **kwargs):
            self.assertEqual(argv, ['fake-kimi', 'login'])
            env = kwargs['env']
            self.assertNotEqual(env['KIMI_CODE_HOME'], str(self.manual))
            self.assertNotIn('KIMI_MODEL_API_KEY', env)
            target = Path(env['KIMI_CODE_HOME']) / 'config.toml'
            target.write_text('[providers."managed:kimi-code"]\ntoken="DESTINATION_SECRET"\n', encoding='utf-8')
            return process
        with patch.dict(os.environ, {'KIMI_CODE_HOME':str(self.manual), 'KIMI_MODEL_API_KEY':'BAD'}), \
             patch.object(setup.shutil, 'which', return_value='fake-kimi'), \
             patch.object(setup.host, 'ensure_private_dir', side_effect=self.private_dir), \
             patch.object(setup, 'acquire_lock', return_value={'token':'synthetic'}), \
             patch.object(setup, 'release_lock', return_value=True) as released, \
             patch.object(native_setup_process, 'spawn_recorded', side_effect=lambda *args: (args[-1](0), 'fake-generation')), \
             patch.object(native_setup_process, 'finish_record'):
            attempt = setup.begin_native_login('prj_1', 'agent:one', root=self.root, popen=popen)
            self.assertEqual(setup.finish_native_login(attempt), 'added')
        target = self.state / 'native/prj_1/agent_one/.kimi-code/config.toml'
        text = target.read_text(encoding='utf-8')
        self.assertIn('DESTINATION_SECRET', text)
        self.assertNotIn('DO_NOT_COPY_SOURCE', text)
        self.assertIn('k3.1-pro', text)
        self.assertEqual(released.call_count, 2)  # 短准备互斥及长授权锁各正常释放一次。

    def test_page_login_accepts_model_generated_by_official_login(self):
        from scripts import native_setup_process
        (self.manual / 'config.toml').unlink()
        process = type('Process', (), {})()
        def popen(argv, **kwargs):
            target = Path(kwargs['env']['KIMI_CODE_HOME']) / 'config.toml'
            target.write_text('[providers."managed:kimi-code"]\n[models."kimi-code/k3.1-pro"]\nprovider="managed:kimi-code"\nmodel="k3.1-pro"\n', encoding='utf-8')
            return process
        with patch.dict(os.environ, {'KIMI_CODE_HOME':str(self.manual)}), \
             patch.object(setup.shutil, 'which', return_value='fake-kimi'), \
             patch.object(setup.host, 'ensure_private_dir', side_effect=self.private_dir), \
             patch.object(setup, 'acquire_lock', return_value={'token':'synthetic'}), \
             patch.object(setup, 'release_lock', return_value=True), \
             patch.object(native_setup_process, 'spawn_recorded', side_effect=lambda *args: (args[-1](0), 'fake-generation')), \
             patch.object(native_setup_process, 'finish_record'):
            attempt = setup.begin_native_login('prj_1', 'agent:one', root=self.root, popen=popen)
            self.assertEqual(setup.finish_native_login(attempt), 'existing')

    def test_failed_login_does_not_prepare_model(self):
        def fail(*args, **kwargs): return type('Result', (), {'returncode': 1})()
        with self.assertRaisesRegex(setup.SetupError, '登录未完成'):
            self.run_setup(fail)
        self.assertFalse((self.state / 'native/prj_1/agent_one/.kimi-code/config.toml').exists())

    def test_running_role_cannot_begin_login(self):
        db = sqlite3.connect(self.dbpath)
        db.execute("UPDATE role_service_state SET desired_state='running', observed_state='running'")
        db.commit(); db.close()
        with self.assertRaisesRegex(setup.SetupError, '先关闭'):
            self.run_setup(lambda *a, **k: self.fail('must not run login'))

    def test_changed_binding_after_login_does_not_write_model(self):
        def login_change(*args, **kwargs):
            result = self.login(*args, **kwargs)
            db = sqlite3.connect(self.dbpath)
            db.execute("UPDATE project_role_bindings SET model_id='other'")
            db.commit(); db.close()
            return result
        with self.assertRaisesRegex(setup.SetupError, '发生变化'):
            self.run_setup(login_change)
        text = (self.state / 'native/prj_1/agent_one/.kimi-code/config.toml').read_text(encoding='utf-8')
        self.assertNotIn('[models.', text)

    def test_wrong_source_is_refused_and_archived_role_fails_before_login(self):
        (self.manual / 'config.toml').write_text('[models."kimi-code/k3.1-pro"]\nmodel="wrong"\nprovider="managed:kimi-code"\n',encoding='utf-8')
        with self.assertRaisesRegex(setup.SetupError, '不一致'):
            self.run_setup()
        db=sqlite3.connect(self.dbpath); db.execute("UPDATE project_roles SET archived_at='yes'"); db.commit(); db.close()
        with self.assertRaisesRegex(setup.SetupError, '不存在'):
            self.run_setup(lambda *a, **k: self.fail('must not run login'))

    def test_existing_conflicting_alias_is_never_overwritten(self):
        config=self.base/'config.toml'
        original='[providers."managed:kimi-code"]\n[models."kimi-code/k3.1-pro"]\nprovider="managed:kimi-code"\nmodel="wrong"\n'
        config.write_text(original, encoding='utf-8')
        with self.assertRaisesRegex(setup.SetupError, '未覆盖'):
            setup._append_model(config, ('kimi-code/k3.1-pro','k3.1-pro','managed:kimi-code'), {})
        self.assertEqual(config.read_text(encoding='utf-8'),original)

    def test_existing_matching_model_is_left_unchanged(self):
        config=self.base/'config.toml'
        original='[providers."managed:kimi-code"]\n[models."kimi-code/k3.1-pro"]\nprovider="managed:kimi-code"\nmodel="k3.1-pro"\n'
        config.write_text(original, encoding='utf-8')
        model={'provider':'managed:kimi-code','model':'k3.1-pro'}
        self.assertEqual(setup._append_model(config, ('kimi-code/k3.1-pro','k3.1-pro','managed:kimi-code'), model),'existing')
        self.assertEqual(config.read_text(encoding='utf-8'),original)

    def test_existing_model_with_different_capacity_or_capabilities_is_never_overwritten(self):
        config=self.base/'config.toml'
        original='[providers."managed:kimi-code"]\n[models."kimi-code/k3.1-pro"]\nprovider="managed:kimi-code"\nmodel="k3.1-pro"\nmax_context_size=1\n'
        config.write_text(original,encoding='utf-8')
        model={'provider':'managed:kimi-code','model':'k3.1-pro','max_context_size':1000000,'capabilities':['thinking']}
        with self.assertRaisesRegex(setup.SetupError,'不一致'):
            setup._append_model(config,('kimi-code/k3.1-pro','k3.1-pro','managed:kimi-code'),model)
        self.assertEqual(config.read_text(encoding='utf-8'),original)

    def test_existing_model_without_source_or_login_provenance_is_refused(self):
        config=self.base/'config.toml'
        config.write_text('[providers."managed:kimi-code"]\n[models."kimi-code/k3.1-pro"]\nprovider="managed:kimi-code"\nmodel="k3.1-pro"\n',encoding='utf-8')
        with self.assertRaisesRegex(setup.SetupError,'无法核对'):
            setup._append_model(config,('kimi-code/k3.1-pro','k3.1-pro','managed:kimi-code'),None)

    def test_invalid_structures_fail_with_fixed_error(self):
        pointer=self.root/'.talk/runtime.local.json'
        pointer.write_text(json.dumps({'schema':'talk-local-runtime-1','config_file':None,'database_file':str(self.dbpath)}),encoding='utf-8')
        with self.assertRaisesRegex(setup.SetupError,'不可用'):
            setup._local_facts(self.root,'prj_1','agent:one')
        config=self.base/'bad.toml';config.write_text('models = ["bad"]\n',encoding='utf-8')
        with self.assertRaisesRegex(setup.SetupError,'格式无效'):
            setup._public_model(config,('kimi-code/k3.1-pro','k3.1-pro','managed:kimi-code'))
        config.write_text('providers = []\nmodels = []\n',encoding='utf-8')
        with self.assertRaisesRegex(setup.SetupError,'未配置'):
            setup._append_model(config,('kimi-code/k3.1-pro','k3.1-pro','managed:kimi-code'),{})

    def test_main_handles_unexpected_structure_without_traceback(self):
        import io
        import contextlib
        with patch.object(setup,'setup',side_effect=TypeError('SENSITIVE')):
            stderr=io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(setup.main(['--project','p','--member','m']),1)
            self.assertNotIn('SENSITIVE',stderr.getvalue())
            self.assertNotIn('Traceback',stderr.getvalue())

    def test_unknown_model_metadata_is_not_silently_dropped(self):
        p=self.manual/'config.toml'
        with p.open('a',encoding='utf-8') as stream: stream.write('api_key = "NOT_FOR_COPY"\n')
        with self.assertRaisesRegex(setup.SetupError, '不支持自动准备'):
            setup._public_model(p,('kimi-code/k3.1-pro','k3.1-pro','managed:kimi-code'))

    def test_role_lookup_uses_actual_orm_schema(self):
        from sqlmodel import SQLModel, Session, create_engine
        from server.models import ProjectRole, ProjectRoleBinding, RunnerRegistry
        engine=create_engine('sqlite://')
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            session.add(RunnerRegistry(runner_id='r',runtime='kimi-code',display_name='Kimi',control_kind='managed_cli',created_by='human:test'))
            session.add(ProjectRole(project_id='p',member_id='agent:k',role_name='K',created_by='human:test'))
            session.add(ProjectRoleBinding(project_id='p',member_id='agent:k',runner_id='r',model_alias='kimi-code/k3.1-pro',model_id='k3.1-pro',provider_id='managed:kimi-code',model_source='builtin',connection_ref='native-kimi-code-managed-login',updated_by='human:test'))
            session.commit()
        with engine.connect() as connection:
            self.assertEqual(setup._role(connection.connection.driver_connection,'p','agent:k'),('kimi-code/k3.1-pro','k3.1-pro','managed:kimi-code'))
        engine.dispose()

    def test_host_blocks_missing_config_and_active_setup_lock(self):
        manager=object.__new__(kimi_role_host.KimiRoleHost)
        manager.project='prj_1'; manager.member='agent:one'; manager.display_name='X'; manager.task_profile='tools'
        manager.client=self.binding_client()
        home=self.base/'host-home'; home.mkdir()
        manager.store=type('Store',(),{'native_home_dir':lambda self,*args: home})()
        with self.assertRaisesRegex(kimi_role_host.rsh.HostError, 'Kimi登录'):
            manager.build_entry_argv('kimi-code','kimi-code/k3.1-pro')
        lock=kimi_role_host.rsh.lock_path_for(home/'kimi-role-setup')
        lock.write_text('locked')
        with self.assertRaisesRegex(kimi_role_host.rsh.HostError, '等待角色'):
            manager.build_entry_argv('kimi-code','kimi-code/k3.1-pro')

    def test_host_accepts_only_configured_model_and_preserves_profile(self):
        manager=object.__new__(kimi_role_host.KimiRoleHost)
        manager.project='prj_1'; manager.member='agent:one'; manager.display_name='X'; manager.task_profile='tools'
        manager.client=self.binding_client()
        manager.project_root=self.root
        home=self.base/'host-home'; home.mkdir()
        child=home/'.kimi-code'; child.mkdir()
        (child/'config.toml').write_text('[providers."managed:kimi-code"]\n[models."kimi-code/k3.1-pro"]\nprovider="managed:kimi-code"\nmodel="k3.1-pro"\n',encoding='utf-8')
        manager.store=type('Store',(),{'native_home_dir':lambda self,*args: home})()
        with patch.object(kimi_role_host.rsh.HostManager,'build_entry_argv',side_effect=lambda *args: (['bridge'],'template',60)):
            argv,_,_=manager.build_entry_argv('kimi-code','kimi-code/k3.1-pro')
        self.assertIn('--kimi-task-profile',argv)
        self.assertEqual(argv[argv.index('--kimi-task-profile')+1],'tools')
        with self.assertRaisesRegex(kimi_role_host.rsh.HostError,'绑定'):
            manager.build_entry_argv('kimi-code','kimi-code/missing')

    def test_untrusted_profile_file_cannot_override_runtime_config(self):
        manager=object.__new__(kimi_role_host.KimiRoleHost)
        manager.project='prj_1'; manager.member='agent:one'; manager.display_name='X'; manager.task_profile='review'
        manager.client=self.binding_client(); manager.project_root=self.root
        home=self.base/'host-home'; home.mkdir(); (home/'.kimi-code').mkdir()
        (home/'.kimi-code/config.toml').write_text('[providers."managed:kimi-code"]\n[models."kimi-code/k3.1-pro"]\nprovider="managed:kimi-code"\nmodel="k3.1-pro"\n',encoding='utf-8')
        manager.store=type('Store',(),{'native_home_dir':lambda self,*args: home})()
        manager.private=self.base/'manager'; manager.private.mkdir()
        selection=manager.private/'task-profile.json'
        selection.write_text(json.dumps({'schema':'talk-kimi-task-profile-1','project_id':'prj_1','member_id':'agent:one','profile':'tools'}),encoding='utf-8')
        with patch.object(kimi_role_host.rsh.HostManager,'build_entry_argv',side_effect=lambda *args: (['bridge'],'template',60)):
            argv,_,_=manager.build_entry_argv('kimi-code','kimi-code/k3.1-pro')
            self.assertEqual(argv[argv.index('--kimi-task-profile')+1],'review')
            selection.write_text(json.dumps({'schema':'talk-kimi-task-profile-1','project_id':'prj_1','member_id':'other','profile':'tools'}),encoding='utf-8')
            argv,_,_=manager.build_entry_argv('kimi-code','kimi-code/k3.1-pro')
            self.assertEqual(argv[argv.index('--kimi-task-profile')+1],'review')

    def test_provider_must_match_current_binding_before_building_entry(self):
        manager=object.__new__(kimi_role_host.KimiRoleHost)
        manager.project='prj_1';manager.member='agent:one';manager.client=self.binding_client()
        home=self.base/'host-home';home.mkdir();(home/'.kimi-code').mkdir()
        (home/'.kimi-code/config.toml').write_text('[providers.other]\n[models."kimi-code/k3.1-pro"]\nprovider="other"\nmodel="k3.1-pro"\n',encoding='utf-8')
        manager.store=type('Store',(),{'native_home_dir':lambda self,*args:home})()
        with patch.object(kimi_role_host.rsh.HostManager,'build_entry_argv') as build:
            with self.assertRaisesRegex(kimi_role_host.rsh.HostError,'Kimi登录'):
                manager.build_entry_argv('kimi-code','kimi-code/k3.1-pro')
            build.assert_not_called()

    def test_start_checks_actual_current_model_binding_each_time(self):
        manager=object.__new__(kimi_role_host.KimiRoleHost)
        home=self.base/'host-home'; home.mkdir(); (home/'.kimi-code').mkdir()
        config=home/'.kimi-code/config.toml'
        config.write_text('[models."kimi-code/k3.1-pro"]\nprovider="managed:kimi-code"\nmodel="k3.1-pro"\n',encoding='utf-8')
        manager.store=type('Store',(),{'native_home_dir':lambda self,*args: home})()
        role={'member_id':'agent:one','archived':False,'binding_state':'bound','model':{'model_alias':'kimi-code/k3.1-pro','model_id':'k3.1-pro'}}
        binding={'runtime':'kimi-code','model_alias':'kimi-code/k3.1-pro','model_id':'k3.1-pro','provider_id':'managed:kimi-code'}
        manager.client=type('Client',(),{'request':lambda self,method,path: {'data':[role]} if path.endswith('/roles') else {'data':[{'member_id':'agent:one','binding_state':'bound','binding':binding}]}})()
        command={'model_alias':'kimi-code/k3.1-pro'}
        with patch.object(kimi_role_host.rsh.HostManager,'preflight',return_value='base-facts'):
            self.assertEqual(manager.preflight(command,'agent:one',project_id='prj_1'),'base-facts')
            role['model']['model_id']='other'
            binding['model_id']='other'
            with self.assertRaisesRegex(kimi_role_host.rsh.HostError,'模型不一致'):
                manager.preflight(command,'agent:one',project_id='prj_1')
            config.write_text('[models."kimi-code/k3.1-pro"]\nprovider="managed:kimi-code"\nmodel="other"\n',encoding='utf-8')
            self.assertEqual(manager.preflight(command,'agent:one',project_id='prj_1'),'base-facts')

    def test_real_http_client_wraps_agent_list_and_detects_provider_mismatch(self):
        binding={'runtime':'kimi-code','model_alias':'kimi-code/k3.1-pro','model_id':'k3.1-pro','provider_id':'managed:kimi-code'}
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_GET(self):
                body=json.dumps([{'member_id':'agent:one','binding_state':'bound','binding':binding}]).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        manager=object.__new__(kimi_role_host.KimiRoleHost)
        manager.project='prj_1';manager.member='agent:one';manager.display_name='K';manager.task_profile='review';manager.project_root=self.root
        manager.client=kimi_role_host.rsh.TalkHostClient('http://127.0.0.1:'+str(server.server_port),'synthetic')
        home=self.base/'host-home';home.mkdir();(home/'.kimi-code').mkdir()
        cfg=home/'.kimi-code/config.toml'
        cfg.write_text('[providers."managed:kimi-code"]\n[models."kimi-code/k3.1-pro"]\nprovider="managed:kimi-code"\nmodel="k3.1-pro"\n',encoding='utf-8')
        manager.store=type('Store',(),{'native_home_dir':lambda self,*args:home})()
        with patch.object(kimi_role_host.rsh.HostManager,'build_entry_argv',side_effect=lambda *args:(['bridge'],'template',60)) as build:
            argv,_,_=manager.build_entry_argv('kimi-code','kimi-code/k3.1-pro')
            self.assertEqual(argv[argv.index('--kimi-task-profile')+1],'review')
            cfg.write_text('[providers.other]\n[models."kimi-code/k3.1-pro"]\nprovider="other"\nmodel="k3.1-pro"\n',encoding='utf-8')
            with self.assertRaisesRegex(kimi_role_host.rsh.HostError,'Kimi登录'):
                manager.build_entry_argv('kimi-code','kimi-code/k3.1-pro')
            self.assertEqual(build.call_count,1)


if __name__ == '__main__':
    unittest.main()

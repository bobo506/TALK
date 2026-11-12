"""Same-boot stale ownership: isolated SQLite, mocked OS process evidence."""
from datetime import timedelta
import socket
from unittest.mock import patch

from server import models as m, role_startup as startup
from scripts import role_service_recovery as local
from tests.test_role_services import RoleServiceTestCase, PROJECT_ID
from tests.test_project_roles import encode


class StaleStartupTests(RoleServiceTestCase):
    def setUp(self):
        super().setUp()
        self.health = {'pid': 123, 'started_at': (startup._now() + timedelta(hours=1)).isoformat()}
        self.cutoff = startup._now() - timedelta(seconds=30)
        self.runtime = patch.object(startup, 'verified_runtime',
            side_effect=lambda *a: ({'hosts': []}, self.health, self.cutoff))
        self.runtime.start()
        self.addCleanup(self.runtime.stop)

    def preference(self):
        with self.make_client() as client:
            response = client.put(f'/api/projects/{PROJECT_ID}/roles/{encode(self.role_a)}/startup',
                                  headers={'X-API-Key': 'bobo-key'}, json={'enabled': True})
        self.assertEqual(response.status_code, 200, response.text)

    def activate(self):
        with self.make_client() as client:
            response = client.post(f'/api/projects/{PROJECT_ID}/role-services/startup',
                headers={'X-API-Key': 'bobo-key'}, json={'activation_id': 'a'*32})
        self.assertEqual(response.status_code, 200, response.text)
        return next(x for x in response.json()['results'] if x['member_id'] == self.role_a)

    def running(self):
        host = socket.gethostname()
        launch, claim = self.start_and_claim(host=host)
        self.assertEqual(self.bind_instance(launch, claim, host=host).status_code, 200)
        self.assertEqual(self.ready_report(launch, claim, host=host,
                         process_started_at=startup._now().isoformat()).status_code, 200)
        return launch, claim

    def test_enabled_dead_same_boot_enqueues_generation_plus_one(self):
        self.preference(); launch, _ = self.running()
        self.cutoff = None
        with patch.object(local, 'recorded_process_state', return_value='absent'):
            result = self.activate()
        self.assertEqual((result['status'], result['error_code']), ('enqueued', 'startup_stale_recovered'))
        self.assertEqual(self.state_row().generation, launch['generation'] + 1)
        self.assertEqual(self.state_row().observed_state, 'starting')
        self.assertEqual(len(self.launch_rows()), 2)

    def test_disabled_dead_is_skipped_and_preserves_desired(self):
        self.running()
        with patch.object(local, 'recorded_process_state', return_value='exited'):
            result = self.activate()
        self.assertEqual((result['status'], result['error_code']), ('skipped', 'startup_not_selected'))
        self.assertEqual((self.state_row().desired_state, self.state_row().observed_state), ('running', 'stopped'))
        self.assertEqual(len(self.launch_rows()), 1)

    def test_present_start_all_skips_without_new_launch(self):
        self.running()
        with patch.object(local, 'recorded_process_state', return_value='present'):
            response = self.start_all()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['results'][0]['status'], 'skipped_running')
        self.assertEqual(len(self.launch_rows()), 1)

    def test_dead_start_all_enqueues(self):
        self.running()
        with patch.object(local, 'recorded_process_state', return_value='absent'):
            response = self.start_all()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['results'][0]['status'], 'requested')
        self.assertEqual(len(self.launch_rows()), 2)

    def test_dead_direct_start_enqueues(self):
        launch, _ = self.running()
        with patch.object(local, 'recorded_process_state', return_value='absent'):
            response = self.start()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['generation'], launch['generation'] + 1)
        self.assertEqual(len(self.launch_rows()), 2)

    def test_manager_update_is_not_manual_and_retained_human_actor_is_not_timestamp(self):
        self.preference(); self.running()
        self.health['started_at'] = startup._now().isoformat()
        with self.session() as session:
            state = session.get(m.RoleServiceState, (PROJECT_ID, self.role_a))
            state.updated_by = 'system:manager'; state.updated_at = startup._now()
            session.add(state); session.commit()
        with patch.object(local, 'recorded_process_state', return_value='absent'):
            self.assertEqual(self.activate()['status'], 'enqueued')

    def test_observed_update_retaining_human_actor_is_not_manual(self):
        self.preference(); self.running()
        self.health['started_at'] = startup._now().isoformat()
        with self.session() as session:
            state = session.get(m.RoleServiceState, (PROJECT_ID, self.role_a))
            self.assertEqual(state.updated_by, 'human:bobo')
            state.updated_at = startup._now(); session.add(state); session.commit()
        with patch.object(local, 'recorded_process_state', return_value='absent'):
            self.assertEqual(self.activate()['status'], 'enqueued')

    def test_nonlocal_and_mismatched_instance_never_release(self):
        launch, claim = self.running()
        with self.session() as session:
            state = session.get(m.RoleServiceState, (PROJECT_ID, self.role_a))
            state.owner_host = 'remote-host'; session.add(state); session.commit()
        with patch.object(local, 'recorded_process_state', return_value='absent'):
            response = self.start_all()
        self.assertEqual(response.json()['results'][0]['status'], 'skipped_running')
        with self.session() as session:
            state = session.get(m.RoleServiceState, (PROJECT_ID, self.role_a))
            state.owner_host = socket.gethostname(); session.add(state)
            instance = session.get(m.AgentInstance, claim['expected_instance_id'])
            instance.pid = 999; session.add(instance); session.commit()
        with patch.object(local, 'recorded_process_state', return_value='absent'):
            response = self.start_all()
        self.assertEqual(response.json()['results'][0]['status'], 'failed')
        self.assertEqual(self.state_row().process_launch_id, launch['launch_id'])
        self.assertEqual(len(self.launch_rows()), 1)

    def test_busy_instance_never_releases(self):
        launch, claim = self.running()
        with self.session() as session:
            instance = session.get(m.AgentInstance, claim['expected_instance_id'])
            instance.status = 'busy'; session.add(instance); session.commit()
        with patch.object(local, 'recorded_process_state', return_value='absent'):
            response = self.start_all()
        self.assertEqual(response.json()['results'][0]['error_code'], 'recovery_tasks_active')
        self.assertEqual(self.state_row().process_launch_id, launch['launch_id'])

    def test_queued_work_and_residual_claims_never_release(self):
        launch, _ = self.running()
        with self.session() as session:
            task = m.AgentTask(target_member_id=self.role_a, created_by='human:bobo',
                               content='fixture', project_id=PROJECT_ID, status='queued')
            session.add(task); session.commit()
        with patch.object(local, 'recorded_process_state', return_value='absent'):
            response = self.start_all()
        self.assertEqual(response.json()['results'][0]['error_code'], 'recovery_tasks_active')
        self.assertEqual(self.state_row().process_launch_id, launch['launch_id'])

    def test_changed_process_evidence_rolls_back(self):
        launch, _ = self.running()
        with patch.object(local, 'recorded_process_state', side_effect=['absent', 'present']):
            response = self.start_all()
        self.assertEqual(response.json()['results'][0]['error_code'], 'recovery_process_unverified')
        self.assertEqual(self.state_row().process_launch_id, launch['launch_id'])
        self.assertEqual(len(self.launch_rows()), 1)

    def test_missing_current_launch_is_safe_if_generation_and_owner_match(self):
        self.running()
        with self.session() as session:
            state = session.get(m.RoleServiceState, (PROJECT_ID, self.role_a))
            state.current_launch_id = None; session.add(state); session.commit()
        with patch.object(local, 'recorded_process_state', return_value='absent'):
            response = self.start_all()
        self.assertEqual(response.json()['results'][0]['status'], 'requested')
        self.assertEqual(len(self.launch_rows()), 2)

    def test_auto_failed_convergence_retaining_human_actor_is_not_manual(self):
        self.preference()
        launch = self.start().json()
        self.health['started_at'] = startup._now().isoformat()
        with self.session() as session:
            state = session.get(m.RoleServiceState, (PROJECT_ID, self.role_a))
            state.desired_state = 'stopped'; state.observed_state = 'failed'
            state.last_result = 'failed'; state.current_launch_id = None
            state.updated_at = startup._now(); session.add(state)
            action = session.get(m.RoleServiceLaunch, launch['launch_id'])
            action.state = 'expired'; session.add(action); session.commit()
        self.assertEqual(self.activate()['status'], 'enqueued')

    def test_active_launch_never_releases(self):
        launch, _ = self.running()
        with self.session() as session:
            action = session.get(m.RoleServiceLaunch, launch['launch_id'])
            action.state = 'claimed'; session.add(action); session.commit()
        with patch.object(local, 'recorded_process_state', return_value='absent'):
            response = self.start_all()
        self.assertEqual(response.json()['results'][0]['error_code'], 'recovery_action_active')
        self.assertEqual(self.state_row().process_launch_id, launch['launch_id'])

    def test_instance_start_time_mismatch_is_rejected(self):
        launch, claim = self.running()
        with self.session() as session:
            state = session.get(m.RoleServiceState, (PROJECT_ID, self.role_a))
            instance = session.get(m.AgentInstance, claim['expected_instance_id'])
            instance.process_started_at = state.process_started_at + timedelta(minutes=1)
            session.add(instance); session.commit()
        with patch.object(local, 'recorded_process_state', return_value='absent'):
            response = self.start_all()
        self.assertEqual(response.json()['results'][0]['error_code'], 'recovery_identity_mismatch')
        self.assertEqual(self.state_row().process_launch_id, launch['launch_id'])

    def test_dead_starting_is_restarted(self):
        self.running()
        with self.session() as session:
            state = session.get(m.RoleServiceState, (PROJECT_ID, self.role_a))
            state.observed_state = 'starting'; session.add(state); session.commit()
        with patch.object(local, 'recorded_process_state', return_value='absent'):
            response = self.start_all()
        self.assertEqual(response.json()['results'][0]['status'], 'requested')
        self.assertEqual(len(self.launch_rows()), 2)

    def test_dead_stopping_is_restarted(self):
        self.running()
        with self.session() as session:
            state = session.get(m.RoleServiceState, (PROJECT_ID, self.role_a))
            state.observed_state = 'stopping'; session.add(state); session.commit()
        with patch.object(local, 'recorded_process_state', return_value='absent'):
            response = self.start_all()
        self.assertEqual(response.json()['results'][0]['status'], 'requested')
        self.assertEqual(len(self.launch_rows()), 2)

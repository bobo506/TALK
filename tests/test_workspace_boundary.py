from tests.test_support import RouteTestCase
from server.models import Project, ProjectAgent


class WorkspaceBoundaryTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.add_member('human:test', api_key='human')
        self.add_member('agent:a', api_key='a')
        self.add_member('agent:b', api_key='b')
        with self.session() as session:
            for project in ('p1', 'p2'):
                session.add(Project(project_id=project, display_name=project, maintainer_member_id='human:test'))
            session.add(ProjectAgent(project_id='p1', member_id='agent:a'))
            session.add(ProjectAgent(project_id='p2', member_id='agent:b'))
            session.commit()

    def test_task_group_and_schedule_require_project_and_schedule_materializes(self):
        h = {'X-API-Key': 'human'}
        with self.make_client() as c:
            task = {'target_member_id': 'agent:a', 'content': 'work'}
            self.assertEqual(c.post('/api/tasks', headers=h, json=task).status_code, 422)
            r = c.post('/api/tasks', headers=h, json={**task, 'project_id': 'p1'})
            self.assertEqual(r.status_code, 201, r.text)
            self.assertEqual(r.json()['project_id'], 'p1')
            group = {'name': 'one'}
            self.assertEqual(c.post('/api/groups', headers=h, json=group).status_code, 422)
            self.assertEqual(c.post('/api/groups', headers=h, json={**group, 'project_id': 'p1'}).status_code, 201)
            self.assertEqual(c.post('/api/groups', headers=h, json={'name':'two', 'project_id':'p2'}).status_code, 201)
            groups = c.get('/api/groups', headers=h, params={'project_id':'p1'}).json()
            self.assertTrue(groups)
            self.assertTrue(all(g['project_id'] == 'p1' for g in groups))
            self.assertEqual(c.post('/api/tasks/schedules', headers=h, json=task).status_code, 422)
            r = c.post('/api/tasks/schedules', headers=h, json={**task, 'project_id':'p1'})
            self.assertEqual(r.status_code, 201, r.text)
            r = c.post('/api/tasks/schedules/run-due', headers=h)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()['created_tasks'][0]['project_id'], 'p1')

    def test_file_project_access(self):
        with self.make_client() as c:
            f = {'file': ('x.txt', b'hello', 'text/plain')}
            self.assertEqual(c.post('/api/files', headers={'X-API-Key':'human'}, files=f).status_code, 422)
            self.assertEqual(c.post('/api/files', headers={'X-API-Key':'b'}, files=f, data={'project_id':'p1'}).status_code, 403)
            r = c.post('/api/files', headers={'X-API-Key':'a'}, files=f, data={'project_id':'p1'})
            self.assertEqual(r.status_code, 201, r.text)
            url = '/api/files/' + r.json()['file_id']
            self.assertEqual(c.get(url, headers={'X-API-Key':'b'}).status_code, 403)
            self.assertEqual(c.get(url, headers={'X-API-Key':'a'}).content, b'hello')
            self.assertEqual(c.get(url, headers={'X-API-Key':'human'}).content, b'hello')

    def test_schema_migration_is_repeatable(self):
        import server.db as db
        with self.engine.begin() as conn:
            for table in ('files', 'agent_task_schedules'):
                sql = conn.exec_driver_sql("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).scalar_one()
                sql = sql.replace('project_id VARCHAR,', '').replace('FOREIGN KEY(project_id) REFERENCES projects (project_id),', '')
                conn.exec_driver_sql(f'DROP TABLE {table}')
                conn.exec_driver_sql(sql)
        db.init_db()
        db.init_db()
        with self.engine.connect() as conn:
            for table in ('files', 'agent_task_schedules'):
                columns = {row[1] for row in conn.exec_driver_sql(f'PRAGMA table_info({table})')}
                indexes = {row[1] for row in conn.exec_driver_sql(f'PRAGMA index_list({table})')}
                self.assertIn('project_id', columns)
                self.assertIn(f'ix_{table}_project_id', indexes)

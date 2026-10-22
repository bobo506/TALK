"""Project names survive member re-registration and stay isolated across projects."""
from sqlmodel import select
from server.models import Member, ProjectRole
from tests.test_project_roles import RoleApiTestCase


class ProjectRoleNameTests(RoleApiTestCase):
    def test_creation_and_rename_are_authoritative_in_actual_roster_response(self):
        self.register_project()
        choice = self.seed_runner_and_choice()
        made = self.create_role('prj_alpha', role_name='WorkBuddy-k3', choice_id=choice,
                                operation_key='name-create-case').json()
        member = made['member_id']
        with self.make_client() as client:
            url = '/api/projects/prj_alpha/agents'
            row = next(r for r in client.get(url, headers={'X-API-Key':'bobo-key'}).json() if r['member_id']==member)
            self.assertEqual(row['role_name'], 'WorkBuddy-k3')
            changed = self.patch_role('prj_alpha', member, {'role_name':'项目审查助手'})
            self.assertEqual(changed.status_code, 200)
            row = next(r for r in client.get(url, headers={'X-API-Key':'bobo-key'}).json() if r['member_id']==member)
            self.assertEqual(row['role_name'], '项目审查助手')
            self.assertEqual(row['display_name'], 'WorkBuddy-k3')
        with self.session() as session:
            self.assertEqual(session.get(Member, member).display_name, 'WorkBuddy-k3')

    def test_same_global_member_has_separate_project_names(self):
        for project in ['prj_alpha','prj_beta']:
            self.register_project(project)
            self.sync_roster(project, [{'member_id':'agent:worker'}])
        with self.session() as session:
            for project, name in [('prj_alpha','WorkBuddy-k3'),('prj_beta','另一项目的名称')]:
                session.add(ProjectRole(project_id=project, member_id='agent:worker', role_name=name,
                                        origin='imported', created_by='human:bobo'))
            session.commit()
        with self.make_client() as client:
            for project, name in [('prj_alpha','WorkBuddy-k3'),('prj_beta','另一项目的名称')]:
                rows=client.get(f'/api/projects/{project}/agents',headers={'X-API-Key':'bobo-key'}).json()
                self.assertEqual(rows[0]['role_name'],name)

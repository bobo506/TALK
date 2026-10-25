"""Real roster DTO -> actual page loader/control; all API data is synthetic."""
import json
from pathlib import Path
import shutil
import subprocess
from sqlmodel import select
from server import models as m
from tests.test_role_services import RoleServiceTestCase,PROJECT_ID,OTHER_PROJECT_ID
from tests.test_project_roles import encode

class StartupRosterTests(RoleServiceTestCase):
    def agents(self,project=PROJECT_ID):
        with self.make_client() as client:
            response=client.get(f'/api/projects/{project}/agents',headers={'X-API-Key':'bobo-key'})
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def render(self,agents):
        root=Path(__file__).resolve().parents[1]
        result=subprocess.run([shutil.which('node') or 'node',str(root/'tests/role_startup_roster_render.cjs')],
            cwd=root,input=json.dumps({'project':PROJECT_ID,'member':self.role_a,'agents':agents}),
            text=True,encoding='utf8',capture_output=True,timeout=20,check=True)
        return json.loads(result.stdout)

    def preference(self,enabled):
        with self.make_client() as client:
            response=client.put(f'/api/projects/{PROJECT_ID}/roles/{encode(self.role_a)}/startup',
                headers={'X-API-Key':'bobo-key'},json={'enabled':enabled})
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def test_real_roster_loader_renders_default_and_saved_values_without_starting(self):
        for enabled,revision in ((False,0),(True,1),(False,2)):
            if revision:self.preference(enabled)
            rows=self.agents();rendered=self.render(rows)
            self.assertTrue(rendered['visible'],'actual page loader hides the control for GET /agents data')
            self.assertEqual(rendered['checked'],enabled)
            self.assertIn('随项目自动启动',rendered['text'])
            self.assertEqual(rendered['requests'],[f'/api/projects/{PROJECT_ID}/agents'])
            startup=next(r for r in rows if r['member_id']==self.role_a)['startup']
            self.assertEqual((startup['enabled'],startup['revision']),(enabled,revision))
            role=next(r for r in self.get_roles().json() if r['member_id']==self.role_a)
            self.assertEqual(startup,role['startup'])
        self.assertEqual(self.launch_rows(),[])
        with self.session() as session:
            self.assertEqual(session.exec(select(m.RoleStartupActivation)).all(),[])
            self.assertEqual(session.exec(select(m.ProjectStartupCycle)).all(),[])

    def test_roster_audit_matches_roles_and_is_scoped_read_only(self):
        self.preference(True);self.register_project(OTHER_PROJECT_ID)
        with self.session() as session:
            session.add(m.ProjectAgent(project_id=OTHER_PROJECT_ID,member_id=self.role_a))
            audit=m.RoleStartupActivation(project_id=PROJECT_ID,activation_id='a'*32,
                member_id=self.role_a,enabled=True,preference_revision=1,expected_generation=0,
                status='failed',error_code='synthetic_failure',lease_hash='must-not-be-public')
            session.add(audit);session.commit();session.refresh(audit)
            before=audit.model_dump()
        row=next(r for r in self.agents() if r['member_id']==self.role_a)
        self.assertIsInstance(row.get('startup'),dict)
        role=next(r for r in self.get_roles().json() if r['member_id']==self.role_a)
        self.assertEqual(row['startup'],role['startup'])
        self.assertEqual(set(row['startup']),{'enabled','revision','updated_at','last_activation'})
        self.assertEqual(set(row['startup']['last_activation']),{'status','error_code','launch_id','updated_at'})
        self.assertNotIn('must-not-be-public',json.dumps(row))
        other=next(r for r in self.agents(OTHER_PROJECT_ID) if r['member_id']==self.role_a)
        self.assertEqual(other['startup'],{'enabled':False,'revision':0,'updated_at':None,'last_activation':None})
        with self.session() as session:
            self.assertEqual(session.get(m.RoleStartupActivation,(PROJECT_ID,'a'*32,self.role_a)).model_dump(),before)
            self.assertIsNone(session.get(m.ProjectRoleStartup,(OTHER_PROJECT_ID,self.role_a)))
        self.assertEqual(self.launch_rows(),[])

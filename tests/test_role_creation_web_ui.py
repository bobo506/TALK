"""创建配置页面的真实静态路由、HTML绑定和资源声明。"""
from pathlib import Path
from html.parser import HTMLParser
from tests.test_support import RouteTestCase

ROOT=Path(__file__).resolve().parents[1]

class IdParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids=[]
        self.assets=[]
    def handle_starttag(self,tag,attrs):
        values=dict(attrs)
        if 'id' in values:
            self.ids.append(values['id'])
        if tag=='script' and values.get('src','').startswith('/'):
            self.assets.append(values['src'])
        if tag=='link' and values.get('href','').startswith('/'):
            self.assets.append(values['href'])

class RoleCreationWebUiTests(RouteTestCase):
    def test_resources_and_html_are_served_and_bound_once(self):
        with self.make_client() as client:
            response=client.get('/')
            self.assertEqual(response.status_code,200)
            parser=IdParser();parser.feed(response.text)
            self.assertEqual(len(parser.ids),len(set(parser.ids)))
            for target in ['role-create-modal','role-create-form','role-create-runner','role-create-model','role-create-name','role-create-description','role-create-submit','role-request-list','role-request-host-panel']:
                self.assertIn(target,parser.ids)
            asset_paths=[asset.split('?',1)[0] for asset in parser.assets]
            self.assertEqual(len(asset_paths),len(set(asset_paths)))
            self.assertTrue(all('?v=' in asset for asset in parser.assets))
            scripts=[path for path in asset_paths if path.endswith('.js')]
            required=['/role-creation.js','/workspace.js','/app.js']
            self.assertTrue(all(path in scripts for path in required))
            self.assertEqual([scripts.index(path) for path in required],sorted(scripts.index(path) for path in required))
            self.assertIn('/role-creation.js?v=20261028-role-create-dialog-v1',parser.assets)
            self.assertIn('/workspace.js?v=20261028-role-list-select-v1',parser.assets)
            self.assertIn('role-create-auto-start',parser.ids)
            for asset in ['/role-creation.js','/role-creation.css']:
                self.assertEqual(client.get(asset).status_code,200)

    def test_creation_dialog_has_native_labels_and_accessibility(self):
        html=(ROOT/'web/index.html').read_text(encoding='utf-8')
        self.assertIn('aria-labelledby="role-create-title"',html)
        self.assertIn('aria-modal="true"',html)
        for field in ['role-create-runner','role-create-model','role-create-name']:
            self.assertRegex(html,rf'id="{field}"[^>]*required')
        self.assertNotIn('onclick=',html)

    def test_creation_dialog_select_height_follows_content(self):
        # 2026-10-28：.group-member-select 的 38px 定高减去 10px 上下内边距和边框后只剩 16px 内容区，
        # 15px 字的行盒放不下，默认提示「选择运行器」上下笔画会被裁掉；下拉必须随内容高度。
        css=(ROOT/'web/role-creation.css').read_text(encoding='utf-8')
        self.assertRegex(css,r'\.role-create-dialog \.role-request-field select \{height:auto;\}')
        self.assertRegex(css,r'\.role-request-field input,\.role-request-field select,\.role-request-field textarea \{[^}]*padding:10px 12px;')

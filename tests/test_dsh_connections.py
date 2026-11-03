import unittest

from scripts import dsh_connections as dsh


class DshConnectionsTest(unittest.TestCase):
    def setUp(self):
        self.binding = dict(runner_id='runner:dsh', runtime='dsh', model_source='registry',
            provider_id='provider', connection_ref='conn', model_id='model-id', model_alias='alias')
        self.entry = dict(self.binding, auth_type='api_key', api_key_env='TALK_DSH_CONNECTION_X_API_KEY',
            target_api_key_env='DEEPSEEK_API_KEY', command_template='dsh --model {model} --id {model_id}',
            tools_command_template='dsh --tools --model {model} --id {model_id}')
        self.config = {'dsh': {'enabled': True, 'connections': {'conn': self.entry}}}

    def test_profiles_and_provider_variable(self):
        entry = dsh.resolve_connection(self.config, self.binding)
        dsh.validate_dsh_config(self.config)
        for profile in dsh.PROFILES:
            self.assertIn('alias', dsh.validate_command(entry, self.binding, profile, which=lambda _: True))
        self.assertEqual(dsh.connection_environment(entry, {'TALK_DSH_CONNECTION_X_API_KEY': 'synthetic'}),
                         {'DEEPSEEK_API_KEY': 'synthetic'})

    def test_reserved_identity(self):
        for target in ('TALK_API_KEY', 'TALK_OTHER_API_KEY'):
            with self.subTest(target=target):
                self.entry['target_api_key_env'] = target
                with self.assertRaises(dsh.ConnectionSetupError):
                    dsh.resolve_connection(self.config, self.binding)

    def test_credentials_in_both_profiles(self):
        for field in ('command_template', 'tools_command_template'):
            original = self.entry[field]
            for flag in ('--api-key=anything', '--key value', '--token value', '--authorization value',
                         '-H Authorization:abc', '-H Authorization', '--header=Authorization:abc'):
                with self.subTest(field=field, flag=flag):
                    self.entry[field] = original + ' ' + flag
                    with self.assertRaises(dsh.ConnectionSetupError):
                        dsh.resolve_connection(self.config, self.binding)
            self.entry[field] = original
        for profile in dsh.PROFILES:
            with self.assertRaises(dsh.ConnectionSetupError):
                dsh.validate_command(self.entry, self.binding, profile, which=lambda _: True, secret='alias')

    def test_missing_and_mismatch(self):
        with self.assertRaises(dsh.ConnectionSetupError):
            dsh.resolve_connection(self.config, dict(self.binding, model_id='wrong'))
        with self.assertRaises(dsh.ConnectionSetupError):
            dsh.connection_environment(self.entry, {})
        del self.entry['tools_command_template']
        with self.assertRaises(dsh.ConnectionSetupError):
            dsh.validate_command(self.entry, self.binding, 'tools', which=lambda _: True)

    def test_template_and_config_are_fail_closed(self):
        for template in ('dsh --model {model}', 'dsh {model!r} {model_id}',
                         'dsh {model} {model_id} {secret}'):
            self.entry['tools_command_template'] = template
            with self.subTest(template=template), self.assertRaises(dsh.ConnectionSetupError):
                dsh.resolve_connection(self.config, self.binding)
        self.entry['tools_command_template'] = 'dsh {model} {model_id}'
        self.config['dsh']['connections'] = {'other': self.entry}
        with self.assertRaises(dsh.ConnectionSetupError):
            dsh.validate_dsh_config(self.config)


if __name__ == '__main__':
    unittest.main()

"""Staging must fail closed before any provider request or database write."""
import unittest
from unittest.mock import patch

from app import create_app
from app.services import mpesa


class StagingConfigurationTests(unittest.TestCase):
    def test_staging_rejects_live_mpesa_at_startup(self):
        with patch.dict('os.environ', {'APP_ENV': 'staging', 'MPESA_ENV': 'production'}, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'sandbox'):
                create_app()

    def test_staging_requires_hosted_security_configuration(self):
        with patch.dict('os.environ', {'APP_ENV': 'staging', 'MPESA_ENV': 'sandbox'}, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'DATABASE_URL'):
                create_app()

    def test_staging_worker_cannot_switch_to_live_provider(self):
        with patch.dict('os.environ', {'APP_ENV': 'staging', 'MPESA_ENV': 'production'}, clear=True):
            with patch.object(mpesa, '_json_request') as network:
                with self.assertRaisesRegex(mpesa.MpesaConfigurationError, 'sandbox'):
                    mpesa.get_access_token()
                network.assert_not_called()

    def test_staging_factory_starts_without_initializer(self):
        env = {'APP_ENV': 'staging', 'MPESA_ENV': 'sandbox',
               'DATABASE_URL': 'postgresql://localhost/isolated_staging',
               'SECRET_KEY': 'disposable-staging-test-secret', 'FLASK_HTTPS': '1',
               'FRONTEND_URL': 'https://staging.example.invalid'}
        with patch.dict('os.environ', env, clear=True):
            with patch('app.db.get_db') as database:
                app = create_app()
                database.assert_not_called()
                self.assertTrue(app.config['SESSION_COOKIE_SECURE'])
                self.assertEqual(app.config['SESSION_COOKIE_SAMESITE'], 'None')

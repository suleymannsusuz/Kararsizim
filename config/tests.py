import json
import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

BASE_DIR = Path(__file__).resolve().parent.parent

PROBE = """
import json
from django.conf import settings as s
print(json.dumps({
    "hosts": s.ALLOWED_HOSTS,
    "csrf": s.CSRF_TRUSTED_ORIGINS,
    "ssl_redirect": s.SECURE_SSL_REDIRECT,
    "session_secure": s.SESSION_COOKIE_SECURE,
    "csrf_secure": s.CSRF_COOKIE_SECURE,
    "hsts": s.SECURE_HSTS_SECONDS,
    "proxy_header": s.SECURE_PROXY_SSL_HEADER,
}))
"""


def load_settings(**overrides):
    """Ayarları temiz bir süreçte, verilen ortam değişkenleriyle yükler (yerel .env'den etkilenmez)."""
    env = os.environ.copy()
    env.update(
        DJANGO_SETTINGS_MODULE="config.settings",
        DJANGO_SECRET_KEY="test-icin-uzun-ve-rastgele-bir-anahtar-0123456789",
        DJANGO_DEBUG="False",
        DJANGO_ALLOWED_HOSTS="",
        DJANGO_CSRF_TRUSTED_ORIGINS="",
        DATABASE_URL="",
        VERCEL="",
        VERCEL_PROJECT_PRODUCTION_URL="",
        VERCEL_URL="",
        VERCEL_BRANCH_URL="",
        DJANGO_SECURE="",
    )
    env.update(overrides)
    # Boş değerler "tanımlı ama boş" kalır; python-dotenv .env'den üzerine yazmaz.
    result = subprocess.run(
        [sys.executable, "-c", "import django; django.setup()\n" + PROBE],
        cwd=BASE_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


class VercelSettingsTests(SimpleTestCase):
    def test_vercel_hosts_and_csrf_origins_come_from_system_variables(self):
        s = load_settings(
            VERCEL="1",
            VERCEL_PROJECT_PRODUCTION_URL="kararsizim.vercel.app",
            VERCEL_URL="kararsizim-abc123.vercel.app",
            VERCEL_BRANCH_URL="kararsizim-git-main.vercel.app",
        )
        self.assertEqual(
            s["hosts"], ["kararsizim.vercel.app", "kararsizim-abc123.vercel.app", "kararsizim-git-main.vercel.app"]
        )
        self.assertEqual(
            s["csrf"],
            [
                "https://kararsizim.vercel.app",
                "https://kararsizim-abc123.vercel.app",
                "https://kararsizim-git-main.vercel.app",
            ],
        )

    def test_custom_domain_can_be_added_next_to_vercel_hosts(self):
        s = load_settings(
            VERCEL="1",
            VERCEL_PROJECT_PRODUCTION_URL="kararsizim.vercel.app",
            DJANGO_ALLOWED_HOSTS="kararsizim.com",
            DJANGO_CSRF_TRUSTED_ORIGINS="https://kararsizim.com",
        )
        self.assertEqual(s["hosts"], ["kararsizim.com", "kararsizim.vercel.app"])
        self.assertEqual(s["csrf"], ["https://kararsizim.com", "https://kararsizim.vercel.app"])

    def test_vercel_enables_production_security(self):
        s = load_settings(VERCEL="1", VERCEL_URL="x.vercel.app")
        self.assertTrue(s["ssl_redirect"])
        self.assertTrue(s["session_secure"])
        self.assertTrue(s["csrf_secure"])
        self.assertEqual(s["hsts"], 31536000)
        self.assertEqual(s["proxy_header"], ["HTTP_X_FORWARDED_PROTO", "https"])

    def test_local_debug_false_keeps_http_usable(self):
        s = load_settings()
        self.assertFalse(s["ssl_redirect"])
        self.assertFalse(s["session_secure"])
        self.assertFalse(s["csrf_secure"])
        self.assertEqual(s["hsts"], 0)
        self.assertIsNone(s["proxy_header"])
        self.assertEqual(s["hosts"], [])

    def test_security_can_be_forced_on_other_hosts(self):
        s = load_settings(DJANGO_SECURE="True", DJANGO_ALLOWED_HOSTS="kararsizim.example")
        self.assertTrue(s["ssl_redirect"])
        self.assertEqual(s["hosts"], ["kararsizim.example"])

    def test_debug_never_turns_on_production_security(self):
        s = load_settings(VERCEL="1", DJANGO_DEBUG="True")
        self.assertFalse(s["ssl_redirect"])
        self.assertFalse(s["session_secure"])

    def test_secret_key_is_required_without_debug(self):
        env = os.environ.copy()
        env.update(DJANGO_SETTINGS_MODULE="config.settings", DJANGO_DEBUG="False", DJANGO_SECRET_KEY="", DATABASE_URL="")
        result = subprocess.run(
            [sys.executable, "-c", "import django; django.setup()"],
            cwd=BASE_DIR, env=env, capture_output=True, text=True, timeout=60,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY", result.stderr)

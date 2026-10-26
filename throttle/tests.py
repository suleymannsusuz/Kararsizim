from datetime import timedelta
from unittest import mock

from django.db import DatabaseError
from django.test import TestCase, override_settings
from django.utils import timezone

from .middleware import RULES, client_ip, hit_key
from .models import RateLimitHit

IP_A = "203.0.113.10"
IP_B = "203.0.113.11"

VOTE_URL = "/anket/1/oy/"  # anket olmasa da kural yola bakar; 404 dönmesi sorun değil
LOGIN_URL = "/giris/"
REGISTER_URL = "/kayit/"


def rule(scope):
    return next(item for item in RULES if item.scope == scope)


@override_settings(THROTTLE_ENABLED=True)
class ThrottleTests(TestCase):
    def post(self, url, ip=IP_A, **extra):
        return self.client.post(url, {}, REMOTE_ADDR=ip, **extra)

    def test_vote_limit_is_enforced_per_ip(self):
        limit = rule("vote").limit
        for _ in range(limit):
            self.assertNotEqual(self.post(VOTE_URL).status_code, 429)
        response = self.post(VOTE_URL)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response["Retry-After"], str(rule("vote").window))
        self.assertContains(response, "Biraz yavaşla", status_code=429)
        self.assertNotEqual(self.post(VOTE_URL, ip=IP_B).status_code, 429)

    def test_login_admin_login_and_register_have_their_own_limits(self):
        for url, scope in ((LOGIN_URL, "login"), ("/yonetim/login/", "login"), (REGISTER_URL, "register")):
            RateLimitHit.objects.all().delete()
            with self.subTest(url=url):
                for _ in range(rule(scope).limit):
                    self.assertNotEqual(self.post(url).status_code, 429)
                self.assertEqual(self.post(url).status_code, 429)

    def test_scopes_are_independent(self):
        for _ in range(rule("register").limit + 1):
            self.post(REGISTER_URL)
        self.assertEqual(self.post(REGISTER_URL).status_code, 429)
        self.assertNotEqual(self.post(LOGIN_URL).status_code, 429)
        self.assertNotEqual(self.post(VOTE_URL).status_code, 429)

    def test_json_request_gets_json_error(self):
        for _ in range(rule("vote").limit):
            self.post(VOTE_URL)
        response = self.post(VOTE_URL, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["ok"], False)
        self.assertIn("Çok fazla istek", response.json()["error"])

    def test_get_requests_are_never_counted(self):
        for _ in range(60):
            self.assertEqual(self.client.get(LOGIN_URL, REMOTE_ADDR=IP_A).status_code, 200)
        self.assertEqual(RateLimitHit.objects.count(), 0)

    def test_hits_outside_the_window_do_not_count(self):
        for _ in range(rule("register").limit):
            self.post(REGISTER_URL)
        self.assertEqual(self.post(REGISTER_URL).status_code, 429)
        RateLimitHit.objects.update(created_at=timezone.now() - timedelta(seconds=rule("register").window + 1))
        self.assertNotEqual(self.post(REGISTER_URL).status_code, 429)

    def test_ip_is_stored_only_as_a_keyed_hash(self):
        self.post(LOGIN_URL)
        hit = RateLimitHit.objects.get()
        self.assertEqual(hit.key, hit_key("login", IP_A))
        self.assertEqual(len(hit.key), 64)
        self.assertNotIn(IP_A, hit.key)
        self.assertNotEqual(hit_key("login", IP_A), hit_key("vote", IP_A))

    def test_forwarded_header_is_trusted_only_on_vercel(self):
        forwarded = {"HTTP_X_FORWARDED_FOR": f"{IP_B}, 10.0.0.1"}
        request = mock.Mock(META={"REMOTE_ADDR": IP_A, **forwarded})
        with override_settings(ON_VERCEL=False):
            self.assertEqual(client_ip(request), IP_A)
        with override_settings(ON_VERCEL=True):
            self.assertEqual(client_ip(request), IP_B)
        request = mock.Mock(META={"REMOTE_ADDR": IP_A})
        with override_settings(ON_VERCEL=True):
            self.assertEqual(client_ip(request), IP_A)

    @override_settings(ON_VERCEL=False)
    def test_spoofed_forwarded_header_does_not_bypass_limit(self):
        for number in range(rule("login").limit):
            self.post(LOGIN_URL, HTTP_X_FORWARDED_FOR=f"198.51.100.{number}")
        self.assertEqual(self.post(LOGIN_URL, HTTP_X_FORWARDED_FOR="198.51.100.200").status_code, 429)

    def test_database_error_lets_the_request_through(self):
        broken = mock.MagicMock()
        broken.objects.filter.side_effect = DatabaseError("tablo yok")
        with mock.patch("throttle.middleware.RateLimitHit", broken):
            with self.assertLogs("throttle.middleware", level="ERROR"):
                response = self.post(LOGIN_URL)
        self.assertEqual(response.status_code, 200)

    def test_old_hits_are_cleaned_up(self):
        old = RateLimitHit.objects.create(scope="login", key="x" * 64)
        RateLimitHit.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=2))
        with mock.patch("throttle.middleware.random.random", return_value=0):
            self.post(LOGIN_URL)
        self.assertFalse(RateLimitHit.objects.filter(pk=old.pk).exists())
        self.assertEqual(RateLimitHit.objects.count(), 1)

"""POST isteklerine IP başına hız sınırı. Sayaçlar veritabanında tutulur, çünkü Vercel'de her istek
farklı bir örneğe düşebilir ve bellek içi sayaç güvenilir olmaz."""

import hashlib
import hmac
import logging
import random
import re
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import DatabaseError
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone

from .models import RateLimitHit

logger = logging.getLogger(__name__)

CLEANUP_CHANCE = 0.01  # isteklerin yaklaşık %1'inde eski kayıtlar silinir
RETENTION = timedelta(days=1)  # en uzun pencere (1 saat) çok altında kalır
MESSAGE = "Çok fazla istek gönderdin. Biraz bekleyip tekrar dene."


@dataclass(frozen=True)
class Rule:
    scope: str
    path: re.Pattern
    limit: int
    window: int  # saniye


RULES = (
    Rule("vote", re.compile(r"^/anket/\d+/oy/$"), limit=15, window=60),
    Rule("login", re.compile(r"^/(giris|yonetim/login)/$"), limit=10, window=600),
    Rule("register", re.compile(r"^/kayit/$"), limit=5, window=3600),
)


def client_ip(request):
    """Vercel gerçek istemci IP'sini X-Forwarded-For'a yazar (istemcinin gönderdiğini ezer); başka
    yerde bu başlık sahte gönderilebileceği için yalnızca REMOTE_ADDR'a güvenilir."""
    if settings.ON_VERCEL:
        first = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
        if first:
            return first
    return request.META.get("REMOTE_ADDR", "")


def hit_key(scope, ip):
    return hmac.new(settings.SECRET_KEY.encode(), f"{scope}:{ip}".encode(), hashlib.sha256).hexdigest()


def _matching_rule(request):
    if request.method != "POST":
        return None
    return next((rule for rule in RULES if rule.path.match(request.path_info)), None)


def _is_limited(rule, ip):
    """Sınır aşıldıysa True. Aşılmadıysa isteği kaydeder. Veritabanı hatasında istek geçer:
    sınırlayıcının arızası siteyi kapatmamalı."""
    try:
        now = timezone.now()
        key = hit_key(rule.scope, ip)
        recent = RateLimitHit.objects.filter(
            scope=rule.scope, key=key, created_at__gte=now - timedelta(seconds=rule.window)
        ).count()
        if recent >= rule.limit:
            return True
        RateLimitHit.objects.create(scope=rule.scope, key=key)
        if random.random() < CLEANUP_CHANCE:
            RateLimitHit.objects.filter(created_at__lt=now - RETENTION).delete()
    except DatabaseError:
        logger.exception("Hız sınırı kontrolü başarısız, istek geçirildi.")
    return False


def _too_many_requests(request, rule):
    if "application/json" in request.headers.get("Accept", ""):
        response = JsonResponse({"ok": False, "error": MESSAGE}, status=429)
    else:
        response = render(request, "429.html", status=429)
    response["Retry-After"] = str(rule.window)
    return response


class ThrottleMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        rule = _matching_rule(request) if settings.THROTTLE_ENABLED else None
        if rule and _is_limited(rule, client_ip(request)):
            return _too_many_requests(request, rule)
        return self.get_response(request)

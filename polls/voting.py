"""Oy verme ve seçmen kimliği mantığı."""

import uuid
from dataclasses import dataclass
from enum import Enum

from django.conf import settings
from django.db import IntegrityError, transaction

from .models import Option, Vote

COOKIE_NAME = "kz_voter"
COOKIE_MAX_AGE = 60 * 60 * 24 * 365


class VoteResult(Enum):
    OK = "ok"
    DUPLICATE = "duplicate"
    INVALID = "invalid"
    CLOSED = "closed"


@dataclass(frozen=True)
class Voter:
    key: str
    user: object = None
    new_cookie_id: str = ""  # doluysa yanıta çerez olarak yazılmalı


def _read_cookie_id(request):
    value = request.get_signed_cookie(COOKIE_NAME, default=None, max_age=COOKIE_MAX_AGE)
    try:
        return str(uuid.UUID(value))
    except (AttributeError, TypeError, ValueError):
        return None


def current_voter_key(request):
    """Mevcut seçmenin anahtarı; üye olmayanda çerez yoksa None (çerez yazmaz)."""
    if request.user.is_authenticated:
        return f"u:{request.user.pk}"
    cookie_id = _read_cookie_id(request)
    return f"a:{cookie_id}" if cookie_id else None


def identify_voter(request):
    """Oy verecek seçmeni belirler; üye olmayan ve çerezi olmayana yeni kimlik üretir."""
    if request.user.is_authenticated:
        return Voter(key=f"u:{request.user.pk}", user=request.user)
    cookie_id = _read_cookie_id(request)
    if cookie_id:
        return Voter(key=f"a:{cookie_id}")
    new_id = str(uuid.uuid4())
    return Voter(key=f"a:{new_id}", new_cookie_id=new_id)


def set_voter_cookie(response, cookie_id):
    response.set_signed_cookie(
        COOKIE_NAME,
        cookie_id,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="Lax",
        secure=not settings.DEBUG,
    )


def cast_vote(poll, option_id, voter):
    """Oyu kaydeder. Seçenek bu ankete ait olmalı; aynı seçmen ikinci kez oy veremez; kapalı ankete oy verilmez."""
    if poll.is_closed:
        return VoteResult.CLOSED
    try:
        option = poll.options.get(pk=int(option_id))
    except (TypeError, ValueError, Option.DoesNotExist):
        return VoteResult.INVALID
    try:
        with transaction.atomic():
            Vote.objects.create(poll=poll, option=option, user=voter.user, voter_key=voter.key)
    except IntegrityError:
        return VoteResult.DUPLICATE
    return VoteResult.OK


def attach_results(polls, voter_key, viewer):
    """Anketlere sonuç bilgisini ekler (Poll.objects.with_results() ile getirilmiş olmalı).

    Seçmenin oylarını tüm anketler için tek sorguda çeker. Sonuçlar yalnızca oy vermiş
    seçmene veya anketin sahibine gösterilir.
    """
    polls = list(polls)
    voted = {}
    if voter_key and polls:
        voted = dict(
            Vote.objects.filter(voter_key=voter_key, poll__in=polls).values_list("poll_id", "option_id")
        )
    for poll in polls:
        options = list(poll.options.all())
        total = sum(option.vote_count for option in options)
        poll.total_votes = total
        poll.voted_option_id = voted.get(poll.pk)
        poll.has_voted = poll.pk in voted
        poll.is_owner = viewer.is_authenticated and poll.author_id == viewer.pk
        # Kapanmış ankete artık oy verilemez, sonuçların kararı etkilemesi söz konusu olmaz: herkese açık.
        poll.show_results = poll.has_voted or poll.is_owner or poll.is_closed
        # Sahip sonuçları görürken de oy verebilir; oy butonları sonuç görünürlüğünden bağımsızdır.
        poll.can_vote = not poll.has_voted and not poll.is_closed
        poll.results = [
            {
                "option": option,
                "votes": option.vote_count,
                "percent": round(option.vote_count * 100 / total) if total else 0,
                "is_mine": option.pk == poll.voted_option_id,
            }
            for option in options
        ]
        poll.status_label = status_label(
            [item["votes"] for item in poll.results], poll.show_results, poll.is_owner, poll.is_closed
        )
    return polls


def status_label(counts, show_results, is_owner=False, is_closed=False):
    """Kartta gösterilen kısa durum etiketi.

    Oy dağılımını ima eden etiketler yalnızca sonuçları görebilen seçmene verilir;
    diğerleri oy verilmemişse yalnızca "ilk oyu sen ver" cümlesini görür.
    """
    total = sum(counts)
    if total == 0:
        if is_closed:
            return "Oy gelmeden kapandı"
        return "Henüz oy yok" if is_owner else "İlk oyu sen ver"
    if not show_results:
        return ""
    shares = sorted((count * 100 / total for count in counts), reverse=True)
    top = shares[0]
    second = shares[1] if len(shares) > 1 else 0
    if top >= 60:
        return "Karar net"
    if top < 45 and sum(1 for share in shares if share >= 15) >= 3:
        return "Kalabalık da kararsız"
    if top == second:
        return "Kafa kafaya"
    if top - second <= 20:
        return "Az farkla önde"
    return "Karar net"

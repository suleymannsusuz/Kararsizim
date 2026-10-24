from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import PollForm
from .models import Poll
from .voting import (
    VoteResult,
    attach_results,
    cast_vote,
    current_voter_key,
    identify_voter,
    set_voter_cookie,
)

User = get_user_model()

PAGE_SIZE = 20
SORT_POPULAR = "populer"
SORT_CLOSED = "kapananlar"


def feed(request):
    """Yeni (varsayılan), Popüler ve Kapananlar sekmeleri; kapalı anketler Yeni ve Popüler'de de 'Kapalı' etiketiyle görünür."""
    polls = Poll.objects.with_results()
    sort = request.GET.get("sirala")
    if sort == SORT_POPULAR:
        polls = polls.annotate(vote_total=Count("votes")).order_by("-vote_total", "-created_at", "-pk")
    elif sort == SORT_CLOSED:
        polls = polls.filter(closed_at__isnull=False).order_by("-closed_at", "-pk")
    else:
        sort = ""
    page = Paginator(polls, PAGE_SIZE).get_page(request.GET.get("sayfa"))
    attach_results(page.object_list, current_voter_key(request), request.user)
    context = {
        "page": page,
        "sort": sort,
        "extra_qs": f"&sirala={sort}" if sort else "",
    }
    return render(request, "polls/feed.html", context)


def user_polls(request, username):
    profile = get_object_or_404(User, username=username.lower())
    polls = Poll.objects.with_results().filter(author=profile)
    page = Paginator(polls, PAGE_SIZE).get_page(request.GET.get("sayfa"))
    attach_results(page.object_list, current_voter_key(request), request.user)
    return render(request, "polls/user_polls.html", {"profile": profile, "page": page, "extra_qs": ""})


def detail(request, pk):
    poll = get_object_or_404(Poll.objects.with_results(), pk=pk)
    attach_results([poll], current_voter_key(request), request.user)
    return render(request, "polls/detail.html", {"poll": poll})


@login_required
def create(request):
    form = PollForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        poll = form.save(request.user)
        messages.success(request, "Anketin yayında!")
        return redirect(poll)
    return render(request, "polls/create.html", {"form": form})


def _wants_json(request):
    return "application/json" in request.headers.get("Accept", "")


def _vote_json(request, poll, voter, result):
    """JSON yanıtı: 200 kaydedildi, 409 zaten oy verilmiş (sonuçlarla birlikte), 400 geçersiz seçenek."""
    if result is VoteResult.INVALID:
        return JsonResponse({"ok": False, "error": "Geçersiz seçenek."}, status=400)

    poll = Poll.objects.with_results().get(pk=poll.pk)
    attach_results([poll], voter.key, request.user)
    payload = {
        "ok": result is VoteResult.OK,
        "results": [
            {
                "option_id": item["option"].pk,
                "text": item["option"].text,
                "votes": item["votes"],
                "percent": item["percent"],
                "position": item["option"].position,
            }
            for item in poll.results
        ],
        "total": poll.total_votes,
        "voted_option_id": poll.voted_option_id,
        "status_label": poll.status_label,
    }
    if result is VoteResult.DUPLICATE:
        payload["error"] = "Bu ankete zaten oy verdin."
    elif result is VoteResult.CLOSED:
        payload["error"] = "Bu anket kapandı."
        payload["closed"] = True
    response = JsonResponse(payload, status=200 if result is VoteResult.OK else 409)
    if result is VoteResult.OK and voter.new_cookie_id:
        set_voter_cookie(response, voter.new_cookie_id)
    return response


@require_POST
def vote(request, pk):
    poll = get_object_or_404(Poll, pk=pk)
    voter = identify_voter(request)
    result = cast_vote(poll, request.POST.get("option"), voter)

    if _wants_json(request):
        return _vote_json(request, poll, voter, result)

    if result is VoteResult.OK:
        messages.success(request, "Oyun kaydedildi.")
    elif result is VoteResult.DUPLICATE:
        messages.info(request, "Bu ankete zaten oy verdin.")
    elif result is VoteResult.CLOSED:
        messages.info(request, "Bu anket kapandı.")
    else:
        messages.error(request, "Geçersiz seçenek.")

    response = redirect(poll)
    if result is VoteResult.OK and voter.new_cookie_id:
        set_voter_cookie(response, voter.new_cookie_id)
    return response


@login_required
@require_POST
def close(request, pk):
    poll = get_object_or_404(Poll, pk=pk)
    if poll.author_id != request.user.pk:
        raise PermissionDenied
    if poll.is_closed:
        messages.info(request, "Bu anket zaten kapalı.")
    else:
        # Aynı anda gelen iki isteğin kapanış zamanını ezmemesi için yalnızca açık anket güncellenir.
        Poll.objects.filter(pk=poll.pk, closed_at__isnull=True).update(closed_at=timezone.now())
        messages.success(request, "Anket kapatıldı. Artık oy verilemez, sonuçlar herkese açık.")
    return redirect(poll)


@login_required
@require_POST
def delete(request, pk):
    poll = get_object_or_404(Poll, pk=pk)
    if poll.author_id != request.user.pk:
        raise PermissionDenied
    poll.delete()
    messages.success(request, "Anket silindi.")
    return redirect("home")

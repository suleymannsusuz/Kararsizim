from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
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

PAGE_SIZE = 20


def feed(request):
    page = Paginator(Poll.objects.with_results(), PAGE_SIZE).get_page(request.GET.get("sayfa"))
    attach_results(page.object_list, current_voter_key(request), request.user)
    return render(request, "polls/feed.html", {"page": page})


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


@require_POST
def vote(request, pk):
    poll = get_object_or_404(Poll, pk=pk)
    voter = identify_voter(request)
    result = cast_vote(poll, request.POST.get("option"), voter)

    if result is VoteResult.OK:
        messages.success(request, "Oyun kaydedildi.")
    elif result is VoteResult.DUPLICATE:
        messages.info(request, "Bu ankete zaten oy verdin.")
    else:
        messages.error(request, "Geçersiz seçenek.")

    response = redirect(poll)
    if result is VoteResult.OK and voter.new_cookie_id:
        set_voter_cookie(response, voter.new_cookie_id)
    return response


@login_required
@require_POST
def delete(request, pk):
    poll = get_object_or_404(Poll, pk=pk)
    if poll.author_id != request.user.pk:
        raise PermissionDenied
    poll.delete()
    messages.success(request, "Anket silindi.")
    return redirect("home")

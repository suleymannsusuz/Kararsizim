import re
import uuid

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .models import Option, Poll, Vote
from .voting import COOKIE_NAME

User = get_user_model()

PASSWORD = "Gizli-Parola-482"


def make_user(username="yazar", email=None):
    return User.objects.create_user(email or f"{username}@gizli-posta.test", username, PASSWORD)


def make_poll(author, question="Bugün sinemaya mı gitsem?", options=("Sinema", "Restoran")):
    poll = Poll.objects.create(author=author, question=question)
    for position, text in enumerate(options):
        Option.objects.create(poll=poll, text=text, position=position)
    return poll


def poll_data(question="Bugün ne yapsam?", options=("Sinema", "Restoran")):
    return {"question": question, "options": list(options)}


class PollModelTests(TestCase):
    def test_question_whitespace_is_cleaned(self):
        poll = make_poll(make_user(), question="  Bugün   sinemaya \n mı gitsem?  ")
        self.assertEqual(poll.question, "Bugün sinemaya mı gitsem?")

    def test_one_vote_per_voter_per_poll_is_enforced_by_database(self):
        poll = make_poll(make_user())
        option = poll.options.first()
        Vote.objects.create(poll=poll, option=option, voter_key="a:1")
        from django.db import IntegrityError, transaction

        with self.assertRaises(IntegrityError), transaction.atomic():
            Vote.objects.create(poll=poll, option=option, voter_key="a:1")


class CreatePollTests(TestCase):
    def setUp(self):
        self.author = make_user()

    def test_guest_is_redirected_to_login(self):
        response = self.client.get(reverse("poll_create"))
        self.assertRedirects(response, "/giris/?next=/anket/olustur/")
        response = self.client.post(reverse("poll_create"), poll_data())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Poll.objects.count(), 0)

    def test_member_creates_poll_and_is_redirected_to_detail(self):
        self.client.force_login(self.author)
        response = self.client.post(
            reverse("poll_create"),
            poll_data("Bugün sinemaya mı gitsem, restorana mı?", ["Sinema", "  Restoran ", "", "Evde kal"]),
        )
        poll = Poll.objects.get()
        self.assertRedirects(response, reverse("poll_detail", args=[poll.pk]))
        self.assertEqual(poll.author, self.author)
        self.assertEqual([o.text for o in poll.options.all()], ["Sinema", "Restoran", "Evde kal"])
        self.assertEqual([o.position for o in poll.options.all()], [0, 1, 2])

    def test_option_count_must_be_between_two_and_five(self):
        self.client.force_login(self.author)
        for options in (["Tek"], [], ["", "Yalnız", ""], ["1", "2", "3", "4", "5", "6"]):
            with self.subTest(options=options):
                response = self.client.post(reverse("poll_create"), poll_data(options=options))
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].non_field_errors())
        self.assertEqual(Poll.objects.count(), 0)

    def test_five_options_are_accepted(self):
        self.client.force_login(self.author)
        self.client.post(reverse("poll_create"), poll_data(options=["1", "2", "3", "4", "5"]))
        self.assertEqual(Option.objects.count(), 5)

    def test_duplicate_options_rejected_case_insensitive(self):
        self.client.force_login(self.author)
        response = self.client.post(reverse("poll_create"), poll_data(options=["Sinema", "  sinema "]))
        self.assertContains(response, "Aynı seçenek birden fazla kez girilemez.")
        self.assertEqual(Poll.objects.count(), 0)

    def test_question_length_limits(self):
        self.client.force_login(self.author)
        for question in ("Kısa", "    a  b   ", "x" * 141, ""):
            with self.subTest(question=question):
                response = self.client.post(reverse("poll_create"), poll_data(question))
                self.assertIn("question", response.context["form"].errors)
        self.assertEqual(Poll.objects.count(), 0)

    def test_option_text_length_limit(self):
        self.client.force_login(self.author)
        response = self.client.post(reverse("poll_create"), poll_data(options=["a" * 61, "b"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Poll.objects.count(), 0)

    def test_submitted_values_are_kept_on_error(self):
        self.client.force_login(self.author)
        response = self.client.post(reverse("poll_create"), poll_data("Geçerli bir soru", ["Tek"]))
        self.assertContains(response, 'value="Tek"')
        self.assertContains(response, "Geçerli bir soru")


class VoteTests(TestCase):
    def setUp(self):
        self.author = make_user()
        self.poll = make_poll(self.author)
        self.sinema, self.restoran = self.poll.options.all()

    def vote(self, option, client=None, poll=None):
        poll = poll or self.poll
        return (client or self.client).post(reverse("poll_vote", args=[poll.pk]), {"option": option.pk})

    def test_guest_can_view_and_vote(self):
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)
        self.assertEqual(self.client.get(reverse("poll_detail", args=[self.poll.pk])).status_code, 200)
        response = self.vote(self.sinema)
        self.assertRedirects(response, reverse("poll_detail", args=[self.poll.pk]))
        vote = Vote.objects.get()
        self.assertEqual(vote.option, self.sinema)
        self.assertIsNone(vote.user)
        self.assertTrue(vote.voter_key.startswith("a:"))

    def test_guest_cookie_is_signed_and_hardened(self):
        self.vote(self.sinema)
        cookie = self.client.cookies[COOKIE_NAME]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
        self.assertEqual(int(cookie["max-age"]), 60 * 60 * 24 * 365)
        self.assertIn(":", cookie.value)  # imza eklenmiş

    def test_second_vote_from_same_browser_is_not_recorded(self):
        self.vote(self.sinema)
        response = self.vote(self.restoran, poll=self.poll)
        self.assertEqual(Vote.objects.count(), 1)
        self.assertEqual(Vote.objects.get().option, self.sinema)
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertIn("Bu ankete zaten oy verdin.", messages)

    def test_voting_twice_in_same_poll_only_blocks_that_poll(self):
        other = make_poll(self.author, question="Başka bir anket?", options=("A", "B"))
        self.vote(self.sinema)
        self.vote(other.options.first(), poll=other)
        self.assertEqual(Vote.objects.count(), 2)

    def test_member_vote_is_tied_to_user(self):
        voter = make_user("oyuncu")
        self.client.force_login(voter)
        self.vote(self.restoran)
        vote = Vote.objects.get()
        self.assertEqual(vote.user, voter)
        self.assertEqual(vote.voter_key, f"u:{voter.pk}")
        self.vote(self.sinema)
        self.assertEqual(Vote.objects.count(), 1)

    def test_member_vote_does_not_set_guest_cookie(self):
        self.client.force_login(make_user("oyuncu"))
        self.vote(self.sinema)
        self.assertNotIn(COOKIE_NAME, self.client.cookies)

    def test_option_from_another_poll_is_rejected(self):
        other = make_poll(self.author, question="Başka bir anket?", options=("A", "B"))
        response = self.vote(other.options.first())
        self.assertRedirects(response, reverse("poll_detail", args=[self.poll.pk]))
        self.assertEqual(Vote.objects.count(), 0)
        self.assertNotIn(COOKIE_NAME, self.client.cookies)

    def test_invalid_option_values_are_rejected(self):
        for value in ("", "abc", "99999", "-1"):
            with self.subTest(value=value):
                self.client.post(reverse("poll_vote", args=[self.poll.pk]), {"option": value})
        self.client.post(reverse("poll_vote", args=[self.poll.pk]), {})
        self.assertEqual(Vote.objects.count(), 0)

    def test_tampered_cookie_is_treated_as_new_voter(self):
        self.client.cookies[COOKIE_NAME] = f"{uuid.uuid4()}:sahte-imza"
        self.vote(self.sinema)
        self.assertEqual(Vote.objects.count(), 1)
        self.assertNotIn("sahte-imza", self.client.cookies[COOKIE_NAME].value)

    def test_vote_requires_post(self):
        self.assertEqual(self.client.get(reverse("poll_vote", args=[self.poll.pk])).status_code, 405)

    def test_vote_on_missing_poll_is_404(self):
        self.assertEqual(self.client.post(reverse("poll_vote", args=[9999]), {"option": 1}).status_code, 404)


class ResultsVisibilityTests(TestCase):
    def setUp(self):
        self.author = make_user()
        self.poll = make_poll(self.author)
        self.sinema, self.restoran = self.poll.options.all()
        # Başka seçmenlerin oyları: Sinema 2, Restoran 1
        for key, option in (("a:1", self.sinema), ("a:2", self.sinema), ("a:3", self.restoran)):
            Vote.objects.create(poll=self.poll, option=option, voter_key=key)

    def detail(self):
        return self.client.get(reverse("poll_detail", args=[self.poll.pk]))

    def test_results_hidden_before_voting(self):
        for url in (reverse("poll_detail", args=[self.poll.pk]), reverse("home")):
            response = self.client.get(url)
            self.assertNotContains(response, 'class="seg')
            self.assertNotContains(response, 'class="legend')
            self.assertNotContains(response, "%67")
            for label in ("Karar net", "Az farkla önde", "Kalabalık da kararsız", "Kafa kafaya"):
                self.assertNotContains(response, label)
            self.assertContains(response, 'class="option-btn')
            self.assertContains(response, "3 kişi oy verdi")

    def test_results_shown_after_voting_with_own_choice_marked(self):
        self.client.post(reverse("poll_vote", args=[self.poll.pk]), {"option": self.restoran.pk})
        response = self.detail()
        self.assertContains(response, 'class="seg opt-', count=2)
        self.assertContains(response, 'class="legend-item', count=2)
        self.assertNotContains(response, 'class="option-btn')
        self.assertContains(response, "4 kişi oy verdi")
        self.assertContains(response, "Kafa kafaya")
        results = response.context["poll"].results
        self.assertEqual([r["votes"] for r in results], [2, 2])
        self.assertEqual([r["percent"] for r in results], [50, 50])
        self.assertEqual([r["is_mine"] for r in results], [False, True])
        self.assertContains(response, "✓")

    def test_owner_sees_results_and_vote_buttons_until_voting(self):
        self.client.force_login(self.author)
        for url in (reverse("poll_detail", args=[self.poll.pk]), reverse("home")):
            response = self.client.get(url)
            self.assertContains(response, 'class="seg opt-', count=2)
            self.assertContains(response, 'class="legend-item', count=2)
            self.assertContains(response, 'class="option-btn', count=2)
            self.assertContains(response, "Sen de oy ver")

    def test_owner_vote_is_recorded_and_buttons_disappear(self):
        self.client.force_login(self.author)
        response = self.client.post(reverse("poll_vote", args=[self.poll.pk]), {"option": self.sinema.pk})
        self.assertRedirects(response, reverse("poll_detail", args=[self.poll.pk]))
        vote = Vote.objects.get(user=self.author)
        self.assertEqual((vote.option, vote.voter_key), (self.sinema, f"u:{self.author.pk}"))
        detail = self.detail()
        self.assertNotContains(detail, 'class="option-btn')
        self.assertNotContains(detail, "Sen de oy ver")
        self.assertContains(detail, "✓")
        self.assertEqual([r["is_mine"] for r in detail.context["poll"].results], [True, False])
        self.assertEqual(detail.context["poll"].total_votes, 4)

    def test_owner_cannot_vote_twice(self):
        self.client.force_login(self.author)
        url = reverse("poll_vote", args=[self.poll.pk])
        self.client.post(url, {"option": self.sinema.pk})
        self.client.post(url, {"option": self.restoran.pk})
        self.assertEqual(Vote.objects.filter(user=self.author).count(), 1)

    def test_owner_cannot_vote_on_closed_poll_and_sees_no_buttons(self):
        close_poll(self.poll)
        self.client.force_login(self.author)
        self.assertNotContains(self.detail(), 'class="option-btn')
        self.client.post(reverse("poll_vote", args=[self.poll.pk]), {"option": self.sinema.pk})
        self.assertFalse(Vote.objects.filter(user=self.author).exists())

    def test_vote_hint_is_only_shown_when_results_are_also_visible(self):
        response = self.detail()
        self.assertContains(response, 'class="option-btn')
        self.assertNotContains(response, "Sen de oy ver")

    def test_other_members_do_not_see_results_before_voting(self):
        self.client.force_login(make_user("baskasi"))
        response = self.detail()
        self.assertNotContains(response, 'class="seg')
        self.assertNotContains(response, 'class="legend')


class FeedTests(TestCase):
    def test_empty_state(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Henüz anket yok")
        self.assertContains(response, "İlk anketi sen oluştur")

    def test_newest_first_and_paginated_by_20(self):
        author = make_user()
        for index in range(25):
            make_poll(author, question=f"Soru numarası {index:02d}?")
        response = self.client.get(reverse("home"))
        page = response.context["page"]
        self.assertEqual(len(page.object_list), 20)
        self.assertEqual(page.object_list[0].question, "Soru numarası 24?")
        self.assertTrue(page.has_next())
        second = self.client.get(reverse("home") + "?sayfa=2").context["page"]
        self.assertEqual(len(second.object_list), 5)
        self.assertEqual(list(second.object_list)[-1].question, "Soru numarası 00?")

    def test_invalid_page_number_falls_back_gracefully(self):
        make_poll(make_user())
        self.assertEqual(self.client.get(reverse("home") + "?sayfa=abc").status_code, 200)
        self.assertEqual(self.client.get(reverse("home") + "?sayfa=999").status_code, 200)

    def test_query_count_does_not_grow_with_poll_count(self):
        author = make_user()
        voter = make_user("oyuncu")
        self.client.force_login(voter)

        def count_queries():
            with CaptureQueriesContext(connection) as queries:
                self.assertEqual(self.client.get(reverse("home")).status_code, 200)
            return len(queries)

        for index in range(3):
            poll = make_poll(author, question=f"Soru numarası {index}?", options=("A", "B", "C"))
            Vote.objects.create(poll=poll, option=poll.options.first(), voter_key=f"u:{voter.pk}", user=voter)
        few = count_queries()
        for index in range(3, 15):
            poll = make_poll(author, question=f"Soru numarası {index}?", options=("A", "B", "C"))
            Vote.objects.create(poll=poll, option=poll.options.first(), voter_key=f"u:{voter.pk}", user=voter)
        self.assertEqual(count_queries(), few)


class DeletePollTests(TestCase):
    def setUp(self):
        self.author = make_user()
        self.poll = make_poll(self.author)
        Vote.objects.create(poll=self.poll, option=self.poll.options.first(), voter_key="a:1")

    def test_owner_can_delete_with_votes_and_options(self):
        self.client.force_login(self.author)
        response = self.client.post(reverse("poll_delete", args=[self.poll.pk]))
        self.assertRedirects(response, reverse("home"))
        self.assertEqual((Poll.objects.count(), Option.objects.count(), Vote.objects.count()), (0, 0, 0))

    def test_other_member_gets_403(self):
        self.client.force_login(make_user("baskasi"))
        response = self.client.post(reverse("poll_delete", args=[self.poll.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Poll.objects.count(), 1)

    def test_guest_cannot_delete(self):
        response = self.client.post(reverse("poll_delete", args=[self.poll.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Poll.objects.count(), 1)

    def test_delete_requires_post(self):
        self.client.force_login(self.author)
        self.assertEqual(self.client.get(reverse("poll_delete", args=[self.poll.pk])).status_code, 405)
        self.assertEqual(Poll.objects.count(), 1)

    def test_delete_button_only_shown_to_owner(self):
        url = reverse("poll_detail", args=[self.poll.pk])
        self.assertNotContains(self.client.get(url), "Anketi sil")
        self.client.force_login(make_user("baskasi"))
        self.assertNotContains(self.client.get(url), "Anketi sil")
        self.client.force_login(self.author)
        self.assertContains(self.client.get(url), "Anketi sil")


class EmailPrivacyTests(TestCase):
    def test_no_email_address_in_any_page(self):
        author = make_user("yazar", "yazar.gizli@example.com")
        voter = make_user("oyuncu", "oyuncu.gizli@example.com")
        poll = make_poll(author)
        Vote.objects.create(poll=poll, option=poll.options.first(), voter_key=f"u:{voter.pk}", user=voter)

        public = [reverse("home"), reverse("poll_detail", args=[poll.pk])]
        guest_only = [reverse("login"), reverse("register")]
        for client_user in (None, author, voter):
            if client_user:
                self.client.force_login(client_user)
                pages = public + [reverse("poll_create")]
            else:
                pages = public + guest_only
            for url in pages:
                with self.subTest(user=client_user, url=url):
                    response = self.client.get(url)
                    html = response.content.decode()
                    self.assertEqual(response.status_code, 200)
                    self.assertNotIn("gizli@example.com", html)
                    self.assertIsNone(re.search(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", html))


JSON = {"HTTP_ACCEPT": "application/json"}


class JsonVoteTests(TestCase):
    def setUp(self):
        self.author = make_user("yazar", "yazar.gizli@example.com")
        self.poll = make_poll(self.author, options=("Sinema", "Restoran", "Evde kal"))
        self.sinema, self.restoran, self.evde = self.poll.options.all()
        self.url = reverse("poll_vote", args=[self.poll.pk])

    def post(self, option_id, client=None):
        return (client or self.client).post(self.url, {"option": option_id}, **JSON)

    def test_successful_vote_returns_200_with_results(self):
        Vote.objects.create(poll=self.poll, option=self.restoran, voter_key="a:1")
        response = self.post(self.sinema.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["voted_option_id"], self.sinema.pk)
        self.assertEqual(
            [(r["option_id"], r["text"], r["votes"], r["percent"]) for r in data["results"]],
            [(self.sinema.pk, "Sinema", 1, 50), (self.restoran.pk, "Restoran", 1, 50), (self.evde.pk, "Evde kal", 0, 0)],
        )
        self.assertEqual([r["position"] for r in data["results"]], [0, 1, 2])
        self.assertEqual(data["status_label"], "Kafa kafaya")
        self.assertEqual(Vote.objects.count(), 2)

    def test_guest_json_vote_sets_cookie_and_second_vote_is_409_with_results(self):
        self.assertEqual(self.post(self.sinema.pk).status_code, 200)
        self.assertIn(COOKIE_NAME, self.client.cookies)
        response = self.post(self.restoran.pk)
        self.assertEqual(response.status_code, 409)
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "Bu ankete zaten oy verdin.")
        self.assertEqual(data["voted_option_id"], self.sinema.pk)
        self.assertEqual(data["total"], 1)
        self.assertEqual(Vote.objects.count(), 1)

    def test_member_json_vote(self):
        voter = make_user("oyuncu")
        self.client.force_login(voter)
        self.assertEqual(self.post(self.evde.pk).status_code, 200)
        self.assertEqual(self.post(self.sinema.pk).status_code, 409)
        self.assertEqual(Vote.objects.get().user, voter)
        self.assertNotIn(COOKIE_NAME, self.client.cookies)

    def test_invalid_option_returns_400(self):
        other = make_poll(self.author, question="Başka bir anket?", options=("A", "B"))
        for option_id in ("", "abc", "99999", other.options.first().pk):
            with self.subTest(option_id=option_id):
                response = self.post(option_id)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), {"ok": False, "error": "Geçersiz seçenek."})
        self.assertEqual(Vote.objects.count(), 0)
        self.assertNotIn(COOKIE_NAME, self.client.cookies)

    def test_json_never_contains_email(self):
        self.client.force_login(make_user("oyuncu", "oyuncu.gizli@example.com"))
        for response in (self.post(self.sinema.pk), self.post(self.sinema.pk), self.post("abc")):
            self.assertNotIn("@", response.content.decode())

    def test_without_json_accept_header_still_redirects(self):
        response = self.client.post(self.url, {"option": self.sinema.pk})
        self.assertRedirects(response, reverse("poll_detail", args=[self.poll.pk]))

    def test_csrf_is_enforced_for_json_requests(self):
        from django.test import Client

        client = Client(enforce_csrf_checks=True)
        response = client.post(self.url, {"option": self.sinema.pk}, **JSON)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Vote.objects.count(), 0)


class PopularSortTests(TestCase):
    def setUp(self):
        author = make_user()
        self.quiet = make_poll(author, question="Sessiz anket burada?")
        self.hot = make_poll(author, question="Popüler anket burada?")
        self.warm = make_poll(author, question="Ilık anket burada?")
        self.newest = make_poll(author, question="En yeni anket burada?")
        for index in range(3):
            Vote.objects.create(poll=self.hot, option=self.hot.options.first(), voter_key=f"a:h{index}")
        Vote.objects.create(poll=self.warm, option=self.warm.options.first(), voter_key="a:w")

    def questions(self, query=""):
        response = self.client.get(reverse("home") + query)
        return [poll.question for poll in response.context["page"].object_list]

    def test_default_is_newest_first(self):
        self.assertEqual(
            self.questions(),
            ["En yeni anket burada?", "Ilık anket burada?", "Popüler anket burada?", "Sessiz anket burada?"],
        )

    def test_popular_orders_by_vote_count_then_recency(self):
        self.assertEqual(
            self.questions("?sirala=populer"),
            ["Popüler anket burada?", "Ilık anket burada?", "En yeni anket burada?", "Sessiz anket burada?"],
        )

    def test_unknown_sort_value_falls_back_to_newest(self):
        self.assertEqual(self.questions("?sirala=bilinmeyen"), self.questions())

    def test_tabs_mark_active_sort(self):
        self.assertContains(self.client.get(reverse("home")), 'class="tab is-active" aria-current="page">Yeni')
        self.assertContains(
            self.client.get(reverse("home") + "?sirala=populer"), 'class="tab is-active" aria-current="page">Popüler'
        )

    def test_pagination_links_keep_sort(self):
        author = make_user("baska")
        for index in range(20):
            make_poll(author, question=f"Ek anket numarası {index:02d}?")
        response = self.client.get(reverse("home") + "?sirala=populer")
        self.assertContains(response, "?sayfa=2&amp;sirala=populer")
        response = self.client.get(reverse("home") + "?sayfa=2&sirala=populer")
        self.assertContains(response, "?sayfa=1&amp;sirala=populer")

    def test_popular_query_count_is_constant(self):
        author = make_user("baska")

        def count_queries():
            with CaptureQueriesContext(connection) as queries:
                self.assertEqual(self.client.get(reverse("home") + "?sirala=populer").status_code, 200)
            return len(queries)

        few = count_queries()
        for index in range(10):
            make_poll(author, question=f"Ek anket numarası {index:02d}?")
        self.assertEqual(count_queries(), few)


class UserPollsPageTests(TestCase):
    def setUp(self):
        self.ali = make_user("ali.veli", "ali.gizli@example.com")
        self.ayse = make_user("ayse")
        self.ali_poll = make_poll(self.ali, question="Alinin anketi burada?")
        self.ayse_poll = make_poll(self.ayse, question="Ayşenin anketi burada?")

    def test_shows_only_that_users_polls(self):
        response = self.client.get(reverse("user_polls", args=["ali.veli"]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "@ali.veli")
        self.assertContains(response, "Alinin anketi burada?")
        self.assertNotContains(response, "Ayşenin anketi burada?")
        self.assertContains(response, "1 anket")

    def test_username_lookup_is_case_insensitive(self):
        self.assertEqual(self.client.get("/u/ALI.Veli/").status_code, 200)

    def test_unknown_user_is_404(self):
        self.assertEqual(self.client.get("/u/yok_boyle_biri/").status_code, 404)

    def test_user_without_polls_shows_empty_state(self):
        make_user("bos")
        self.assertContains(self.client.get("/u/bos/"), "henüz bir anket oluşturmamış")

    def test_page_shows_username_but_never_email(self):
        html = self.client.get("/u/ali.veli/").content.decode()
        self.assertNotIn("ali.gizli@example.com", html)
        self.assertIsNone(re.search(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", html))

    def test_poll_cards_link_author_names_to_user_page(self):
        for url in (reverse("home"), reverse("poll_detail", args=[self.ali_poll.pk])):
            self.assertContains(self.client.get(url), 'href="/u/ali.veli/"')

    def test_voting_state_is_respected_on_user_page(self):
        self.client.post(reverse("poll_vote", args=[self.ali_poll.pk]), {"option": self.ali_poll.options.first().pk})
        response = self.client.get("/u/ali.veli/")
        self.assertContains(response, 'class="legend-item', count=2)

    def test_deleted_polls_disappear_from_user_page(self):
        self.client.force_login(self.ali)
        self.client.post(reverse("poll_delete", args=[self.ali_poll.pk]))
        self.assertContains(self.client.get("/u/ali.veli/"), "0 anket")


class UiDetailTests(TestCase):
    def test_avatar_color_is_deterministic_and_username_based(self):
        from .templatetags.poll_extras import avatar_color

        self.assertEqual(avatar_color("ali"), avatar_color("ali"))
        self.assertNotEqual(avatar_color("ali"), avatar_color("ayse"))
        self.assertRegex(avatar_color("ali"), r"^hsl\(\d{1,3} 65% 38%\)$")

    def test_avatar_color_is_applied_on_cards(self):
        from .templatetags.poll_extras import avatar_color

        make_poll(make_user("renkli"))
        self.assertContains(self.client.get(reverse("home")), f"background: {avatar_color('renkli')}")

    def test_delete_form_has_confirmation_prompt(self):
        author = make_user()
        poll = make_poll(author)
        self.client.force_login(author)
        response = self.client.get(reverse("poll_detail", args=[poll.pk]))
        self.assertContains(response, "data-confirm=")

    def test_create_form_exposes_counter_and_option_rows_for_js(self):
        self.client.force_login(make_user())
        response = self.client.get(reverse("poll_create"))
        self.assertContains(response, 'data-counter="140"')
        self.assertContains(response, "data-option-row", count=5)
        self.assertContains(response, "data-poll-form")

    def test_card_has_status_region_and_total_hook_for_js(self):
        make_poll(make_user())
        response = self.client.get(reverse("home"))
        self.assertContains(response, 'role="status"')
        self.assertContains(response, "js-total")

    def test_css_and_js_urls_carry_a_version_to_defeat_stale_browser_cache(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertRegex(html, r'/static/css/main\.css\?v=\d+')
        self.assertRegex(html, r'/static/js/main\.js\?v=\d+')

    def test_favicon_is_linked(self):
        self.assertContains(self.client.get(reverse("home")), "img/favicon.svg")


class StatusLabelTests(TestCase):
    def label(self, counts, show_results=True, is_owner=False):
        from .voting import status_label

        return status_label(counts, show_results, is_owner)

    def test_no_votes(self):
        self.assertEqual(self.label([0, 0]), "İlk oyu sen ver")
        self.assertEqual(self.label([0, 0, 0], is_owner=True), "Henüz oy yok")
        self.assertEqual(self.label([0, 0], show_results=False), "İlk oyu sen ver")

    def test_hidden_results_get_no_distribution_hint(self):
        self.assertEqual(self.label([9, 1], show_results=False), "")

    def test_decisive_poll(self):
        self.assertEqual(self.label([13, 7]), "Karar net")  # %65
        self.assertEqual(self.label([8, 1, 1]), "Karar net")
        self.assertEqual(self.label([60, 40]), "Karar net")  # eşik: %60

    def test_narrow_lead(self):
        self.assertEqual(self.label([11, 9]), "Az farkla önde")  # %55 - %45
        self.assertEqual(self.label([50, 30, 20]), "Az farkla önde")

    def test_exact_tie(self):
        self.assertEqual(self.label([5, 5]), "Kafa kafaya")

    def test_crowd_split_across_many_options(self):
        self.assertEqual(self.label([4, 4, 3, 3]), "Kalabalık da kararsız")
        self.assertEqual(self.label([5, 4, 4, 1, 1]), "Kalabalık da kararsız")

    def test_leader_more_than_twenty_points_ahead_is_decisive(self):
        self.assertEqual(self.label([55, 30, 15]), "Karar net")
        self.assertEqual(self.label([58, 20, 22]), "Karar net")


class CardDesignTests(TestCase):
    def setUp(self):
        self.author = make_user()

    def test_feed_and_user_page_use_wide_two_column_layout(self):
        make_poll(self.author)
        for url in (reverse("home"), reverse("user_polls", args=["yazar"])):
            response = self.client.get(url)
            self.assertContains(response, '<body class="is-wide">')
            self.assertContains(response, 'class="poll-grid"')

    def test_detail_create_and_auth_pages_stay_narrow(self):
        poll = make_poll(self.author)
        self.client.force_login(self.author)
        for url in (reverse("poll_detail", args=[poll.pk]), reverse("poll_create")):
            self.assertNotContains(self.client.get(url), "is-wide")
        self.client.logout()
        for url in (reverse("login"), reverse("register")):
            self.assertNotContains(self.client.get(url), "is-wide")

    def test_empty_feed_does_not_render_grid(self):
        response = self.client.get(reverse("home"))
        self.assertNotContains(response, 'class="poll-grid"')
        self.assertContains(response, "Henüz anket yok")

    def test_unvoted_poll_with_votes_shows_neutral_bar_and_no_verdict(self):
        poll = make_poll(self.author)
        for index in range(4):
            Vote.objects.create(poll=poll, option=poll.options.first(), voter_key=f"a:{index}")
        response = self.client.get(reverse("home"))
        self.assertContains(response, 'class="dist"')
        self.assertNotContains(response, "dist-fill")
        self.assertContains(response, '<p class="poll-verdict"></p>', html=False)
        self.assertContains(response, "4 kişi oy verdi")

    def test_poll_without_votes_invites_first_vote(self):
        make_poll(self.author)
        response = self.client.get(reverse("home"))
        self.assertContains(response, "İlk oyu sen ver")
        self.assertContains(response, "0 kişi oy verdi")
        self.assertNotContains(response, "dist-fill")

    def test_owner_sees_waiting_label_when_no_votes(self):
        make_poll(self.author)
        self.client.force_login(self.author)
        self.assertContains(self.client.get(reverse("home")), "Henüz oy yok")

    def test_segments_are_proportional_and_skip_empty_options(self):
        poll = make_poll(self.author, options=("A", "B", "C"))
        a, b, c = poll.options.all()
        for index, option in enumerate([a, a, a, c]):
            Vote.objects.create(poll=poll, option=option, voter_key=f"a:s{index}")
        self.client.force_login(self.author)
        html = self.client.get(reverse("poll_detail", args=[poll.pk])).content.decode()
        segments = re.findall(r'class="seg (opt-\d)" style="flex-grow: (\d+)"', html)
        self.assertEqual(segments, [("opt-0", "3"), ("opt-2", "1")])
        self.assertIn("Karar net", html)

    def test_voter_sees_verdict_in_feed_after_voting(self):
        poll = make_poll(self.author)
        for index in range(3):
            Vote.objects.create(poll=poll, option=poll.options.last(), voter_key=f"a:o{index}")
        self.client.post(reverse("poll_vote", args=[poll.pk]), {"option": poll.options.last().pk})
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Karar net")
        self.assertContains(response, "4 kişi oy verdi")

    def test_legend_never_shows_counts_to_unvoted_visitors(self):
        poll = make_poll(self.author)
        for index in range(5):
            Vote.objects.create(poll=poll, option=poll.options.first(), voter_key=f"a:x{index}")
        for url in (reverse("home"), reverse("poll_detail", args=[poll.pk]), reverse("user_polls", args=["yazar"])):
            response = self.client.get(url)
            self.assertNotContains(response, "%100")
            self.assertNotContains(response, "legend-item")


def close_poll(poll, minutes_ago=0):
    from datetime import timedelta

    from django.utils import timezone

    Poll.objects.filter(pk=poll.pk).update(closed_at=timezone.now() - timedelta(minutes=minutes_ago))
    poll.refresh_from_db()
    return poll


class ClosePollTests(TestCase):
    def setUp(self):
        self.author = make_user()
        self.poll = make_poll(self.author)
        self.url = reverse("poll_close", args=[self.poll.pk])

    def test_owner_can_close_and_is_redirected_to_detail(self):
        self.client.force_login(self.author)
        response = self.client.post(self.url)
        self.assertRedirects(response, reverse("poll_detail", args=[self.poll.pk]))
        self.poll.refresh_from_db()
        self.assertTrue(self.poll.is_closed)
        self.assertIsNotNone(self.poll.closed_at)

    def test_other_member_gets_403_and_poll_stays_open(self):
        self.client.force_login(make_user("baskasi"))
        self.assertEqual(self.client.post(self.url).status_code, 403)
        self.poll.refresh_from_db()
        self.assertFalse(self.poll.is_closed)

    def test_guest_is_sent_to_login_and_poll_stays_open(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/giris/", response["Location"])
        self.poll.refresh_from_db()
        self.assertFalse(self.poll.is_closed)

    def test_close_requires_post(self):
        self.client.force_login(self.author)
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.poll.refresh_from_db()
        self.assertFalse(self.poll.is_closed)

    def test_closing_twice_keeps_first_closing_time(self):
        self.client.force_login(self.author)
        self.client.post(self.url)
        self.poll.refresh_from_db()
        first = self.poll.closed_at
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 302)
        self.poll.refresh_from_db()
        self.assertEqual(self.poll.closed_at, first)

    def test_close_button_only_for_owner_and_only_while_open(self):
        detail = reverse("poll_detail", args=[self.poll.pk])
        self.assertNotContains(self.client.get(detail), "Anketi kapat")
        self.client.force_login(make_user("baskasi"))
        self.assertNotContains(self.client.get(detail), "Anketi kapat")
        self.client.force_login(self.author)
        self.assertContains(self.client.get(detail), "Anketi kapat")
        self.assertContains(self.client.get(detail), "data-confirm=")
        close_poll(self.poll)
        response = self.client.get(detail)
        self.assertNotContains(response, "Anketi kapat")
        self.assertContains(response, "Anketi sil")

    def test_owner_can_still_delete_a_closed_poll(self):
        close_poll(self.poll)
        self.client.force_login(self.author)
        self.client.post(reverse("poll_delete", args=[self.poll.pk]))
        self.assertEqual(Poll.objects.count(), 0)


class ClosedPollBehaviourTests(TestCase):
    def setUp(self):
        self.author = make_user()
        self.poll = make_poll(self.author)
        self.sinema, self.restoran = self.poll.options.all()
        for key, option in (("a:1", self.sinema), ("a:2", self.sinema), ("a:3", self.restoran)):
            Vote.objects.create(poll=self.poll, option=option, voter_key=key)
        close_poll(self.poll)
        self.url = reverse("poll_vote", args=[self.poll.pk])

    def test_vote_on_closed_poll_is_not_recorded_and_sets_no_cookie(self):
        response = self.client.post(self.url, {"option": self.sinema.pk})
        self.assertRedirects(response, reverse("poll_detail", args=[self.poll.pk]))
        self.assertEqual(Vote.objects.count(), 3)
        self.assertNotIn(COOKIE_NAME, self.client.cookies)
        self.assertIn("Bu anket kapandı.", [str(m) for m in response.wsgi_request._messages])

    def test_json_vote_on_closed_poll_returns_409_with_results(self):
        response = self.client.post(self.url, {"option": self.sinema.pk}, **JSON)
        self.assertEqual(response.status_code, 409)
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertTrue(data["closed"])
        self.assertEqual(data["error"], "Bu anket kapandı.")
        self.assertEqual(data["total"], 3)
        self.assertEqual([r["votes"] for r in data["results"]], [2, 1])
        self.assertIsNone(data["voted_option_id"])
        self.assertNotIn(COOKIE_NAME, self.client.cookies)
        self.assertNotIn("@", response.content.decode())

    def test_results_are_public_on_closed_poll_without_voting(self):
        for url in (reverse("poll_detail", args=[self.poll.pk]), reverse("home")):
            response = self.client.get(url)
            self.assertContains(response, 'class="seg opt-', count=2)
            self.assertContains(response, 'class="legend-item', count=2)
            self.assertNotContains(response, 'class="option-btn')
            self.assertContains(response, "Kapalı")
            self.assertContains(response, "Karar net")
            self.assertContains(response, "3 kişi oy verdi")

    def test_closed_poll_with_no_votes_says_so(self):
        empty = close_poll(make_poll(self.author, question="Oy gelmeyen anket burada?"))
        response = self.client.get(reverse("poll_detail", args=[empty.pk]))
        self.assertContains(response, "Oy gelmeden kapandı")
        self.assertContains(response, "0 kişi oy verdi")

    def test_closed_card_has_closed_class(self):
        self.assertContains(self.client.get(reverse("home")), "poll-card is-closed")

    def test_open_poll_hides_closed_marker(self):
        make_poll(self.author, question="Açık anket burada?")
        html = self.client.get(reverse("home")).content.decode()
        self.assertEqual(html.count('class="tag-closed"'), 1)


class ClosedTabTests(TestCase):
    def setUp(self):
        author = make_user()
        self.open_poll = make_poll(author, question="Açık kalan anket burada?")
        self.old_closed = close_poll(make_poll(author, question="Önce kapanan anket?"), minutes_ago=60)
        self.new_closed = close_poll(make_poll(author, question="Sonra kapanan anket?"), minutes_ago=5)

    def questions(self, query=""):
        response = self.client.get(reverse("home") + query)
        return [poll.question for poll in response.context["page"].object_list]

    def test_closed_tab_lists_only_closed_polls_latest_closing_first(self):
        self.assertEqual(self.questions("?sirala=kapananlar"), ["Sonra kapanan anket?", "Önce kapanan anket?"])

    def test_new_and_popular_tabs_still_list_closed_polls(self):
        self.assertEqual(len(self.questions()), 3)
        self.assertEqual(len(self.questions("?sirala=populer")), 3)

    def test_tabs_mark_closed_as_active(self):
        response = self.client.get(reverse("home") + "?sirala=kapananlar")
        self.assertContains(response, 'class="tab is-active" aria-current="page">Kapananlar')
        self.assertContains(response, 'class="tab">Yeni')
        self.assertContains(response, 'class="tab">Popüler')

    def test_closed_tab_pagination_keeps_sort(self):
        author = make_user("baska")
        for index in range(20):
            close_poll(make_poll(author, question=f"Kapalı ek anket {index:02d}?"))
        response = self.client.get(reverse("home") + "?sirala=kapananlar")
        self.assertContains(response, "?sayfa=2&amp;sirala=kapananlar")

    def test_empty_closed_tab_message(self):
        Poll.objects.all().update(closed_at=None)
        response = self.client.get(reverse("home") + "?sirala=kapananlar")
        self.assertContains(response, "Kapanan anket yok")
        self.assertNotContains(response, "İlk anketi sen oluştur")

    def test_closed_tab_query_count_is_constant(self):
        author = make_user("baska")

        def count_queries():
            with CaptureQueriesContext(connection) as queries:
                self.assertEqual(self.client.get(reverse("home") + "?sirala=kapananlar").status_code, 200)
            return len(queries)

        few = count_queries()
        for index in range(10):
            close_poll(make_poll(author, question=f"Kapalı ek anket {index:02d}?"))
        self.assertEqual(count_queries(), few)

    def test_unknown_sort_still_falls_back_to_new(self):
        self.assertEqual(self.questions("?sirala=bilinmeyen"), self.questions())

    def test_user_page_shows_closed_polls_with_tag(self):
        response = self.client.get(reverse("user_polls", args=["yazar"]))
        self.assertContains(response, 'class="tag-closed"', count=2)

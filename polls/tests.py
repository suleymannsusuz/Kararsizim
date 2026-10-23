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
            self.assertNotContains(response, 'class="bar"')
            self.assertNotContains(response, "%67")
            self.assertContains(response, 'class="option-btn')
            self.assertContains(response, "3 oy")

    def test_results_shown_after_voting_with_own_choice_marked(self):
        self.client.post(reverse("poll_vote", args=[self.poll.pk]), {"option": self.restoran.pk})
        response = self.detail()
        self.assertContains(response, 'class="bar"', count=2)
        self.assertNotContains(response, 'class="option-btn')
        self.assertContains(response, "4 oy")
        results = response.context["poll"].results
        self.assertEqual([r["votes"] for r in results], [2, 2])
        self.assertEqual([r["percent"] for r in results], [50, 50])
        self.assertEqual([r["is_mine"] for r in results], [False, True])
        self.assertContains(response, "✓")

    def test_owner_always_sees_results(self):
        self.client.force_login(self.author)
        for url in (reverse("poll_detail", args=[self.poll.pk]), reverse("home")):
            response = self.client.get(url)
            self.assertContains(response, 'class="bar"', count=2)
            self.assertNotContains(response, 'class="option-btn')

    def test_other_members_do_not_see_results_before_voting(self):
        self.client.force_login(make_user("baskasi"))
        self.assertNotContains(self.detail(), 'class="bar"')


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
        self.assertContains(response, 'class="bar"', count=2)

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

    def test_favicon_is_linked(self):
        self.assertContains(self.client.get(reverse("home")), "img/favicon.svg")

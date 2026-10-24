# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**kararsızım** — a Turkish-language poll site where people ask others to help them decide (Django, server-rendered templates, plain HTML/CSS/JS, Postgres on Supabase, deployed to Vercel).

The full spec (data model, URLs, vote/response behaviour, design tokens, phase scopes and acceptance criteria, decision log) lives in `docs/kararsizim-proje-plani.md`. Read the relevant sections there before working on a phase; do not duplicate it here.

## Working agreement
- Work proceeds in phases (Faz 0–4 in the plan). Implement **only the requested phase**, check its acceptance criteria, run tests, summarize, and stop. Faz 0–3 (skeleton, accounts, poll core, UI polish and JS) are done; Faz 4 (Supabase + Vercel) is next.
- Present a short plan before Faz 2 and Faz 4. Commit only when the user asks.
- Faz 4: the user explicitly asked Claude to create the Supabase project (done: `kararsizim`, ref `vedhbxahipejdggbtzho`, eu-central-1, free plan, in the user's org). Migrations are applied to it and RLS is enabled (policy-less) on all `public` tables; the project's Data API is still on until the user disables it in the panel. Any new migration that adds tables needs the RLS statement from the README re-run. The working pooler host is `aws-1-eu-central-1.pooler.supabase.com` (`aws-0-…` returns "tenant not found"). Do not ask for or print the database password or connection string; the user puts `DATABASE_URL` into the local `.env` themselves, and `.env` lines must never be echoed unmasked. Vercel is a later stage and stays manual unless the user says otherwise.
- Environment: Python 3.13 in `.venv` (the plan says 3.12; the user chose to keep 3.13), Django 5.2 LTS. Question every new dependency.

## Commands
Windows; use the venv interpreter directly.
```
.venv\Scripts\python.exe manage.py runserver
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe manage.py test
.venv\Scripts\python.exe manage.py test accounts.tests.SomeTestCase.test_name   # single test
.venv\Scripts\python.exe manage.py makemigrations && .venv\Scripts\python.exe manage.py migrate
```
No linter or formatter is configured. The local `.env` is gitignored (copy `.env.example`); without it the app refuses to start because `DJANGO_DEBUG` defaults to `False` and `DJANGO_SECRET_KEY` is then required. `.claude/launch.json` defines a `django` preview server on port 8000.

## Architecture notes that span files
- **Custom user model** (`accounts.User`, `AUTH_USER_MODEL`) logs in by **email** (`USERNAME_FIELD = "email"`). `UserManager` and `User.save()` both lowercase email and username, and case-insensitive `UniqueConstraint(Lower(...))` backs it at the DB level. `first_name`/`last_name` are removed, so the admin in `accounts/admin.py` defines its own fieldsets; keep them in sync with the model. Never change the user model after migrations are applied elsewhere.
- **Auth flow** (`accounts/`): `RegisterForm` is a plain `forms.Form` (not a ModelForm) so duplicate checks are explicit `__iexact` queries with Turkish messages, and it validates username (`^[a-z0-9_.]{3,20}$` after lowercasing, plus the reserved-names set) and passwords. `LoginForm` takes an email in the `username` field and lowercases it, because lookup is an exact match against the stored lowercase email. Logout is Django's POST-only `LogoutView`. Shared form markup is `templates/partials/form_fields.html`.
- **Settings** (`config/settings.py`) read everything from env vars. `DATABASE_URL` empty/unset falls back to SQLite (`dj_database_url.parse` with an explicit `or`, because `dj_database_url.config` does not fall back when the variable is set but empty). When the URL is Postgres, `DISABLE_SERVER_SIDE_CURSORS=True`, `sslmode=require` (opt out with `DATABASE_SSL_REQUIRE=False`) and `CONN_MAX_AGE=0` are applied for the Supabase transaction pooler. `manage.py test` ignores `DATABASE_URL` and always uses SQLite, so tests never touch the remote database. Secure cookies, whitenoise and Vercel config are still pending (Faz 4, deploy part).
- **Supabase is only a Postgres host.** No Supabase Auth, anon key or JS client; all data access goes through Django. Migrations run locally against the remote DB, never in the Vercel build.
- **Voting identity** (`polls/voting.py`): `voter_key` is `u:<user id>` for members and `a:<uuid>` from a signed `kz_voter` cookie for guests; `UniqueConstraint(poll, voter_key)` plus `IntegrityError` handling in `cast_vote` enforces one vote. The guest cookie is written only after a successful vote (`current_voter_key` reads without creating one; `identify_voter` may mint a new id). Results are hidden from non-owners until they vote, and votes cannot be changed.
- **Results rendering**: always load polls through `Poll.objects.with_results()` (prefetches options annotated with `vote_count`) and pass them to `attach_results(polls, voter_key, viewer)`, which adds `results`, `total_votes`, `show_results`, `is_owner` etc. in one extra query for the viewer's votes. Templates must only render per-option counts when `poll.show_results`; `tests.py` asserts the feed query count stays constant as polls grow. `partials/poll_card.html` is shared by feed and detail (`detail=True` adds the owner's delete button).
- **Vote endpoint contract** (`polls/views.py`): `POST /anket/<id>/oy/` returns JSON only when the request has `Accept: application/json` (200 saved, 409 duplicate with the same results payload, 400 invalid option; results include `position` for the color class), otherwise redirects with `messages`. `static/js/main.js` is a no-build, no-framework enhancement layer that builds the result DOM with `textContent` (never `innerHTML`, since option text is user input) and mirrors the markup of `partials/poll_card.html`; change both together. It also handles the confirm-on-submit hook (`data-confirm`), the `0/140` counter (`data-counter`), and add/remove option rows (`data-poll-form`, `data-option-row`).
- **Feed and profile**: `?sirala=populer` orders by vote count (annotated as `vote_total`, not `total_votes`, which `attach_results` sets per poll); unknown values fall back to newest. Pagination links carry the sort through the `extra_qs` context variable. `/u/<username>/` looks the user up lowercased and shows only that user's polls. Avatar colors come from the `avatar_color` filter in `polls/templatetags/poll_extras.py` (deterministic, not Python's randomized `hash()`).
- **Poll creation form** (`polls/forms.py`): options are repeated `options` inputs read with `getlist` (not fixed fields), so a 6th option is rejected instead of silently dropped; Faz 3's add/remove JS must keep that field name. Option colors come from `position` via `.opt-0`…`.opt-4` classes setting `--c`.
- **Email must never be exposed** in templates, JSON responses or page source; authors are shown by `username` only.
- **JS is progressive enhancement only**: every flow (vote, create, delete, logout) must work as a plain form POST + redirect with JS disabled. State-changing actions are POST-only.
- Templates are in the top-level `templates/` (`base.html`, `partials/`), statics in `static/`. The navbar currently hard-codes `/giris/`, `/kayit/`, `/cikis/`, `/u/<username>/`, `/anket/olustur/` paths, which will be real routes in later phases; keep URL paths in Turkish as specified in the plan.
- UI text is Turkish, identifiers and code are English. Admin lives at `/yonetim/`, not `/admin/`.

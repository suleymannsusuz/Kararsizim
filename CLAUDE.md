# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**kararsızım** — a Turkish-language poll site where people ask others to help them decide (Django, server-rendered templates, plain HTML/CSS/JS, Postgres on Supabase, deployed to Vercel).

The full spec (data model, URLs, vote/response behaviour, design tokens, phase scopes and acceptance criteria, decision log) lives in `docs/kararsizim-proje-plani.md`. Read the relevant sections there before working on a phase; do not duplicate it here.

## Working agreement
- Work proceeds in phases (Faz 0–4 in the plan). Implement **only the requested phase**, check its acceptance criteria, run tests, summarize, and stop. Faz 0 is done; Faz 1 (accounts) is next.
- Present a short plan before Faz 2 and Faz 4. Commit only when the user asks.
- Faz 4: do not use the Supabase/Vercel MCP tools. Prepare code, settings and README, and give the user panel steps to perform themselves.
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
- **Settings** (`config/settings.py`) read everything from env vars. `DATABASE_URL` empty/unset falls back to SQLite (`dj_database_url.parse` with an explicit `or`, because `dj_database_url.config` does not fall back when the variable is set but empty). Postgres-specific tuning (`DISABLE_SERVER_SIDE_CURSORS`, SSL, secure cookies, whitenoise) is intentionally deferred to Faz 4.
- **Supabase is only a Postgres host.** No Supabase Auth, anon key or JS client; all data access goes through Django. Migrations run locally against the remote DB, never in the Vercel build.
- **Voting identity** (planned in `polls/voting.py`): `voter_key` is `u:<user id>` for members and `a:<uuid>` from a signed `kz_voter` cookie for guests; `UniqueConstraint(poll, voter_key)` plus `IntegrityError` handling enforces one vote. Results are hidden from non-owners until they vote, and votes cannot be changed.
- **Email must never be exposed** in templates, JSON responses or page source; authors are shown by `username` only.
- **JS is progressive enhancement only**: every flow (vote, create, delete, logout) must work as a plain form POST + redirect with JS disabled. State-changing actions are POST-only.
- Templates are in the top-level `templates/` (`base.html`, `partials/`), statics in `static/`. The navbar currently hard-codes `/giris/`, `/kayit/`, `/cikis/`, `/u/<username>/`, `/anket/olustur/` paths, which will be real routes in later phases; keep URL paths in Turkish as specified in the plan.
- UI text is Turkish, identifiers and code are English. Admin lives at `/yonetim/`, not `/admin/`.

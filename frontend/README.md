# Kompass frontend (prototype)

Thin TypeScript/React frontend for evaluating the REST API design. It is a pure
presentation layer over `/api/` — no business logic. Types are generated from
the backend's OpenAPI schema, so the client is fully typed against the API.

## Stack

- **Vite + React 18 + TypeScript**
- **openapi-fetch** — typed fetch client
- **openapi-typescript** — generates `src/api/schema.d.ts` from `openapi.json`

## One-time backend setup

The prototype logs in via the OAuth2 Resource-Owner-Password grant against the
project's own provider (`/o/token/`). Production should use Authorization-Code +
PKCE — this shortcut only exists so the prototype is easy to run.

The dev container already serves the API + `/o/` at **http://localhost:8000**
(its entrypoint runs `runserver`), so there is no separate server step — just
start the environment and create the dev OAuth app and a login user:

```bash
make dev up                                   # starts API on http://localhost:8000
make dev manage ensure_frontend_oauth_app     # creates the public dev OAuth app
make dev createsuperuser                       # a user with a usable password
```

If the API lives elsewhere, set `VITE_API_BASE` for the frontend.

## Run the frontend

```bash
cd frontend
npm install
npm run gen:api      # regenerate types from openapi.json (already generated)
npm run dev          # http://localhost:5173
```

Log in with a Django user that has a usable password. What you see is scoped by
the same permission model the admin enforces: without extra permissions a user
sees only themselves; a user with `list_global_member` / `view_group` sees more.

## Regenerating the API contract

When the backend API changes, re-export the schema and regenerate types. Run
the export from the host using the project venv (it can see `frontend/`, which
is not mounted into the dev container):

```bash
# from repo root: dump the schema to frontend/openapi.json
cd jdav_web && ../.venv/bin/python export_openapi.py
# then regenerate the typed client
cd ../frontend && npm run gen:api
```

The schema is exported in the source language, English, and the output is
byte-identical whatever the exporter's environment looks like. That matters
because every `verbose_name` and `help_text` lands in it as a title or
description, and those are lazy translations: compiled `.mo` files are
gitignored and built at container start, so an export that followed the
ambient locale disagreed with itself between a fresh checkout and a running
container — hundreds of strings flipping language, none of them a real change.
English is also the right language for the artifact, which is a contract read
by developers and fed to a type generator, not a page shown to a member.

It is a script rather than a `manage.py` command because a couple of
`help_text`s interpolate with `%` at model-definition time, freezing their
language as the models are imported. `manage.py` has already called
`django.setup()` by the time a command runs, so only a script can deactivate
translations early enough.

One source of churn is left: those same interpolated `help_text`s embed
deployment settings (the mailer's allowed forwarding domains), so the schema
still reflects whichever configuration the exporter ran against.

## Scope

Deliberately partial — enough to evaluate the design: members (list / detail /
edit), groups, excursions. Writes, workflow actions, documents and the other
apps are not wired yet.

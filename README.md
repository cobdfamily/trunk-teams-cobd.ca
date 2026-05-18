# trunk-teams-cobd.ca

[![test](https://github.com/cobdfamily/trunk-teams-cobd.ca/actions/workflows/test.yml/badge.svg)](https://github.com/cobdfamily/trunk-teams-cobd.ca/actions/workflows/test.yml)

Per-team production data for the **cobd.ca** tenant of
[`cobdfamily/trunk`](https://github.com/cobdfamily/trunk) —
menus, extensions, documents, audio prompts. One repo == one
team; sibling repos hold each other team (`trunk-teams-<name>`
when others come online).

The trunk deploy host clones this repo and bind-mounts its
root at `/app/data/teams/cobd.ca` inside the trunk container.
The bind goes to the team-slot path, **not** `/app/data` — a
whole-data bind would shadow the trunk image's built-in
`/app/data/templates` (shared rendering templates baked in
since trunk v5.7.0).

```
audio/<file>             team-wide WAVs
team.yaml                signature_verification, pbx
menus/<name>.yaml        Twilio Gather config
extensions/<n>/          per-extension profile + audio
  profile.yaml           alias | dial.pbx | legacy sip
  audio/<file>
documents/<name>.xml.j2  per-team Jinja2 doc routes

tests/                   E2E harness (test_e2e.py +
                         trunk-config.yaml + requirements.txt)
docker-compose.yaml      brings up trunk + talkshow with this
                         repo mounted at the cobd.ca slot
```

## Bind-mount for production

In your trunk deploy host's compose:

```yaml
services:
  trunk:
    image: kibble.apps.blindhub.ca/cobdfamily/trunk:latest
    volumes:
      - /opt/trunk-teams-cobd.ca:/app/data/teams/cobd.ca:ro
      - ./config.yaml:/app/config.yaml:ro
```

Setup the host once:

```sh
sudo mkdir -p /opt/trunk-teams-cobd.ca
sudo git clone https://github.com/cobdfamily/trunk-teams-cobd.ca \
     /opt/trunk-teams-cobd.ca
```

Edits land on the next request -- trunk has no cache. To
sync new content from this repo:

```sh
cd /opt/trunk-teams-cobd.ca && git pull
```

No container restart needed.

## Adding more teams

Each team gets its own data repo. A trunk deploy serving
two teams has two bind mounts:

```yaml
volumes:
  - /opt/trunk-teams-cobd.ca:/app/data/teams/cobd.ca:ro
  - /opt/trunk-teams-other:/app/data/teams/other:ro
```

The repo name pattern is `trunk-teams-<team-name>`. Team
admins get write access to just their repo.

## Schema

The canonical reference for every YAML field here lives in
the trunk repo at
[`SCHEMA.md`](https://github.com/cobdfamily/trunk/blob/main/SCHEMA.md).
Read it before adding or editing files here -- it lists every
required / optional / defaulted field with notes on audio-
path heuristics and the three extension profile shapes.

Schema versions are pinned to trunk releases: a trunk minor
bump that touches a schema shape always documents the change
in `SCHEMA.md` first.

## End-to-end tests

`docker-compose.yaml` brings up `cobdfamily/trunk` with this
checkout mounted at `/app/data/teams/cobd.ca`, plus
`cobdfamily/talkshow` alongside it for production-shape
parity. `tests/test_e2e.py` walks the menu / extension /
audio paths and asserts the rendered TwiML.

```sh
docker compose up -d

python3 -m venv tests/.venv
tests/.venv/bin/pip install -r tests/requirements.txt
tests/.venv/bin/python -m pytest tests/test_e2e.py -v

docker compose down -v
```

The suite locks the data tree against the regression that
bit production once: `{{ data.. }}` smudges in the shared
templates from a stale `trunk-migrate` run that broke every
menu and extension render.

## CI

`.github/workflows/test.yml` runs the E2E suite on push, on
PR, and nightly at 07:00 UTC. The nightly catches a
`trunk:latest` or `talkshow:latest` regression that breaks
rendering of this data tree within ~24h, instead of waiting
for the next push to surface it.

## History

This repo was previously named `cobdfamily/trunk-data` and
held nested per-team subdirs under `teams/<team>/`. The
v0.7.0 rename to `cobdfamily/trunk-teams-cobd.ca` collapsed
that to one repo per team; the inert `teams/general/` slot
that lived at the old root has been dropped. GitHub
preserves redirects from the old URL.

## License

AGPL-3.0 — see `LICENSE`.

# trunk-data

[![test](https://github.com/cobdfamily/trunk-data/actions/workflows/test.yml/badge.svg)](https://github.com/cobdfamily/trunk-data/actions/workflows/test.yml)

Per-team production data for `cobdfamily/trunk` — menus,
extensions, documents, audio prompts. The `trunk` deploy
host clones this repo and bind-mounts its `teams/` subdir
at `/app/data/teams` inside the trunk container. **Not**
mounted at `/app/data` — the shared rendering templates
ship inside the trunk image at `/app/data/templates` and
a whole-data bind would shadow them. See trunk's
[DEPLOYMENT.md](https://github.com/cobdfamily/trunk/blob/main/DEPLOYMENT.md)
for the bind-mount example.

```
teams/<team>/
  team.yaml              optional, per-team settings
                         (signature_verification, pbx)
  menus/<name>.yaml      Twilio Gather config
  extensions/<n>/        per-extension profile + audio
    profile.yaml         alias | dial.pbx | legacy sip
    audio/<file>
  documents/<name>.xml.j2
  audio/<file>
```

## Schema

The canonical reference for every YAML field in this tree
lives in the trunk repo at
[`SCHEMA.md`](https://github.com/cobdfamily/trunk/blob/main/SCHEMA.md).
Read it before adding or editing files here -- it lists
every required / optional / defaulted field with notes on
audio-path heuristics and the three extension profile
shapes.

This repo tracks `main`; schema versions are pinned to
trunk releases (a trunk minor-bump that touches a schema
shape always documents the change in `SCHEMA.md` first).

## End-to-end tests

`docker-compose.yaml` brings up `cobdfamily/trunk` with
this checkout mounted as its data tree, plus a
`cobdfamily/talkshow` alongside it for production-shape
parity. `tests/test_e2e.py` walks the menu / extension /
audio paths through trunk and asserts the rendered TwiML.

```sh
docker compose up -d

python3 -m venv tests/.venv
tests/.venv/bin/pip install -r tests/requirements.txt
tests/.venv/bin/python -m pytest tests/test_e2e.py -v

docker compose down -v
```

The suite locks the data tree against the regression that
bit production once: `{{ data.. }}` smudges in the shared
templates from a stale `trunk-migrate` run that broke
every menu and extension render.

## CI

`.github/workflows/test.yml` runs the E2E suite on push,
on PR, and nightly at 07:00 UTC. The nightly catches a
`trunk:latest` or `talkshow:latest` regression that
breaks rendering of this data tree within ~24h, instead
of waiting for the next push to surface it.

## License

AGPL-3.0 — see `LICENSE`.

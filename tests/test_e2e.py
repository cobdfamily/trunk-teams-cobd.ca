"""End-to-end tests for the trunk-teams-cobd.ca tree.

Assumes the docker-compose stack at the repo root is up -- trunk
serving from this checkout (bind-mounted at
/app/data/teams/cobd.ca) and a talkshow alongside it (unused
by the current paths but present for the production-shape stack).

The tests walk the menu / extension / audio paths Twilio actually
hits, verify the rendered TwiML, and lock the data tree against
the regression that bit production earlier (``{{ data.. }}``
from a stale trunk-migrate run breaking every extension call).
Run inside CI via .github/workflows/test.yml.
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET

import pytest
import requests


TRUNK_BASE_URL = os.environ.get("TRUNK_BASE_URL", "http://localhost:1962")
TALKSHOW_BASE_URL = os.environ.get("TALKSHOW_BASE_URL", "http://localhost:8001")

# X-Forwarded-* headers the tests send so trunk emits URLs that
# match this hardcoded host (rather than http://trunk:1962, which
# Twilio would never reach in production). Mirrors what the
# reverse proxy does in front of trunk on the deploy host.
PROXY_HEADERS = {
    "X-Forwarded-Proto": "https",
    "X-Forwarded-Host": "phone.example",
}


def _post(path: str, **form) -> requests.Response:
    """POST a Twilio-shaped form-urlencoded webhook to trunk.
    ``allow_redirects=False`` so a 302 to ``phone.example`` (the
    test public host) doesn't try to DNS-resolve and time out —
    we want to inspect the redirect, not follow it."""
    return requests.post(
        TRUNK_BASE_URL + path,
        data=form,
        headers=PROXY_HEADERS,
        timeout=10,
        allow_redirects=False,
    )


def _get(path: str) -> requests.Response:
    return requests.get(
        TRUNK_BASE_URL + path,
        headers=PROXY_HEADERS,
        timeout=10,
        allow_redirects=False,
    )


# ---------------------------------------------------------------------------
# liveness — both services
# ---------------------------------------------------------------------------


def test_trunk_liveness():
    r = requests.get(TRUNK_BASE_URL + "/", timeout=5)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["service"] == "trunk"
    assert body["status"] == "ok"
    assert body["version"]


def test_talkshow_liveness():
    """Talkshow is in the compose for production-shape parity even
    though the current cobd.ca tree doesn't reference it. This
    test is a smoke check that the image still boots with stub
    Azure credentials. Skips if the host port isn't bound."""
    try:
        r = requests.get(TALKSHOW_BASE_URL + "/", timeout=5)
    except requests.RequestException:
        pytest.skip(f"talkshow not reachable at {TALKSHOW_BASE_URL}")
    assert r.status_code == 200
    assert r.json()["service"] == "talkshow"


# ---------------------------------------------------------------------------
# menu render — the entry path Twilio hits on every inbound call
# ---------------------------------------------------------------------------


_TWIML_NS = ""  # TwiML is namespaceless XML.


def _parse_twiml(text: str) -> ET.Element:
    """Wrap the bare TwiML fragment trunk emits in a single root
    element so ElementTree can parse it, then return the inner
    element list."""
    root = ET.fromstring(f"<Response>{text}</Response>")
    return root


def test_mainmenu_renders_gather():
    """``GET /menus/mainmenu`` (Twilio's first hit) returns a
    Gather with the menu prompt. The Gather's action is the same
    URL trunk's running on, so Twilio re-POSTs the user's DTMF
    back to it."""
    r = _post("/v1/teams/cobd.ca/menus/mainmenu")
    assert r.status_code == 200, r.text
    assert "<Gather" in r.text
    # The Gather action URL is the public origin (X-Forwarded-Host).
    assert "phone.example" in r.text
    # Prompt audio is what mainmenu.yaml configured.
    assert "/audio/mainmenu.wav" in r.text
    # And the rendered URL points at the team-prefixed audio path.
    assert "/v1/teams/cobd.ca/audio/mainmenu.wav" in r.text


def test_mainmenu_with_invalid_digit_replays_gather():
    """A digit not listed in mainmenu.yaml re-renders the gather
    so Twilio prompts the caller again (the legacy IVR shape)."""
    r = _post("/v1/teams/cobd.ca/menus/mainmenu", Digits="9999")
    assert r.status_code == 200
    # Still a Gather (re-prompt), not a Redirect.
    assert "<Gather" in r.text


def test_mainmenu_routes_extension_digit_to_extension():
    """Pressing 5 on mainmenu goes to /extensions/100 per
    menus/mainmenu.yaml. Verify the response is a Redirect to
    the matching path."""
    r = _post("/v1/teams/cobd.ca/menus/mainmenu", Digits="5")
    assert r.status_code == 200
    assert "<Redirect" in r.text
    assert "/v1/teams/cobd.ca/extensions/100" in r.text


# ---------------------------------------------------------------------------
# extension render — the regression we fixed lives here
# ---------------------------------------------------------------------------


def test_extension_100_dial_renders_pbx_loop():
    """Regression test for the ``{{ data.. }}`` template fix.
    Extension 100's profile.yaml has ``dial.pbx: ['100']``.
    The extension template should render a <Sip> with
    ``x-extension=100`` substituted in. Before the fix, the Sip
    tag rendered ``x-extension={{ data.. }}`` (Jinja2 syntax
    error -> 500 + error doc fallthrough)."""
    r = _post("/v1/teams/cobd.ca/extensions/100")
    assert r.status_code == 200, r.text
    assert "<Dial" in r.text
    assert "<Sip>" in r.text
    # The pbx item ('100') flows into x-extension=
    assert "x-extension=100" in r.text
    # And the broken double-dot literal is gone for good.
    assert "data.." not in r.text


def test_extension_with_voicemail_falls_through_when_absent():
    """Extension 100 has no voicemail config in profile.yaml;
    the {% if data.extension.voicemail %} branch should be a
    no-op and the response should not contain a <Record> tag."""
    r = _post("/v1/teams/cobd.ca/extensions/100")
    assert "<Record" not in r.text


def test_extension_unknown_returns_error_doc():
    """An extension number with no profile.yaml -> trunk returns
    a 302 to documents/default with ``?error=true``. Twilio
    follows the redirect and renders that template."""
    r = _post("/v1/teams/cobd.ca/extensions/9999999")
    assert r.status_code in (302, 303, 307)
    location = r.headers.get("location", "")
    assert "/documents/default" in location
    assert "error=true" in location


# ---------------------------------------------------------------------------
# audio serve — file response from the team tree
# ---------------------------------------------------------------------------


def test_team_audio_served():
    r = requests.get(
        TRUNK_BASE_URL + "/v1/teams/cobd.ca/audio/mainmenu.wav",
        headers=PROXY_HEADERS, timeout=10,
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"
    # WAV files start with "RIFF".
    assert r.content[:4] == b"RIFF"


def test_team_audio_missing_returns_404_or_fallback():
    r = requests.get(
        TRUNK_BASE_URL + "/v1/teams/cobd.ca/audio/does-not-exist.wav",
        headers=PROXY_HEADERS, timeout=10,
    )
    # No templates/error.wav in this tree, so 404 is the expected
    # path. If a fallback gets added later, 200 with audio/wav
    # is also acceptable.
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        assert r.headers["content-type"] == "audio/wav"


# ---------------------------------------------------------------------------
# template parses — sentinel against re-introducing data..
# ---------------------------------------------------------------------------


def test_no_data_dot_dot_in_repo_templates(tmp_path):
    """Local sentinel: scan every .j2 in the repo for the broken
    ``{{ data.. }}`` artifact the trunk-migrate fix replaced. If
    a future migration regresses it, this test catches it before
    the templates ship."""
    here = os.path.dirname(__file__)
    repo_root = os.path.dirname(here)
    matches = []
    for root, _dirs, files in os.walk(repo_root):
        for name in files:
            if not name.endswith(".j2"):
                continue
            path = os.path.join(root, name)
            with open(path) as f:
                if re.search(r"\bdata\.\.", f.read()):
                    matches.append(path)
    assert not matches, f"`data..` reappeared in: {matches}"

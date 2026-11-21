"""Run with the hub on the path:  PYTHONPATH=../Pixoo64-Marketplace pytest"""

import importlib.util
import json
import threading
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("spotify_plugin", ROOT / "plugin.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

DEFAULTS = {f["name"]: f["default"] for f in json.loads((ROOT / "plugin.json").read_text())["settings"]
            if "default" in f}


class Bridge:
    def __init__(self):
        self.stop_event = threading.Event()
        self.sent = []

    def send(self, msg):
        self.sent.append(msg)

    def last(self, kind):
        return next((m for m in reversed(self.sent) if m["type"] in kind), None)


class Resp:
    def __init__(self, status=200, data=None, content=b""):
        self.status_code, self._data, self.content, self.headers = status, data, content, {}
        self.ok = status < 400

    def json(self):
        return self._data

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(self.status_code)


def cover_png():
    buf = BytesIO()
    Image.new("RGB", (300, 300), (200, 30, 30)).save(buf, "PNG")
    return buf.getvalue()


def playback(device_type, name="Gerät", playing=True):
    return {
        "is_playing": playing, "progress_ms": 30000,
        "device": {"name": name, "type": device_type},
        "item": {"name": "Song", "duration_ms": 120000, "artists": [{"name": "Band"}],
                 "album": {"images": [{"url": "https://i/640", "width": 640}, {"url": "https://i/64", "width": 64}]}},
    }


@pytest.fixture
def plugin(tmp_path):
    state = {"player": None}

    class Session:
        headers = {}

        def post(self, url, **kw):
            return Resp(200, {"access_token": "tok", "expires_in": 3600})

        def get(self, url, **kw):
            if url.endswith("/me/player"):
                return Resp(204) if state["player"] is None else Resp(200, state["player"])
            if url.startswith("https://i/"):
                return Resp(200, content=cover_png())
            return Resp(404)

    cfg = dict(DEFAULTS, client_id="id", client_secret="sec", refresh_token="r")
    bridge = Bridge()
    p = mod.Spotify("spotify", cfg, str(tmp_path), bridge)
    p.setup()
    p.session = Session()
    return p, bridge, state


def run(p, t):
    p.next_poll = 0
    import time
    orig = time.time
    mod.time.time = lambda: t
    try:
        p.tick()
    finally:
        mod.time.time = orig


@pytest.mark.parametrize("dtype,shown", [
    ("Computer", True), ("Smartphone", False), ("Tablet", False), ("Speaker", True), ("Automobile", False),
])
def test_device_types(plugin, dtype, shown):
    p, bridge, state = plugin
    state["player"] = playback(dtype)
    run(p, 1000)
    msg = bridge.last({"frame", "release"})
    assert (msg is not None and msg["type"] == "frame") == shown
    if not shown:
        assert "Display bleibt aus" in bridge.last({"status"})["text"]


def test_switching_from_pc_to_phone_releases(plugin):
    p, bridge, state = plugin
    state["player"] = playback("Computer", "PC")
    run(p, 1000)
    assert bridge.last({"frame", "release"})["type"] == "frame"
    state["player"] = playback("Smartphone", "iPhone")
    run(p, 1010)
    assert bridge.last({"frame", "release"})["type"] == "release"


def test_name_rules(plugin):
    p, bridge, state = plugin
    p.config["exclude_devices"] = "arbeitslaptop, Büro"
    p.config["include_devices"] = "Tims iPad"
    assert not mod.device_allowed({"name": "Arbeitslaptop", "type": "Computer"}, p.config)
    assert mod.device_allowed({"name": "tims ipad", "type": "Tablet"}, p.config)
    assert not mod.device_allowed({"name": "Schul-iPad", "type": "Tablet"}, p.config)


def test_pause_grace_then_release(plugin):
    p, bridge, state = plugin
    state["player"] = playback("Computer", playing=False)
    run(p, 1000)
    assert bridge.last({"frame", "release"})["type"] == "frame"
    run(p, 1005)
    assert bridge.last({"frame", "release"})["type"] == "frame"
    run(p, 1011)
    assert bridge.last({"frame", "release"})["type"] == "release"


def test_nothing_playing(plugin):
    p, bridge, state = plugin
    run(p, 1000)
    assert bridge.last({"frame"}) is None
    assert bridge.last({"status"})["text"] == "Gerade läuft nichts."


def test_progress_bar_drawn(plugin):
    p, bridge, state = plugin
    state["player"] = playback("Computer")
    run(p, 1000)
    import base64
    frame = base64.b64decode(bridge.last({"frame"})["frames"][0])
    px = lambda x, y: tuple(frame[(y * 64 + x) * 3:(y * 64 + x) * 3 + 3])
    assert px(5, 63) == p.bar_color            # 25% played -> first 16 columns filled
    assert px(40, 63) != p.bar_color
    assert px(10, 30)[0] > 150                  # the red cover


def test_connect_requires_credentials(plugin):
    p, _, _ = plugin
    r = p.on_action("connect", {"client_id": "", "client_secret": ""})
    assert not r["ok"]
    r = p.on_action("connect", {"client_id": "abc", "client_secret": "x", "redirect_uri": "http://127.0.0.1:8888/callback"})
    assert r["ok"] and "client_id=abc" in r["open_url"] and "state=" in r["open_url"]


def test_finish_rejects_foreign_state(plugin):
    p, _, _ = plugin
    p.on_action("connect", {"client_id": "abc", "client_secret": "x", "redirect_uri": "u"})
    r = p.on_action("finish", {"callback_url": "http://127.0.0.1:8888/callback?code=c&state=wrong",
                               "client_id": "abc", "client_secret": "x", "redirect_uri": "u"})
    assert not r["ok"]


def test_missing_credentials_reported(tmp_path):
    bridge = Bridge()
    p = mod.Spotify("spotify", dict(DEFAULTS), str(tmp_path), bridge)
    p.setup()
    p.tick()
    st = bridge.last({"status"})
    assert st["level"] == "warn" and "Client ID" in st["text"]

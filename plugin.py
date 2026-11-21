"""Spotify cover art for Pixoo Hub.

Polls the Spotify Web API for the current playback and shows the album cover
with an optional progress bar. Playback on devices the user excluded (by
default smartphones and tablets) never lights up the display.
"""

from __future__ import annotations

import base64
import secrets
import time
from io import BytesIO
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from PIL import Image, ImageEnhance

from pixoohub.sdk import ActionResult, Plugin

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API = "https://api.spotify.com/v1"
SCOPES = "user-read-playback-state user-read-currently-playing"
SPOTIFY_GREEN = (30, 215, 96)

DEVICE_TYPE_DE = {
    "Computer": "Computer", "Smartphone": "Smartphone", "Tablet": "Tablet", "Speaker": "Lautsprecher",
    "TV": "Fernseher", "AVR": "AV-Receiver", "STB": "Set-Top-Box", "AudioDongle": "Audio-Dongle",
    "GameConsole": "Spielkonsole", "CastVideo": "Chromecast", "CastAudio": "Chromecast Audio",
    "Automobile": "Auto", "Unknown": "unbekanntes Gerät",
}


class AuthError(Exception):
    """Credentials are missing or were rejected; user action needed."""


def _names(text: str) -> set:
    return {n.strip().casefold() for n in (text or "").split(",") if n.strip()}


def device_allowed(device: dict, config: dict) -> bool:
    """Decide whether playback on `device` may light up the display."""
    name = (device.get("name") or "").casefold()
    if name and name in _names(config.get("exclude_devices", "")):
        return False
    if name and name in _names(config.get("include_devices", "")):
        return True
    allowed = config.get("show_on_types")
    if not isinstance(allowed, list):
        allowed = []
    return (device.get("type") or "Unknown") in allowed


def vibrant_color(img: Image.Image) -> tuple:
    """Most prominent saturated, reasonably bright color of an image."""
    small = img.convert("RGB").resize((24, 24))
    best, best_score = None, 0.0
    for count, (r, g, b) in small.getcolors(24 * 24) or []:
        hi, lo = max(r, g, b), min(r, g, b)
        sat = (hi - lo) / hi if hi else 0
        if hi < 90 or sat < 0.35:
            continue
        score = count * sat * (hi / 255)
        if score > best_score:
            best, best_score = (r, g, b), score
    return best or SPOTIFY_GREEN


class Spotify(Plugin):
    interval = 1.0

    def setup(self):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "PixooHub-Spotify/2"
        self.access_token: Optional[str] = None
        self.token_expires = 0.0

        self.playback: Optional[dict] = None   # last API answer
        self.polled_at = 0.0
        self.next_poll = 0.0
        self.paused_since: Optional[float] = None

        self.cover_url: Optional[str] = None
        self.cover: Optional[Image.Image] = None
        self.bar_color = SPOTIFY_GREEN
        self.last_frame: Optional[bytes] = None
        self.showing = False
        self.problem: Optional[str] = None  # auth problem the user must fix

        if not self.cfg("client_id") or not self.cfg("client_secret"):
            self.status("Client ID und Client Secret fehlen – siehe Einstellungen.", "warn")
        elif not self._refresh_token():
            self.status("Noch nicht mit Spotify verbunden – Knopf 'Mit Spotify verbinden' benutzen.", "warn")

    # ---------------------------------------------------------------- auth
    def _refresh_token(self) -> str:
        stored = self.storage.get("auth") or {}
        if stored.get("refresh_token") and stored.get("client_id") == self.cfg("client_id"):
            return stored["refresh_token"]
        return self.cfg("refresh_token", "")

    def _basic_auth(self, client_id: str, client_secret: str) -> dict:
        raw = f"{client_id}:{client_secret}".encode()
        return {"Authorization": "Basic " + base64.b64encode(raw).decode()}

    def _ensure_token(self) -> str:
        if self.access_token and time.time() < self.token_expires - 60:
            return self.access_token
        cid, secret, refresh = self.cfg("client_id"), self.cfg("client_secret"), self._refresh_token()
        if not (cid and secret):
            raise AuthError("Client ID und Client Secret fehlen.")
        if not refresh:
            raise AuthError("Noch nicht mit Spotify verbunden.")
        r = self.session.post(TOKEN_URL, data={"grant_type": "refresh_token", "refresh_token": refresh},
                              headers=self._basic_auth(cid, secret), timeout=10)
        if r.status_code in (400, 401):
            raise AuthError(f"Spotify lehnt die Zugangsdaten ab ({r.json().get('error_description', r.status_code)}). Bitte neu verbinden.")
        r.raise_for_status()
        data = r.json()
        self.access_token = data["access_token"]
        self.token_expires = time.time() + int(data.get("expires_in", 3600))
        if data.get("refresh_token"):  # Spotify may rotate it
            self.storage.set("auth", {"client_id": cid, "refresh_token": data["refresh_token"]})
        return self.access_token

    # -------------------------------------------------------------- actions
    def on_action(self, name, values):
        if name == "connect":
            return self._action_connect(values)
        if name == "finish":
            return self._action_finish(values)
        if name == "which_device":
            return self._action_which_device()
        return super().on_action(name, values)

    def _action_connect(self, values):
        cid = (values.get("client_id") or "").strip()
        if not cid or not values.get("client_secret"):
            return ActionResult("Erst Client ID und Client Secret eintragen.", ok=False)
        state = secrets.token_urlsafe(16)
        self.storage.set("pending_state", state)
        url = AUTH_URL + "?" + urlencode({
            "client_id": cid, "response_type": "code", "redirect_uri": values.get("redirect_uri"),
            "scope": SCOPES, "state": state, "show_dialog": "true",
        })
        return ActionResult("Spotify-Anmeldung geöffnet. Danach die Adresse aus der Adresszeile unten einfügen.", open_url=url)

    def _action_finish(self, values):
        raw = (values.get("callback_url") or "").strip()
        if not raw:
            return ActionResult("Bitte zuerst die Adresse nach der Anmeldung einfügen.", ok=False)
        q = parse_qs(urlparse(raw).query)
        if "error" in q:
            return ActionResult(f"Spotify meldet: {q['error'][0]}", ok=False)
        code = (q.get("code") or [None])[0]
        if not code:
            return ActionResult("In der Adresse steht kein 'code=' – bitte die komplette Adresse kopieren.", ok=False)
        expected = self.storage.get("pending_state")
        if expected and (q.get("state") or [None])[0] != expected:
            return ActionResult("Die Adresse gehört zu einer älteren Anmeldung. Bitte Schritt 1 wiederholen.", ok=False)
        cid, secret = values.get("client_id", "").strip(), values.get("client_secret", "")
        r = self.session.post(TOKEN_URL, data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": values.get("redirect_uri"),
        }, headers=self._basic_auth(cid, secret), timeout=10)
        if not r.ok:
            try:
                err = r.json().get("error_description") or r.json().get("error")
            except ValueError:
                err = r.status_code
            return ActionResult(f"Token-Abruf fehlgeschlagen: {err}", ok=False)
        data = r.json()
        self.storage.set("auth", {"client_id": cid, "refresh_token": data["refresh_token"]})
        self.storage.delete("pending_state")
        me = self.session.get(API + "/me", headers={"Authorization": "Bearer " + data["access_token"]}, timeout=10)
        who = me.json().get("display_name") if me.ok else None
        msg = f"Verbunden{' als ' + who if who else ''}."
        if cid != self.cfg("client_id") or secret != self.cfg("client_secret"):
            msg += " Jetzt noch 'Einstellungen speichern' drücken."
        return ActionResult(msg, values={"callback_url": ""})

    def _action_which_device(self):
        try:
            token = self._ensure_token()
        except AuthError as e:
            return ActionResult(str(e), ok=False)
        r = self.session.get(API + "/me/player/devices", headers={"Authorization": "Bearer " + token}, timeout=10)
        r.raise_for_status()
        devices = r.json().get("devices", [])
        if not devices:
            return ActionResult("Spotify kennt gerade keine aktiven Geräte. Starte die Wiedergabe und versuch es nochmal.")
        parts = []
        for d in devices:
            verdict = "würde angezeigt" if device_allowed(d, self.config) else "bleibt dunkel"
            mark = "▶ " if d.get("is_active") else ""
            parts.append(f"{mark}{d.get('name')} ({d.get('type')}) – {verdict}")
        return ActionResult("; ".join(parts) + ". (Bewertet mit den gespeicherten Regeln.)")

    # ------------------------------------------------------------------ loop
    def tick(self):
        now = time.time()
        if now >= self.next_poll:
            self._poll(now)
        self._render(now)
        return 1.0

    def _poll(self, now: float) -> None:
        interval = max(2, self.cfg("poll_interval", 3, int))
        self.next_poll = now + interval
        try:
            token = self._ensure_token()
        except AuthError as e:
            self.playback = None
            self.problem = str(e)
            self.next_poll = now + 60
            return
        self.problem = None
        r = self.session.get(API + "/me/player", params={"additional_types": "episode"},
                             headers={"Authorization": "Bearer " + token}, timeout=10)
        if r.status_code == 204:
            self.playback = None
        elif r.status_code == 401:
            self.access_token = None
            return
        elif r.status_code == 429:
            wait = int(r.headers.get("Retry-After", "30"))
            self.next_poll = now + wait
            self.status(f"Spotify bremst die Abfragen – nächste in {wait}s.", "warn")
            return
        else:
            r.raise_for_status()
            self.playback = r.json()
        self.polled_at = now

    def _render(self, now: float) -> None:
        pb = self.playback
        item = pb.get("item") if pb else None
        device = (pb or {}).get("device") or {}

        if self.problem:
            self._hide(self.problem, "warn")
            return
        if not pb or not item:
            self.paused_since = None
            self._hide("Gerade läuft nichts.")
            return

        title = item.get("name", "?")
        if not device_allowed(device, self.config):
            kind = DEVICE_TYPE_DE.get(device.get("type"), device.get("type") or "?")
            self._hide(f"„{title}“ läuft auf {device.get('name', '?')} ({kind}) – Display bleibt aus.")
            return

        if not pb.get("is_playing"):
            if self.paused_since is None:
                self.paused_since = now
            if now - self.paused_since >= self.cfg("pause_grace", 10, float):
                self._hide(f"Pausiert: {title}")
                return
        else:
            self.paused_since = None

        self._load_cover(item)
        frame = self.cover.copy() if self.cover else self._placeholder(title)

        if self.cfg("show_progress", True, bool) and item.get("duration_ms"):
            progress = pb.get("progress_ms") or 0
            if pb.get("is_playing"):
                progress += (now - self.polled_at) * 1000
            self._draw_progress(frame, min(1.0, progress / item["duration_ms"]))

        data = frame.tobytes()
        if data != self.last_frame or not self.showing:
            self.show(frame)
            self.last_frame = data
            self.showing = True
        artist = ", ".join(a.get("name", "") for a in item.get("artists", [])) or item.get("show", {}).get("name", "")
        state = "▶" if pb.get("is_playing") else "❚❚"
        self.status(f"{state} {title} – {artist} · {device.get('name', '')}")

    def _hide(self, why: str, level: str = "info") -> None:
        if self.showing:
            self.release()
            self.showing = False
            self.last_frame = None
        self.status(why, level)

    # ---------------------------------------------------------------- image
    def _load_cover(self, item: dict) -> None:
        images = item.get("album", {}).get("images") or item.get("images") or []
        if not images:
            self.cover_url, self.cover = None, None
            return
        # smallest image that is still at least 64px, else the largest
        images = sorted(images, key=lambda i: i.get("width") or 0)
        pick = next((i for i in images if (i.get("width") or 0) >= 64), images[-1])
        if pick["url"] == self.cover_url:
            return
        try:
            r = self.session.get(pick["url"], timeout=10)
            r.raise_for_status()
            img = Image.open(BytesIO(r.content)).convert("RGB")
        except Exception as e:
            self.log.warning("cover download failed: %s", e)
            self.cover_url, self.cover = pick["url"], None
            return
        img = img.resize((64, 64), Image.LANCZOS)
        # LEDs wash out mid tones; a little extra saturation keeps covers recognizable
        img = ImageEnhance.Color(img).enhance(1.15)
        self.cover_url, self.cover = pick["url"], img
        self.bar_color = vibrant_color(img)

    def _draw_progress(self, img: Image.Image, fraction: float) -> None:
        px = img.load()
        filled = round(fraction * 64)
        for x in range(64):
            for y in (62, 63):
                if x < filled:
                    px[x, y] = self.bar_color
                else:
                    r, g, b = px[x, y]
                    px[x, y] = (r // 3, g // 3, b // 3)

    def _placeholder(self, title: str) -> Image.Image:
        from pixoohub.sdk import wrap
        img = self.canvas()
        lines = wrap(title, 60)[:6]
        y = max(4, (64 - len(lines) * 7) // 2)
        for i, line in enumerate(lines):
            self.text(img, line, (2, y + i * 7), SPOTIFY_GREEN if i == 0 else (200, 200, 200))
        return img

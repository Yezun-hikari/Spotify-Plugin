# Spotify for Pixoo Hub

Shows the cover of the song you're playing on your Pixoo 64, with an optional progress bar
in the cover's accent color.

It only lights up when Spotify plays on a device you want: by default **not** when the
music runs on a smartphone or tablet. Listening on your phone on the go, in bed, or on the
iPad at school leaves the display dark. Playing on the PC or a speaker at home shows the
cover. The rules can be refined per device name.

Requires Pixoo Hub 2.

## Setup

1. Open the [Spotify developer dashboard](https://developer.spotify.com/dashboard) and
   create an app. Tick **Web API**, and add `http://127.0.0.1:8888/callback` as redirect URI.
2. Copy **Client ID** and **Client Secret** into the plugin settings in Pixoo Hub.
3. Press **1. Mit Spotify verbinden** and log in. Spotify then sends you to
   `http://127.0.0.1:8888/callback?code=…` — that page won't load, which is expected.
   Copy the full address from the address bar into the field below the button.
4. Press **2. Verbindung abschließen**, then **Einstellungen speichern**.

The refresh token is stored in the plugin's private storage, not in the settings.

## Which device lights up the display

Spotify reports the active device with a name and a type (`Computer`, `Smartphone`,
`Tablet`, `Speaker`, `TV`, …).

- **Gerätetypen**: the cover is shown only if the device type is ticked.
  Default: everything except smartphone, tablet and car.
- **Immer ignorieren**: device names that never light up the display.
- **Immer anzeigen**: device names that always do, whatever their type.

**Welches Gerät spielt gerade?** lists Spotify's current devices and whether each one
would be shown — handy for finding the exact names.

## Settings

| | |
|---|---|
| Fortschrittsbalken | 1-pixel bar on the bottom row, over the two darkened bottom rows |
| Nach Pause noch anzeigen | keep the cover for a few seconds after pausing (default 10) |
| Spotify abfragen alle | poll interval, 2–60 s (default 3) |
| Refresh-Token | only for tokens from version 1; otherwise use the connect button |

## Development

```bash
PYTHONPATH=../Pixoo64-Marketplace python -m pytest
```

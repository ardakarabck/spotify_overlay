# Spotify Now Playing — Stream Overlay

A single-file browser overlay that displays the track currently playing on your
Spotify account. Built for OBS and Streamlabs, used on Kick.

**Live:** https://ardakarabck.github.io/spotify_overlay/

No server, no subscription, no third-party service. The page talks directly to
the Spotify Web API from your browser.

---

## What it shows

- Album cover art, rotating while playback is active
- Track title and artist
- Progress bar and elapsed / total time
- Slides out of view automatically when nothing is playing

The timer advances one second at a time even though Spotify is only polled every
three seconds — see [How the timer works](#how-the-timer-works).

---

## Setup

### 1. Host it

The overlay is already deployed via GitHub Pages from `index.html` on the `main`
branch. To run your own copy, fork this repo and enable **Settings → Pages →
Deploy from a branch → main → / (root)**.

`.nojekyll` is required. Without it GitHub runs Jekyll over the repo and serves a
generated page instead of the overlay.

### 2. Create a Spotify app

1. Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) → **Create app**
2. **Redirect URI:** your Pages URL, exactly — including the trailing slash
3. Under APIs, select **Web API**
4. Save, then copy the **Client ID**

Name the app something that doesn't begin with "Spot" and doesn't imply Spotify
endorsement — this is required by the Spotify Branding Guidelines.

### 3. Connect

Open the overlay in a normal browser, paste your Client ID, and click
**Connect Spotify**. The login is remembered, so this is a one-time step.

### 4. Add to OBS / Streamlabs

**Sources → + → Browser**, then:

| Setting | Value |
|---|---|
| URL | your Pages URL |
| Width | 480 |
| Height | 160 |

Kick broadcasts whatever OBS outputs, so nothing further is needed on Kick's side.

> **After every change to the overlay**, right-click the browser source →
> **Refresh cache of current page**. OBS caches aggressively and will keep
> showing an old version otherwise.

---

## When the browser source can't reach Spotify

The overlay normally talks to Spotify straight from the browser source. On some
machines that stops working: the embedded Chromium in Streamlabs Desktop and OBS
fails the TLS handshake with `accounts.spotify.com` and shows
`ERR_SSL_PROTOCOL_ERROR`, while curl, Chrome and Python on the very same machine
reach that host without complaint.

The symptom is the card sitting on **Reconnecting…** roughly an hour after the
overlay starts. That is the access token expiring with no way to refresh it.

`helper.py` moves the part that needs TLS out of the browser source. It holds the
refresh token, talks to Spotify over Python's own TLS stack, and serves the
overlay plus a `/nowplaying` endpoint on loopback. The browser source then only
speaks plain HTTP to `127.0.0.1`, where there is no handshake to get wrong.

Standard library only — no `pip install`.

### Setup

1. In your Spotify app, add a second **Redirect URI**, exactly:
   `http://127.0.0.1:8765/callback`
2. Run it:
   ```
   python helper.py
   ```
   The first run asks for your Client ID and opens a normal browser to log in.
   Both are saved to `helper_config.json` — gitignored, because it holds a live
   refresh token.
3. Point the browser source at `http://127.0.0.1:8765/` instead of the Pages URL.
4. Leave it running while you stream.

| Flag | |
|---|---|
| `--port 8766` | if 8765 is taken — change the Redirect URI to match |
| `--reauth` | discard the stored login and log in again |

On Windows, **`start_overlay.bat`** does the same from a double-click. It runs
`helper.py` from its own folder, so a desktop shortcut to it works from
anywhere, and it holds the window open after the helper stops so a startup
error is readable instead of vanishing with the console. Flags pass through, so
a shortcut can carry `--reauth` or `--port` in its Target.

`index.html` notices it is being served from localhost and reads `/nowplaying`
instead of calling Spotify itself. The same file still works unchanged on GitHub
Pages, so the hosted setup above is untouched.

This also fixes a subtler failure. Spotify rotates the refresh token on every
refresh and invalidates the one just used, so two copies of the hosted overlay on
one account — a browser source and a forgotten browser tab, say — will knock each
other offline. One helper process owns the token, so there is no race.

---

## Customizing

All styling lives in the `:root` block at the top of `index.html`:

```css
--accent: #1DB954;           /* progress bar and highlights */
--bg: rgba(18,18,18,0.85);   /* card background and opacity */
--radius: 16px;              /* corner rounding */
```

To reposition the card, edit `#overlay`:

```css
position:fixed; left:20px; top:20px;      /* current: top-left */
transform:translateY(-140%);              /* slide-in direction */
```

Use `bottom:20px` with `translateY(140%)` to anchor it to the bottom instead —
the transform sign has to match, or the card slides in from the wrong edge.

---

## How the timer works

Polling Spotify once per second risks rate limiting, but polling every three
seconds makes the clock jump `0:01 → 0:04 → 0:07`. The overlay solves this with
client-side interpolation.

Each poll records an anchor — the reported position and the local time it
arrived:

```js
pbProgress = d.progress_ms;
pbStamp    = performance.now();
pbPlaying  = d.is_playing;
```

A 250 ms ticker then predicts forward from that anchor:

```js
let cur = pbProgress;
if (pbPlaying) cur += performance.now() - pbStamp;
```

The poll is the source of truth; the ticker is a prediction. Since playback
advances at exactly 1 ms per 1 ms, the prediction is near-perfect, and each poll
resets the anchor so error never accumulates.

Two details that matter: `performance.now()` is used rather than `Date.now()`
because it's monotonic and unaffected by system clock changes, and the ticker
runs at 250 ms rather than 1000 ms because a one-second interval drifts out of
phase with the actual second boundary and visibly stutters.

---

## Privacy and permissions

The overlay requests two read-only scopes:

- `user-read-currently-playing`
- `user-read-playback-state`

It cannot control playback, and has no access to your profile, playlists,
library, or listening history.

Authentication uses the Authorization Code flow with PKCE, so no client secret is
needed and nothing sensitive is stored in this repository. Your Client ID and
refresh token are kept in your browser's `localStorage` and never leave your
device except when sent to Spotify.

Under the helper, those same two values live in `helper_config.json` on your
machine instead of in `localStorage`, and the browser source holds nothing at
all.

**To disconnect:** hover over the page and click **Disconnect Spotify**, or open
the overlay with `?disconnect=1` appended. This erases all stored values
immediately. Under the helper, stop it and delete `helper_config.json`. You can
additionally revoke access from your Spotify account page under **Apps**.

Full details in [PRIVACY.md](PRIVACY.md).

---

## Music licensing

The overlay itself only reads and displays metadata, and carries the attribution
required by the Spotify Developer Policy. The audio you broadcast is a separate
matter.

Spotify Premium is a personal, non-commercial licence, and broadcasting it to an
audience falls outside those terms. Kick's own terms require you to hold the
rights to whatever you broadcast, and its DMCA policy reserves removal of content
and termination of accounts.

Playing stream-licensed labels reduces the practical risk considerably, since the
parties who would otherwise complain actively want streamers using their catalog:

| Source | Licence |
|---|---|
| NCS (NoCopyrightSounds) | Free for streams **with attribution** |
| Monstercat | Requires paid **Monstercat Gold** |
| Chillhop Records | Varies by track — check their terms |

Verify each label's current terms yourself. "No copyright" in a channel name is
marketing, not a licence.

---

## Attribution

Music metadata and cover art are supplied by Spotify. Cover art links back to the
corresponding track on the Spotify Service. Spotify is a trademark of Spotify AB.
This project is not affiliated with or endorsed by Spotify AB.
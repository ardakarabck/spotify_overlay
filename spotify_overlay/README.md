# Spotify Now-Playing Overlay — Setup

A self-contained overlay that shows your current Spotify track (album art, title,
artist, animated progress bar) on your Kick stream. No monthly service, no third party —
it talks directly to Spotify from your own browser source.

---

## Step 1 — Host the file (pick ONE)

The overlay needs a real URL for Spotify's login to redirect back to. Two easy options:

**A. GitHub Pages (free, recommended)**
1. Create a free GitHub account, make a new **public** repo.
2. Upload `spotify-overlay.html`, rename it to `index.html`.
3. Repo → **Settings → Pages** → Source: `main` branch → Save.
4. After a minute you get a URL like `https://YOURNAME.github.io/REPO/`. That's your overlay URL.

**B. Local (test on your own machine)**
1. Put `spotify-overlay.html` in a folder.
2. In that folder run: `python -m http.server 8080`
3. Your overlay URL is `http://localhost:8080/spotify-overlay.html`
   (Local works for testing, but GitHub Pages is more reliable inside OBS.)

> Opening the file directly with `file://` will NOT work — Spotify rejects `file://` redirects.

---

## Step 2 — Create a Spotify app (one-time)

1. Go to **developer.spotify.com/dashboard** → log in → **Create app**.
2. Name/description: anything. **APIs used:** Web API.
3. **Redirect URI:** paste the *exact* overlay URL from Step 1
   (the setup screen also displays the exact value to use).
4. Save. Open the app → **Settings** → copy the **Client ID**.

---

## Step 3 — Connect

1. Open your overlay URL in a normal browser (Chrome/Edge).
2. Paste your **Client ID** → **Connect Spotify** → approve.
3. It redirects back and starts showing your current track. Done — the login is
   remembered, so you won't repeat this.

---

## Step 4 — Add to OBS / Streamlabs (for Kick)

1. In OBS: **Sources → + → Browser**.
2. URL = your overlay URL. Width **480**, Height **160** (adjust to taste).
3. Position it wherever you like on your canvas.
4. Kick captures whatever OBS outputs, so once it's in OBS it's on your Kick stream.

---

## Customizing the look

Open `spotify-overlay.html` in any text editor. At the very top, in the `:root` block,
change these:

```
--accent: #1DB954;   /* bar + glow color — set to your brand color */
--bg: rgba(18,18,18,0.85);  /* card background + transparency */
--radius: 16px;      /* corner roundness */
```

The card sits bottom-left by default. To move it, find `#overlay` and change
`left:20px; bottom:20px;` (e.g. `right:20px; top:20px;` for top-right).

---

## Notes

- The album art spins while a song is playing and stops when paused.
- When nothing is playing, the card slides out of view automatically.
- Your Client ID and login token live only in that browser's localStorage —
  nothing is sent anywhere except Spotify's own servers.
- If it ever stops updating, re-open the overlay URL in a browser once to refresh the login.
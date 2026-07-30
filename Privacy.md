# Privacy Policy — Spotify Now Playing Overlay

**Last updated:** 30 July 2026

This page explains what data the Spotify Now Playing Overlay ("the Overlay")
accesses and how it is handled. It is provided to meet the privacy policy
requirement in Section I.1.1 of the Spotify Developer Policy.

## Who runs this

The Overlay is a personal, non-commercial project operated by its individual
user. It is not affiliated with, endorsed by, or sponsored by Spotify AB.

## What data is accessed

When you connect your Spotify account, the Overlay requests two read-only
permissions:

- `user-read-currently-playing`
- `user-read-playback-state`

These allow it to read **the track currently playing on your account** —
title, artist, album cover art, track length, and playback position.

The Overlay does **not** request, and cannot access:

- your email address, name, or profile details
- your playlists, library, or listening history
- your password or payment information
- the ability to control, start, stop, or alter playback

## Where the data goes

Nowhere. There is no server, no database, and no analytics.

- All requests go directly from your browser to Spotify's API.
- Track information is held in browser memory only, to draw it on screen.
- It is overwritten on each refresh and discarded when the page closes.
- No data is transmitted to the operator or to any third party.

## What is stored

Three values are saved in your browser's `localStorage`, on your own device:

| Key | Purpose |
|---|---|
| `sp_client_id` | Your Spotify application's Client ID |
| `sp_refresh` | Refresh token, so you don't re-authorize on every load |
| `sp_verifier` | Temporary PKCE value used during login |

These never leave your device except when sent to Spotify to renew your session.

## Disconnecting and deleting your data

You may disconnect at any time:

1. **In the Overlay** — hover over the page and click **Disconnect Spotify**.
   You can also open the Overlay with `?disconnect=1` appended to its address.
2. **On Spotify** — go to your Spotify account page → **Apps** →
   **Remove Access** for this application.

Disconnecting erases every stored value listed above from your browser
immediately, and the Overlay stops making any requests to Spotify. Because
nothing is stored anywhere else, no further deletion is necessary or possible.

## Attribution

All music metadata and cover art shown by the Overlay is supplied by Spotify.
Cover art links back to the corresponding track on the Spotify Service.
Spotify is a trademark of Spotify AB.

## Children

The Overlay is not directed at children and is not intended for use by anyone
under the age required to hold a Spotify account in their country.

## Changes

Any change to this policy will be published on this page with a revised date.

## Contact

Questions about this policy can be directed to the repository operator through
the project's GitHub repository.
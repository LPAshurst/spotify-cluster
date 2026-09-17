# Spotify Playlist Genre + K-Means Clusterer

Splits a big Spotify playlist into smaller ones by **master genre first**,
then by **audio-feature K-Means clusters within each genre** if that genre
has enough tracks to make sub-splitting worthwhile.

## How it's organized

| File | Responsibility |
|---|---|
| `config.py` | All the knobs — playlist ID, thresholds, feature list, file paths |
| `spotify_client.py` | Auth, the `/me/playlists` workaround, playlist read/write helpers |
| `audio_features.py` | Pulls acousticness/energy/tempo/etc. from ReccoBeats |
| `genre.py` | Pulls a raw genre-ish tag per track from Last.fm, maps it to a master genre |
| `clustering.py` | Builds genre buckets, sub-clusters big ones with K-Means, names them |
| `state.py` | Load/save `cluster_state.json` |
| `main.py` | Entry point — wires the above together |

## Setup

1. **Spotify app** — create one at https://developer.spotify.com/dashboard,
   add `http://localhost:8888/callback` as a redirect URI, grab the client
   ID/secret. If it's in Development Mode, add your own account under
   *User Management* in the app settings.
2. **Last.fm API key** — free, no OAuth: https://www.last.fm/api/account/create
3. Copy `.env.example` to `.env` and fill in both sets of credentials.
4. Edit `PLAYLIST_ID` in `config.py` to your source playlist's ID (just the
   ID — the part after `/playlist/` and before any `?`).
5. `pip install -r requirements.txt`
6. `python main.py`

Run it again later (cron, weekly, whatever) and it'll only process tracks
it hasn't seen before, routing each into the right genre/cluster playlist
automatically.

## How the genre logic works

Genre tagging happens in two layers, on purpose:

1. **Raw tag fetch** (`genre.py`, `get_top_tag`/`get_artist_top_tag`) — asks
   Last.fm for the track's top community tag, falling back to the artist's
   top tag if the track itself has none. This is free and needs no OAuth,
   but the tags are crowd-sourced folksonomy — they mix real genres with
   mood/decade noise ("2010s", "favorites"), which `TAG_BLOCKLIST` filters
   out.
2. **Raw tag → master genre** (`classify_genre`, cached in `genre_map.json`)
   — a small ordered keyword table buckets whatever Last.fm returns into
   one of ~15 master genres. Anything unmatched lands in `"Other"`.

The mapping is cached per unique raw tag, not per track — a library of 1,500
tracks might only produce 100–300 distinct tags, and each one only ever gets
classified once, the same way `seen_track_ids` avoids re-fetching audio
features you already have.

**After a run, check `genre_map.json` for anything mapped to `"Other"`.**
Either add a keyword to `GENRE_KEYWORDS` in `genre.py`, or hand-edit that
one entry directly (e.g. `"vaporwave": "Electronic"`) — it'll stick for
every future run.

### Swapping in a paid, single-label genre source

If Last.fm's noisy tags aren't cutting it, **SoundStat**
(https://soundstat.info) takes a Spotify track ID and returns one clean
`genre` field directly (plus its own audio-feature analysis, as a bonus).
It's billed per unique track analyzed beyond a small free tier, so budget
for your library size. To swap it in: replace `get_top_tag`/
`get_artist_top_tag` in `genre.py` with a call to SoundStat's track endpoint,
and drop the blocklist/fallback logic entirely — there's only one tag to
pick, so `classify_genre` runs on that instead.

## How the clustering logic works

For each master genre bucket:

- **Under `SUBCLUSTER_THRESHOLD` tracks** (default 60) — one playlist, no
  K-Means. Not enough data for meaningful sub-clusters.
- **At or above the threshold** — K-Means on the same audio features as
  before (`FEATURE_COLS` in `config.py`), scaled per-bucket, with cluster
  count scaled to bucket size (`min(NUM_CLUSTERS, tracks // 30)`, floor of
  2). Each sub-cluster gets named the same way as before (`name_cluster` in
  `clustering.py`) and becomes its own playlist, e.g. `Pop — Upbeat Dance
  (42)`.

`cluster_state.json` now nests everything under `genre_buckets`, keyed by
master genre, so incremental runs look up the right scaler/centers/playlist
IDs for a track's specific genre before deciding where it goes. A genre
that's never shown up before gets a fresh bucket built on the spot,
mid-run.

## Skipped tracks

Two things get pulled out before clustering, for different reasons:

- **Local files / id-less items** — tracks added to the playlist from your
  own computer rather than Spotify's catalog come back from the API with
  `id: null`. They can't be fetched from ReccoBeats or added to a playlist
  by URI, so they're filtered out in `get_playlist_tracks` and reported to
  stdout each run. Not persisted anywhere, since there's no stable ID to
  track them by — they'll just get reported again next time if they're
  still in the source playlist.
- **No audio features available** — if ReccoBeats has nothing for a track,
  it's recorded in `cluster_state.json` under `skipped_no_features` so it
  isn't retried (and re-logged) on every single run forever. Run
  `python main.py --retry-skipped` any time you want to re-check all of
  them — useful after ReccoBeats' catalog has had time to grow.

## Known caveats

- **Spotify's Feb 2026 Web API migration** removed
  `POST /users/{user_id}/playlists` for Development Mode apps (as of March
  2026, it 403s unconditionally). `spotify_client.create_playlist()` already
  routes around this via `POST /me/playlists`. If `playlist_add_items` ever
  starts 403ing too, Spotify's migration guide is the first place to check —
  they've also been moving playlist-content endpoints from `/tracks` to
  `/items`.
- **ReccoBeats coverage isn't 100%** — some tracks won't have audio features
  available and get silently skipped (logged to stdout). That's unchanged
  from the original script.
- **Last.fm rate limiting** — `attach_genres` sleeps 0.25s between tracks to
  stay well under Last.fm's limits. For a very large first run (thousands of
  tracks) this adds real wall-clock time; that's the trade-off for a free,
  no-OAuth genre source.
- **Spotify's own artist `genres` field** was considered and skipped — it's
  been unreliable for many artists since a still-unresolved bug (empty or
  stripped genre lists), and it's assigned per-artist rather than per-track
  anyway.

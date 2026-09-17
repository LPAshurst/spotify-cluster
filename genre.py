import json
import os
import time

import requests
from tqdm import tqdm

import config
from spotify_client import get_artist_genres

# ---------------------------------------------------------------------------
# This module's job: for every track, build a weighted {tag: weight} dict
# combining four signals:
#
#   1. Last.fm track tags       — most specific, per-song
#   2. Last.fm artist tags      — per-artist, cached
#   3. Spotify artist genres    — per-artist, cached
#   4. MusicBrainz artist genres — per-artist, cached
#
# clustering.py turns these dicts into vectors and runs clustering on them —
# this file never buckets anything itself, it just gathers and weights tags.
#
# Sources 2-4 are all per-artist, so they're cached to disk
# (config.TAG_CACHE_FILE) once computed. A library of ~1,000 tracks might
# only have 200-400 distinct artists, and on later incremental runs almost
# all of those artists are already cached — only genuinely new artists pay
# the MusicBrainz/Spotify lookup cost again.
# ---------------------------------------------------------------------------


def _clean(tag):
    tag = tag.lower().strip()
    return tag if tag and tag not in config.TAG_BLOCKLIST else None


def load_tag_cache():
    if os.path.exists(config.TAG_CACHE_FILE):
        with open(config.TAG_CACHE_FILE) as f:
            return json.load(f)
    return {}


def save_tag_cache(cache):
    with open(config.TAG_CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


# ---------------------------------------------------------------------------
# Last.fm
# ---------------------------------------------------------------------------
def _lastfm_top_tags(params):
    if not config.LASTFM_API_KEY:
        return []
    params = {**params, "api_key": config.LASTFM_API_KEY, "format": "json", "autocorrect": 1}
    try:
        resp = requests.get(config.LASTFM_API_URL, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json().get("toptags", {}).get("tag", [])
    except requests.RequestException:
        return []


def _weighted_tags(raw_tags, limit, weight):
    out = {}
    for tag in raw_tags:
        name = _clean(tag.get("name", ""))
        if not name:
            continue
        count = tag.get("count", 0)  # Last.fm counts are already 0-100 relative weights
        out[name] = (count / 100) * weight
        if len(out) >= limit:
            break
    return out


def lastfm_track_tags(track_name, artist_name):
    raw = _lastfm_top_tags({"method": "track.getTopTags", "artist": artist_name, "track": track_name})
    return _weighted_tags(raw, config.LASTFM_TRACK_TAG_LIMIT, config.LASTFM_TRACK_TAG_WEIGHT)


def lastfm_artist_tags(artist_name):
    raw = _lastfm_top_tags({"method": "artist.getTopTags", "artist": artist_name})
    return _weighted_tags(raw, config.LASTFM_ARTIST_TAG_LIMIT, config.LASTFM_ARTIST_TAG_WEIGHT)


# ---------------------------------------------------------------------------
# MusicBrainz — search for the artist's MBID, then look up its curated
# genre list. Two requests per new (uncached) artist, each rate-limited.
# ---------------------------------------------------------------------------
def _mb_headers():
    return {"User-Agent": config.MUSICBRAINZ_USER_AGENT}


def _mb_wait():
    time.sleep(config.MUSICBRAINZ_RATE_LIMIT_SECONDS)


def _find_musicbrainz_artist_id(artist_name):
    try:
        resp = requests.get(
            f"{config.MUSICBRAINZ_API_URL}artist/",
            params={"query": f'artist:"{artist_name}"', "fmt": "json", "limit": 1},
            headers=_mb_headers(),
            timeout=10,
        )
        _mb_wait()
        resp.raise_for_status()
        artists = resp.json().get("artists", [])
        return artists[0]["id"] if artists else None
    except requests.RequestException:
        _mb_wait()
        return None


def musicbrainz_artist_genres(artist_name):
    if not config.ENABLE_MUSICBRAINZ:
        return {}

    mbid = _find_musicbrainz_artist_id(artist_name)
    if not mbid:
        return {}

    try:
        resp = requests.get(
            f"{config.MUSICBRAINZ_API_URL}artist/{mbid}",
            params={"inc": "genres", "fmt": "json"},
            headers=_mb_headers(),
            timeout=10,
        )
        _mb_wait()
        resp.raise_for_status()
        genres = resp.json().get("genres", [])
    except requests.RequestException:
        _mb_wait()
        return {}

    genres = sorted(genres, key=lambda g: g.get("count", 0), reverse=True)[:config.MUSICBRAINZ_GENRE_LIMIT]
    max_count = max((g.get("count", 0) for g in genres), default=0) or 1

    out = {}
    for g in genres:
        name = _clean(g.get("name", ""))
        if name:
            out[name] = (g.get("count", 0) / max_count) * config.MUSICBRAINZ_GENRE_WEIGHT
    return out


# ---------------------------------------------------------------------------
# Combine sources 2-4 for one artist, cached to disk by artist id (falls
# back to name if a track has no artist id, e.g. some local/compilation
# entries).
# ---------------------------------------------------------------------------
def _get_artist_tags(artist_id, artist_name, tag_cache, spotify_genres_by_artist):
    key = artist_id or artist_name
    if key in tag_cache:
        return tag_cache[key]

    combined = {}
    combined.update(lastfm_artist_tags(artist_name))

    if config.ENABLE_SPOTIFY_GENRES:
        for g in spotify_genres_by_artist.get(artist_id, []):
            name = _clean(g)
            if name:
                combined[name] = combined.get(name, 0) + config.SPOTIFY_GENRE_WEIGHT

    if config.ENABLE_MUSICBRAINZ:
        for tag, weight in musicbrainz_artist_genres(artist_name).items():
            combined[tag] = combined.get(tag, 0) + weight

    tag_cache[key] = combined
    return combined


def attach_tags(df):
    """Add a 'tags' column (dict of {tag: weight}) to a tracks DataFrame."""
    tag_cache = load_tag_cache()

    spotify_genres_by_artist = {}
    if config.ENABLE_SPOTIFY_GENRES:
        artist_ids = sorted({aid for aid in df["artist_id"].dropna().unique()})
        uncached_ids = [aid for aid in artist_ids if aid not in tag_cache]
        if uncached_ids:
            spotify_genres_by_artist = get_artist_genres(uncached_ids)

    all_tags = []
    for _, row in tqdm(df.iterrows(), total=len(df), desc="Gathering tags", unit="track"):
        combined = dict(lastfm_track_tags(row["name"], row["artist"]))
        for tag, weight in _get_artist_tags(
            row["artist_id"], row["artist"], tag_cache, spotify_genres_by_artist
        ).items():
            combined[tag] = combined.get(tag, 0) + weight
        all_tags.append(combined)
        time.sleep(0.25)  # stay well under Last.fm's rate limit for the per-track call

    save_tag_cache(tag_cache)
    return df.assign(tags=all_tags)
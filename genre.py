import json
import os
import time

import requests

import config

# ---------------------------------------------------------------------------
# Layer 1: raw tag -> master genre
#
# The vocabulary of raw tags that actually shows up in your library is small
# (a few hundred unique strings at most), so this is a lookup table you build
# up once and cache to disk — never re-classified for a tag you've already
# seen. Anything the keyword rules below don't catch lands in "Other"; check
# genre_map.json after a run and either add a keyword rule here or hand-edit
# that one entry directly.
# ---------------------------------------------------------------------------
GENRE_KEYWORDS = [
    # more specific terms first — first match wins
    ("metalcore", "Metal"), ("deathcore", "Metal"), ("metal", "Metal"),
    ("hip hop", "Hip-Hop/Rap"), ("rap", "Hip-Hop/Rap"), ("trap", "Hip-Hop/Rap"),
    ("r&b", "R&B/Soul"), ("soul", "R&B/Soul"),
    ("punk", "Punk"),
    ("techno", "Electronic"), ("house", "Electronic"), ("edm", "Electronic"),
    ("dubstep", "Electronic"), ("electro", "Electronic"), ("synth", "Electronic"),
    ("indie", "Indie/Alternative"), ("alternative", "Indie/Alternative"),
    ("rock", "Rock"),
    ("pop", "Pop"),
    ("country", "Country"),
    ("jazz", "Jazz"),
    ("classical", "Classical"), ("orchestra", "Classical"),
    ("folk", "Folk"),
    ("reggaeton", "Latin"), ("latin", "Latin"),
    ("reggae", "Reggae"),
    ("blues", "Blues"),
]

# Last.fm tags that are moods/decades/meta-noise rather than genres — skip
# these when picking a track's "best" tag.
TAG_BLOCKLIST = {
    "seen live", "favorites", "favourite", "beautiful", "awesome", "love",
    "2020s", "2010s", "2000s", "1990s", "1980s", "chill", "sad", "happy",
    "female vocalists", "male vocalists", "under 2000 listeners",
}


def classify_genre(raw_genre):
    g = raw_genre.lower()
    for keyword, master in GENRE_KEYWORDS:
        if keyword in g:
            return master
    return "Other"


def load_genre_map():
    if os.path.exists(config.GENRE_MAP_FILE):
        with open(config.GENRE_MAP_FILE) as f:
            return json.load(f)
    return {}


def save_genre_map(genre_map):
    with open(config.GENRE_MAP_FILE, "w") as f:
        json.dump(genre_map, f, indent=2)


def get_master_genre(raw_genre, genre_map):
    if raw_genre not in genre_map:
        genre_map[raw_genre] = classify_genre(raw_genre)
    return genre_map[raw_genre]


# ---------------------------------------------------------------------------
# Layer 0: fetch a raw genre-ish tag per track from Last.fm
#
# Free API key, no OAuth. Matches by artist + track name, which you already
# have from get_playlist_tracks(). Falls back to the artist's top tag if the
# specific track has no tags of its own.
#
# Swap-in note: if you'd rather pay for a single authoritative genre label
# per track instead of a crowd-tagged one, SoundStat (soundstat.info) takes a
# Spotify track ID and returns a clean `genre` field directly — replace
# get_top_tag()/get_artist_top_tag() with a call to that API and skip the
# blocklist/fallback logic entirely, since there's only one tag to pick.
# ---------------------------------------------------------------------------
def _first_valid_tag(tags):
    for tag in tags:
        name = tag.get("name", "").lower().strip()
        if name and name not in TAG_BLOCKLIST:
            return name
    return None


def get_top_tag(track_name, artist_name):
    if not config.LASTFM_API_KEY:
        return None
    params = {
        "method": "track.getTopTags",
        "artist": artist_name,
        "track": track_name,
        "api_key": config.LASTFM_API_KEY,
        "format": "json",
        "autocorrect": 1,
    }
    try:
        resp = requests.get(config.LASTFM_API_URL, params=params, timeout=10)
        resp.raise_for_status()
        tags = resp.json().get("toptags", {}).get("tag", [])
        return _first_valid_tag(tags)
    except requests.RequestException:
        return None


def get_artist_top_tag(artist_name):
    if not config.LASTFM_API_KEY:
        return None
    params = {
        "method": "artist.getTopTags",
        "artist": artist_name,
        "api_key": config.LASTFM_API_KEY,
        "format": "json",
        "autocorrect": 1,
    }
    try:
        resp = requests.get(config.LASTFM_API_URL, params=params, timeout=10)
        resp.raise_for_status()
        tags = resp.json().get("toptags", {}).get("tag", [])
        return _first_valid_tag(tags)
    except requests.RequestException:
        return None


def attach_genres(df):
    """Add raw_genre + master_genre columns to a features DataFrame."""
    genre_map = load_genre_map()
    artist_tag_cache = {}
    raw_genres = []

    for _, row in df.iterrows():
        tag = get_top_tag(row["name"], row["artist"])

        if not tag:
            if row["artist"] not in artist_tag_cache:
                artist_tag_cache[row["artist"]] = get_artist_top_tag(row["artist"]) or "unknown"
            tag = artist_tag_cache[row["artist"]]

        raw_genres.append(tag)
        time.sleep(0.25)  # stay well under Last.fm's rate limit

    df = df.assign(raw_genre=raw_genres)
    df["master_genre"] = df["raw_genre"].apply(lambda g: get_master_genre(g, genre_map))
    save_genre_map(genre_map)
    return df

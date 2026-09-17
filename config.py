import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Spotify auth
# ---------------------------------------------------------------------------
SPOTIFY_CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI")
SPOTIFY_SCOPE = (
    "playlist-read-private playlist-read-collaborative "
    "playlist-modify-private playlist-modify-public"
)

# ---------------------------------------------------------------------------
# Last.fm (crowd-sourced track + artist tags) — free API key, no OAuth:
# https://www.last.fm/api/account/create
# ---------------------------------------------------------------------------
LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
LASTFM_API_URL = "https://ws.audioscrobbler.com/2.0/"
LASTFM_TRACK_TAG_LIMIT = 5   # top N tags to pull per track
LASTFM_ARTIST_TAG_LIMIT = 5  # top N tags to pull per artist (cached)

# ---------------------------------------------------------------------------
# MusicBrainz (curated per-artist genre list) — no API key, but they require
# an identifying User-Agent and a strict ~1 req/sec rate limit. Set
# MUSICBRAINZ_CONTACT (your email or a project URL) before running — see
# https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting
# ---------------------------------------------------------------------------
ENABLE_MUSICBRAINZ = True
MUSICBRAINZ_API_URL = "https://musicbrainz.org/ws/2/"
MUSICBRAINZ_CONTACT = os.getenv("MUSICBRAINZ_CONTACT", "you@example.com")
MUSICBRAINZ_USER_AGENT = f"spotify-genre-clusterer/1.0 ( {MUSICBRAINZ_CONTACT} )"
MUSICBRAINZ_RATE_LIMIT_SECONDS = 1.1
MUSICBRAINZ_GENRE_LIMIT = 5  # top N genres to pull per artist

# ---------------------------------------------------------------------------
# Spotify's own per-artist genre tags — no extra auth needed, and sp.artists()
# is batched 50-at-a-time so this is cheap regardless of library size.
# ---------------------------------------------------------------------------
ENABLE_SPOTIFY_GENRES = True

# ---------------------------------------------------------------------------
# Tag weighting — how much each source contributes to a track's tag vector.
# Track-level Last.fm tags are the most specific signal (about that one
# song); everything else is artist-level and applies to every song by that
# artist, so it's weighted a bit lower.
# ---------------------------------------------------------------------------
LASTFM_TRACK_TAG_WEIGHT = 1.0
LASTFM_ARTIST_TAG_WEIGHT = 0.6
SPOTIFY_GENRE_WEIGHT = 0.8
MUSICBRAINZ_GENRE_WEIGHT = 0.8

# Tags that are moods/decades/meta-noise rather than genres — dropped from
# every source before they can enter a track's tag vector.
TAG_BLOCKLIST = {
    "seen live", "favorites", "favourite", "beautiful", "awesome", "love",
    "2020s", "2010s", "2000s", "1990s", "1980s", "chill", "sad", "happy",
    "female vocalists", "male vocalists", "under 2000 listeners", "spotify",
}

# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------
NUM_CLUSTERS = 10          # how many playlists to split the whole library into
MAX_TAG_FEATURES = 150     # size of the tag vocabulary (feature dimensions),
                            # frozen after the first run so later runs project
                            # new tracks into the same space instead of
                            # re-clustering everything
CLUSTER_NAME_TOP_TAGS = 3  # how many distinctive tags to use in a cluster's name

# ---------------------------------------------------------------------------
# Source playlist / behavior
# ---------------------------------------------------------------------------
PLAYLIST_ID = "0PWYwl5ZGQoJQ1jxaPOk7z"  # just the ID, not the full URL — edit me
MAKE_PLAYLISTS_PUBLIC = False

STATE_FILE = "cluster_state.json"          # seen tracks, vocab, cluster centers, playlist ids
TAG_CACHE_FILE = "artist_tag_cache.json"   # per-artist Last.fm/Spotify/MusicBrainz tags, cached across runs
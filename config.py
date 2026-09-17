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
# Last.fm (genre tags) — free API key, no OAuth: https://www.last.fm/api/account/create
# ---------------------------------------------------------------------------
LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
LASTFM_API_URL = "https://ws.audioscrobbler.com/2.0/"

# ---------------------------------------------------------------------------
# ReccoBeats (audio features) — free, no key required
# ---------------------------------------------------------------------------
RECCOBEATS_AUDIO_FEATURES_URL = "https://api.reccobeats.com/v1/audio-features"
RECCOBEATS_BATCH_SIZE = 40  # ReccoBeats doesn't publish an official cap; keep modest

# ---------------------------------------------------------------------------
# Source playlist / behavior
# ---------------------------------------------------------------------------
PLAYLIST_ID = "0PWYwl5ZGQoJQ1jxaPOk7z"  # just the ID, not the full URL — edit me
MAKE_PLAYLISTS_PUBLIC = False

NUM_CLUSTERS = 6            # max sub-clusters within any one genre bucket
SUBCLUSTER_THRESHOLD = 60   # genre buckets smaller than this skip K-Means entirely

FEATURE_COLS = [
    "acousticness", "danceability", "energy", "instrumentalness",
    "liveness", "loudness", "speechiness", "tempo", "valence",
]

STATE_FILE = "cluster_state.json"   # seen tracks, cluster centers, playlist ids (per genre)
GENRE_MAP_FILE = "genre_map.json"   # cached raw-tag -> master-genre lookups

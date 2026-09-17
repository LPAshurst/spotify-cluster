import time

import spotipy
from spotipy.oauth2 import SpotifyOAuth

import config

sp = spotipy.Spotify(
    auth_manager=SpotifyOAuth(
        client_id=config.SPOTIFY_CLIENT_ID,
        client_secret=config.SPOTIFY_CLIENT_SECRET,
        redirect_uri=config.SPOTIFY_REDIRECT_URI,
        scope=config.SPOTIFY_SCOPE,
        open_browser=False,
    )
)


def chunk(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def create_playlist(name, public=False, description=""):
    """Workaround for Spotify's Feb 2026 Web API migration.

    spotipy's built-in user_playlist_create() still posts to the deprecated
    POST /users/{user_id}/playlists endpoint, which now returns 403 for every
    caller regardless of scopes. POST /me/playlists is the endpoint Spotify's
    migration guide names as the replacement, and it doesn't need a user id
    at all. Drop this and go back to sp.user_playlist_create() once spotipy
    ships an official fix.
    """
    payload = {"name": name, "public": public, "description": description}
    return sp._post("me/playlists", payload=payload)


def add_tracks(playlist_id, track_ids):
    track_uris = [f"spotify:track:{tid}" for tid in track_ids]
    for uri_batch in chunk(track_uris, 100):
        sp.playlist_add_items(playlist_id, uri_batch)
        time.sleep(0.3)


def get_playlist_tracks(playlist_id):
    """Loop through a playlist and return (tracks, skipped_local).

    tracks: dicts with a usable Spotify track id.
    skipped_local: local files and other id-less items. Spotify returns
    these with id: null (most commonly local files added from your own
    computer rather than Spotify's catalog) — they can never be requested
    from a features API or added to a playlist by URI, so they're pulled
    out here instead of crashing downstream on a None id.
    """
    tracks = []
    skipped_local = []
    results = sp.playlist_items(playlist_id)
    while results:
        for item in results["items"]:
            song_item = item.get("item")
            if not song_item:
                continue
            if not song_item.get("id"):
                skipped_local.append({
                    "name": song_item.get("name", "Unknown"),
                    "artist": song_item["artists"][0]["name"] if song_item.get("artists") else "Unknown",
                })
                continue
            tracks.append({
                "id": song_item["id"],
                "name": song_item["name"],
                "artist": song_item["artists"][0]["name"] if song_item["artists"] else "Unknown",
            })
        results = sp.next(results) if results.get("next") else None
    return tracks, skipped_local

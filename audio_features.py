import time

import pandas as pd
import requests

import config
from spotify_client import chunk


def get_audio_features_batch(spotify_ids, debug=False):
    """Query ReccoBeats' batch audio-features endpoint for a list of Spotify track IDs."""
    try:
        resp = requests.get(
            config.RECCOBEATS_AUDIO_FEATURES_URL,
            params={"ids": ",".join(spotify_ids)},
            timeout=15,
        )
        if debug:
            print(f"  [debug] status={resp.status_code} url={resp.url}")
            print(f"  [debug] raw response (first 1000 chars): {resp.text[:1000]}")

        resp.raise_for_status()
        data = resp.json()
        content = data.get("content", data)

        results = {}
        for entry in content:
            href = entry.get("href", "")
            spotify_id = href.rstrip("/").split("/")[-1] if href else None
            track_ref = spotify_id or entry.get("trackId") or entry.get("id")
            if track_ref:
                results[track_ref] = {col: entry.get(col) for col in config.FEATURE_COLS}
        return results
    except requests.RequestException as e:
        print(f"  [!] Batch request failed: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"  [!] Response body: {e.response.text[:1000]}")
        return {}


def build_feature_dataframe(tracks):
    """Fetch audio features in batches and assemble into a DataFrame.

    Returns (df, no_feature_ids) — no_feature_ids is every track ReccoBeats
    had no usable data for, so the caller can remember not to retry them
    forever.
    """
    rows = []
    no_feature_ids = []
    id_to_track = {t["id"]: t for t in tracks}

    for i, batch in enumerate(chunk(list(id_to_track.keys()), config.RECCOBEATS_BATCH_SIZE)):
        print(f"Fetching audio features for batch of {len(batch)} tracks...")
        features_by_id = get_audio_features_batch(batch, debug=(i == 0))

        for spotify_id in batch:
            t = id_to_track[spotify_id]
            features = features_by_id.get(spotify_id)
            if not features or all(v is None for v in features.values()):
                print(f"  [!] No audio features for {t['name']} - {t['artist']}, skipping.")
                no_feature_ids.append(spotify_id)
                continue
            rows.append({"id": t["id"], "name": t["name"], "artist": t["artist"], **features})

        time.sleep(0.5)

    return pd.DataFrame(rows), no_feature_ids

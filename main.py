"""
Spotify Playlist Genre Clusterer
---------------------------------
Pulls every track from a source playlist, gathers genre/tag signals for
each one from three sources — Last.fm (track + artist tags), Spotify
(artist genres), and MusicBrainz (artist genres) — combines them into a
per-track weighted tag vector, and splits the whole library into
config.NUM_CLUSTERS playlists with K-Means on that tag space.

Later runs (e.g. a weekly cron job): only processes tracks not seen before,
vectorizes each one into the same tag space the first run built, and drops
it straight into its nearest existing cluster. No re-clustering.

Tracks are skipped (and remembered, so they aren't retried every run) if:
  - they're local files / id-less playlist items (can never be fetched or
    added via the Web API) — reported each run, not persisted, since they
    have no stable id to track by
  - none of the three sources returned any usable tag for them — persisted
    in cluster_state.json under "skipped_no_tags"

Setup:
    pip install -r requirements.txt
    cp .env.example .env      # fill in Spotify + Last.fm creds, MUSICBRAINZ_CONTACT
    edit PLAYLIST_ID and NUM_CLUSTERS in config.py

Run:
    python main.py                 # normal run
    python main.py --retry-skipped # also re-check tracks previously skipped
                                    # for missing tags
"""

import sys

import pandas as pd

import config
from spotify_client import get_playlist_tracks
from genre import attach_tags
from clustering import run_initial_clustering, run_incremental_update
from state import load_state, save_state


def main():
    retry_skipped = "--retry-skipped" in sys.argv

    tracks, skipped_local = get_playlist_tracks(config.PLAYLIST_ID)
    if skipped_local:
        print(f"Skipping {len(skipped_local)} local/id-less track(s) this run (not persisted).")

    state = load_state()
    seen_ids = set(state["seen_track_ids"]) if state else set()
    skipped_no_tags = set(state.get("skipped_no_tags", [])) if state else set()

    if retry_skipped and skipped_no_tags:
        print(f"--retry-skipped: re-checking {len(skipped_no_tags)} previously skipped track(s).")
        skipped_no_tags = set()

    exclude_ids = seen_ids | skipped_no_tags
    new_tracks = [t for t in tracks if t["id"] not in exclude_ids]

    if not new_tracks:
        print("No new tracks since last run. Nothing to do.")
        return

    print(f"Processing {len(new_tracks)} new track(s)...")
    df = pd.DataFrame(new_tracks)  # columns: id, name, artist, artist_id

    print("Gathering genre tags from Last.fm, Spotify, and MusicBrainz...")
    df = attach_tags(df)

    has_tags = df["tags"].apply(bool)
    no_tag_ids = df.loc[~has_tags, "id"].tolist()
    df = df.loc[has_tags].reset_index(drop=True)

    print(f"Got usable tags for {len(df)} / {len(new_tracks)} tracks.")
    if no_tag_ids:
        print(f"  {len(no_tag_ids)} track(s) had no usable tags from any source — "
              f"skipped, won't retry unless you run with --retry-skipped.")

    if df.empty:
        print("Could not find tags for any new tracks. Nothing to add.")
        state = state or {"seen_track_ids": [], "vocab": [], "cluster_centers": [], "cluster_playlist_ids": {}}
        state["skipped_no_tags"] = sorted(skipped_no_tags | set(no_tag_ids))
        save_state(state)
        return

    if state is None or not state.get("vocab"):
        print("No previous run detected — doing initial tag vectorization + clustering.")
        state = run_initial_clustering(df)
    else:
        print("Previous run detected — routing new tracks into existing clusters.")
        state = run_incremental_update(df, state)

    state["skipped_no_tags"] = sorted(skipped_no_tags | set(no_tag_ids))
    save_state(state)
    print("Done. State saved to", config.STATE_FILE)


if __name__ == "__main__":
    main()
"""
Spotify Playlist Genre + K-Means Clusterer
-------------------------------------------
First run: pulls every track from a source playlist, fetches audio features
(ReccoBeats) and a genre tag (Last.fm) per track, buckets tracks by master
genre, sub-clusters any bucket large enough to benefit from K-Means on audio
features, and creates one playlist per (genre, sub-cluster).

Later runs (e.g. a weekly cron job): only processes tracks not seen before,
routes each into its genre bucket, and either drops it straight into that
bucket's single playlist or assigns it to its nearest existing sub-cluster.
No re-clustering needed. A genre never seen before gets its own new bucket
created on the spot.

Tracks are skipped (and remembered, so they aren't retried every run) if:
  - they're local files / id-less playlist items (can never be fetched or
    added via the Web API) — reported each run, not persisted, since they
    have no stable id to track by
  - ReccoBeats has no audio features for them — persisted in
    cluster_state.json under "skipped_no_features"

Setup:
    pip install -r requirements.txt
    cp .env.example .env      # fill in your Spotify + Last.fm credentials
    edit PLAYLIST_ID in config.py

Run:
    python main.py                 # normal run
    python main.py --retry-skipped # also re-check tracks previously skipped
                                    # for missing audio features
"""

import sys

import config
from spotify_client import get_playlist_tracks
from audio_features import build_feature_dataframe
from genre import attach_genres
from clustering import run_initial_clustering, run_incremental_update
from state import load_state, save_state


def main():
    retry_skipped = "--retry-skipped" in sys.argv

    tracks, skipped_local = get_playlist_tracks(config.PLAYLIST_ID)

    state = load_state()
    seen_ids = set(state["seen_track_ids"]) if state else set()
    skipped_no_features = set(state.get("skipped_no_features", [])) if state else set()

    if retry_skipped and skipped_no_features:
        print(f"--retry-skipped: re-checking {len(skipped_no_features)} previously skipped track(s).")
        skipped_no_features = set()

    exclude_ids = seen_ids | skipped_no_features
    new_tracks = [t for t in tracks if t["id"] not in exclude_ids]

    if not new_tracks:
        print("No new tracks since last run. Nothing to do.")
        return

    print(f"Processing {len(new_tracks)} new track(s)...")
    df, no_feature_ids = build_feature_dataframe(new_tracks)

    # dropna can also remove rows ReccoBeats partially answered (some
    # columns present, others None) — fold those into the same skip list.
    before_ids = set(df["id"]) if not df.empty else set()
    df = df.dropna(subset=config.FEATURE_COLS).reset_index(drop=True)
    after_ids = set(df["id"]) if not df.empty else set()
    no_feature_ids = sorted(set(no_feature_ids) | (before_ids - after_ids))

    print(f"Got audio features for {len(df)} / {len(new_tracks)} tracks.")
    if no_feature_ids:
        print(f"  {len(no_feature_ids)} track(s) had no usable audio features — "
              f"skipped, won't retry unless you run with --retry-skipped.")

    if df.empty:
        print("Could not fetch audio features for any new tracks. Nothing to add.")
        state = state or {"seen_track_ids": [], "genre_buckets": {}}
        state["skipped_no_features"] = sorted(skipped_no_features | set(no_feature_ids))
        save_state(state)
        return

    print("Fetching genre tags from Last.fm...")
    df = attach_genres(df)
    print("\nMaster genre breakdown for this batch:")
    print(df["master_genre"].value_counts().to_string())
    print()

    if state is None:
        print("No previous run detected — doing initial genre + cluster setup.")
        state = run_initial_clustering(df)
    else:
        print("Previous run detected — routing new tracks into existing buckets.")
        state["seen_track_ids"] = list(seen_ids | set(df["id"].tolist()))
        state = run_incremental_update(df, state)

    state["skipped_no_features"] = sorted(skipped_no_features | set(no_feature_ids))
    save_state(state)
    print("Done. State saved to", config.STATE_FILE)


if __name__ == "__main__":
    main()

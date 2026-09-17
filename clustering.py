import numpy as np
from sklearn.cluster import KMeans

import config
from spotify_client import create_playlist, add_tracks


def build_vocab(tag_dicts, max_features):
    """Top N tags by total weight across the library — these become the
    fixed feature dimensions every track gets vectorized into. Frozen after
    the first run and stored in state, the same role the audio-feature
    scaler used to play."""
    totals = {}
    for tags in tag_dicts:
        for tag, weight in tags.items():
            totals[tag] = totals.get(tag, 0) + weight
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    return [tag for tag, _ in ranked[:max_features]]


def vectorize(tags, vocab):
    vec = np.array([tags.get(tag, 0.0) for tag in vocab], dtype=float)
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec


def name_cluster(cluster_vectors, vocab, corpus_avg, top_n):
    """Name a cluster after the tags that are most over-represented in it
    relative to the whole library — not just its most common tags, which
    would just be whatever's most common everywhere."""
    if len(cluster_vectors) == 0:
        return "Mixed Vibes"
    cluster_avg = cluster_vectors.mean(axis=0)
    distinctiveness = cluster_avg - corpus_avg
    top_idx = np.argsort(distinctiveness)[::-1][:top_n]
    names = [vocab[i].title() for i in top_idx if distinctiveness[i] > 0]
    return " / ".join(names) if names else "Mixed Vibes"


def run_initial_clustering(df):
    """First run: build the tag vocabulary, vectorize every track, and split
    the whole library into config.NUM_CLUSTERS playlists in one pass."""
    tag_dicts = df["tags"].tolist()
    vocab = build_vocab(tag_dicts, config.MAX_TAG_FEATURES)

    X = np.array([vectorize(t, vocab) for t in tag_dicts])
    empty = int((X.sum(axis=1) == 0).sum())
    if empty:
        print(f"  [!] {empty} track(s) matched none of the top {len(vocab)} tags in "
              f"the vocabulary — they'll be assigned to whichever cluster happens to "
              f"be closest to the origin, which may not be meaningful for them.")

    k = min(config.NUM_CLUSTERS, len(df))
    kmeans = KMeans(n_clusters=k, random_state=42, n_init="auto")
    labels = kmeans.fit_predict(X)

    corpus_avg = X.mean(axis=0)
    cluster_playlist_ids = {}
    for cluster_id in sorted(set(labels)):
        mask = labels == cluster_id
        cluster_df = df[mask]
        name = name_cluster(X[mask], vocab, corpus_avg, config.CLUSTER_NAME_TOP_TAGS)
        full_name = f"{name} ({mask.sum()})"
        playlist = create_playlist(
            name=full_name,
            public=config.MAKE_PLAYLISTS_PUBLIC,
            description="Auto-generated — Last.fm + Spotify + MusicBrainz genre clustering",
        )
        add_tracks(playlist["id"], cluster_df["id"].tolist())
        cluster_playlist_ids[str(cluster_id)] = playlist["id"]
        print(f"  Created '{full_name}' — {mask.sum()} tracks.")

    return {
        "seen_track_ids": df["id"].tolist(),
        "vocab": vocab,
        "cluster_centers": kmeans.cluster_centers_.tolist(),
        "cluster_playlist_ids": cluster_playlist_ids,
    }


def run_incremental_update(df, state):
    """Later runs: vectorize new tracks into the frozen vocabulary from the
    first run and drop each one into its nearest existing cluster. No
    re-clustering, no re-fetching centers."""
    vocab = state["vocab"]
    centers = np.array(state["cluster_centers"])

    to_add = {}
    for _, row in df.iterrows():
        vec = vectorize(row["tags"], vocab)
        cluster_id = str(int(np.argmin(np.linalg.norm(centers - vec, axis=1))))
        playlist_id = state["cluster_playlist_ids"].get(cluster_id)
        if not playlist_id:
            print(f"  [!] No playlist found for cluster {cluster_id}, skipping {row['name']}.")
            continue
        to_add.setdefault(playlist_id, []).append(row["id"])

    for playlist_id, track_ids in to_add.items():
        add_tracks(playlist_id, track_ids)
        print(f"  Added {len(track_ids)} track(s) to playlist {playlist_id}.")

    state["seen_track_ids"] = list(set(state["seen_track_ids"]) | set(df["id"].tolist()))
    return state
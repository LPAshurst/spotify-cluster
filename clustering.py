import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

import config
from spotify_client import create_playlist, add_tracks


def name_cluster(avg):
    """Build a simple descriptive name from a cluster's averaged feature values."""
    tags = []

    if avg["energy"] >= 0.7 and avg["valence"] >= 0.6:
        tags.append("Upbeat")
    elif avg["energy"] <= 0.4 and avg["valence"] <= 0.4:
        tags.append("Moody")
    elif avg["valence"] >= 0.65:
        tags.append("Feel Good")
    elif avg["energy"] <= 0.35:
        tags.append("Chill")

    if avg["acousticness"] >= 0.6:
        tags.append("Acoustic")
    elif avg["instrumentalness"] >= 0.5:
        tags.append("Instrumental")

    if avg["danceability"] >= 0.7:
        tags.append("Dance")

    if avg["speechiness"] >= 0.33:
        tags.append("Rap-Leaning")

    if avg["tempo"] >= 140:
        tags.append("Fast")
    elif avg["tempo"] <= 90:
        tags.append("Slow")

    if not tags:
        tags.append("Mixed Vibes")

    return " ".join(tags[:3])


def build_genre_bucket(genre, group):
    """Create playlist(s) for one master-genre bucket.

    Buckets smaller than SUBCLUSTER_THRESHOLD get a single playlist and no
    K-Means. Larger buckets get sub-clustered on audio features, same as the
    original single-genre version of this script did across the whole
    library — just scoped to one genre now.
    """
    if len(group) < config.SUBCLUSTER_THRESHOLD:
        playlist = create_playlist(
            name=f"{genre} ({len(group)})",
            public=config.MAKE_PLAYLISTS_PUBLIC,
            description=f"Auto-generated — {genre} tracks",
        )
        add_tracks(playlist["id"], group["id"].tolist())
        print(f"  Created '{genre} ({len(group)})' — {len(group)} tracks, no sub-clustering.")
        return {
            "cluster_centers": None,
            "cluster_playlist_ids": {"0": playlist["id"]},
            "scaler_mean": None,
            "scaler_scale": None,
        }

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(group[config.FEATURE_COLS].values)
    k = max(2, min(config.NUM_CLUSTERS, len(group) // 30))
    kmeans = KMeans(n_clusters=k, random_state=42, n_init="auto")
    labels = kmeans.fit_predict(X_scaled)
    group = group.assign(cluster=labels)

    playlist_ids = {}
    for cluster_id in sorted(group["cluster"].unique()):
        cluster_songs = group[group["cluster"] == cluster_id]
        avg_features = cluster_songs[config.FEATURE_COLS].mean()
        name = f"{genre} — {name_cluster(avg_features)} ({len(cluster_songs)})"
        playlist = create_playlist(
            name=name,
            public=config.MAKE_PLAYLISTS_PUBLIC,
            description=f"Auto-generated — {genre} / K-Means on audio features",
        )
        add_tracks(playlist["id"], cluster_songs["id"].tolist())
        playlist_ids[str(cluster_id)] = playlist["id"]
        print(f"  Created '{name}' — {len(cluster_songs)} tracks.")

    return {
        "cluster_centers": kmeans.cluster_centers_.tolist(),
        "cluster_playlist_ids": playlist_ids,
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
    }


def run_initial_clustering(df):
    """First run: bucket every track by master genre, sub-cluster big buckets."""
    genre_buckets_state = {}
    for genre, group in df.groupby("master_genre"):
        print(f"Genre bucket '{genre}': {len(group)} tracks")
        genre_buckets_state[genre] = build_genre_bucket(genre, group)

    return {
        "seen_track_ids": df["id"].tolist(),
        "genre_buckets": genre_buckets_state,
    }


def assign_to_existing_cluster(row, bucket_state):
    """Nearest saved cluster center within a genre bucket, or the bucket's
    single playlist if it was never sub-clustered."""
    if bucket_state["cluster_centers"] is None:
        return bucket_state["cluster_playlist_ids"]["0"]

    mean = np.array(bucket_state["scaler_mean"])
    scale = np.array(bucket_state["scaler_scale"])
    x_scaled = (row[config.FEATURE_COLS].values.astype(float) - mean) / scale

    centers = np.array(bucket_state["cluster_centers"])
    distances = np.linalg.norm(centers - x_scaled, axis=1)
    cluster_id = str(int(np.argmin(distances)))
    return bucket_state["cluster_playlist_ids"].get(cluster_id)


def run_incremental_update(df, state):
    """Later runs: route each new track into its genre bucket, then its
    nearest existing cluster within that bucket. A genre never seen before
    gets a brand-new bucket created on the spot."""
    genre_buckets = state["genre_buckets"]
    to_add = {}  # playlist_id -> [track_id, ...]

    for genre, group in df.groupby("master_genre"):
        if genre not in genre_buckets:
            print(f"New genre bucket encountered: '{genre}' — creating it now.")
            genre_buckets[genre] = build_genre_bucket(genre, group)
            continue

        bucket_state = genre_buckets[genre]
        for _, row in group.iterrows():
            playlist_id = assign_to_existing_cluster(row, bucket_state)
            if not playlist_id:
                print(f"  [!] No playlist found in '{genre}' bucket, skipping {row['name']}.")
                continue
            to_add.setdefault(playlist_id, []).append(row["id"])

    for playlist_id, track_ids in to_add.items():
        add_tracks(playlist_id, track_ids)
        print(f"  Added {len(track_ids)} track(s) to playlist {playlist_id}.")

    state["genre_buckets"] = genre_buckets
    return state

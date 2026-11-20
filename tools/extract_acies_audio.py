#!/usr/bin/env python3
"""Extract APK audio unchanged and catalog likely music using ffprobe."""
import argparse
import concurrent.futures
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import zipfile


def sha256(path):
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe(item):
    path, source = item
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams",
         "-of", "json", str(path)], capture_output=True, text=True, check=True,
    )
    if result.stderr.strip():
        raise RuntimeError(f"Invalid audio {source}: {result.stderr}")
    data = json.loads(result.stdout)
    fmt = data["format"]
    stream = next(s for s in data["streams"] if s["codec_type"] == "audio")
    duration = float(fmt["duration"])
    match = re.fullmatch(r"sound\[(\d+)\]\[(\d+)\]\[(\d+)\]\.ogg", path.name)
    index = tuple(map(int, match.groups())) if match else None
    # Include the short box BGM alongside every long track. Group membership
    # is an inference; the title and box mappings have native-symbol evidence.
    music = duration >= 20 or index == (1, 0, 5)
    label = {
        (0, 0, 0): "Title theme (SoundBgmTitle)",
        (1, 0, 5): "Box background cue (SoundBgmBoxBackground)",
    }.get(index, "Music candidate " + ("-".join(f"{n:03d}" for n in index)
                                     if index else path.stem))
    return {
        "source": source, "file": path.name,
        "category": "music" if music else "other_audio",
        "label": label if music else path.stem,
        "duration_seconds": duration,
        "codec": stream["codec_name"], "channels": stream["channels"],
        "sample_rate": int(stream["sample_rate"]), "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "tags": fmt.get("tags", {}) | stream.get("tags", {}),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("--out-dir", type=Path, default=Path("decrypts/audio"))
    args = parser.parse_args()
    if not shutil.which("ffprobe"):
        parser.error("ffprobe is required (brew install ffmpeg)")
    if args.out_dir.exists() and any(args.out_dir.iterdir()):
        parser.error("Output directory must be empty; choose a new --out-dir")
    all_dir = args.out_dir / "all"
    music_dir = args.out_dir / "music"
    all_dir.mkdir(parents=True, exist_ok=True)
    music_dir.mkdir(parents=True, exist_ok=True)
    items = []
    extensions = {".ogg", ".mp3", ".wav", ".m4a", ".aac", ".flac", ".opus"}
    with zipfile.ZipFile(args.apk) as archive:
        for entry in sorted(archive.infolist(), key=lambda i: i.filename):
            if Path(entry.filename).suffix.lower() not in extensions:
                continue
            # Preserve source paths if the APK has colliding basenames.
            target = all_dir / Path(entry.filename).name
            if target.exists():
                raise ValueError(f"Duplicate audio basename: {entry.filename}")
            target.write_bytes(archive.read(entry))  # ZIP CRC checked on read.
            items.append((target, entry.filename))
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        records = list(pool.map(probe, items))
    music = [r for r in records if r["category"] == "music"]
    for record in music:
        shutil.copy2(all_dir / record["file"], music_dir / record["file"])
    playlist = ["#EXTM3U"]
    for record in music:
        playlist.extend([f'#EXTINF:{record["duration_seconds"]:.3f},{record["label"]}',
                         record["file"]])
    (music_dir / "acies-music.m3u").write_text("\n".join(playlist) + "\n")
    manifest = {
        "apk": args.apk.name, "apk_sha256": sha256(args.apk),
        "audio_count": len(records), "music_candidate_count": len(music),
        "music_selection": "duration >=20s, plus native SoundBgmBoxBackground cue",
        "audio": records,
    }
    (args.out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    with (args.out_dir / "catalog.csv").open("w", newline="") as stream:
        fields = [k for k in records[0] if k != "tags"] if records else []
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    print(f"Extracted {len(records)} audio files; selected {len(music)} music/cue candidates")
    print(f"Music duration: {sum(r['duration_seconds'] for r in music) / 60:.2f} minutes")
    print(f"Output: {args.out_dir.resolve()}")


if __name__ == "__main__":
    main()

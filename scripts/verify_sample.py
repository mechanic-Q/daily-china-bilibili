#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bilibili_daily import advance_after_verification, mirror_publish_package, validate_date  # noqa: E402

OLD_SCRIPT_PATHS = (
    Path("/home/lmr/.hermes/scripts/daily_china_crosspost.py"),
    Path("/home/lmr/daily-china-crosspost/scripts/daily_china_crosspost.py"),
)
EXPECTED_OLD_SCRIPT_SHA256 = "95e50fa3894e539d4d08e9d50addaf4c46ee0422c836467da15bb99932e68c6d"
EXPECTED_OLD_VIDEO_SHA256 = "34d5e40838e76fdca14eea3718ed7d48107c3367d07cfb9aec33ad66c4b96f7b"


def sha256(path: Path) -> str:
    with path.open("rb") as file_obj:
        return hashlib.file_digest(file_obj, "sha256").hexdigest()


def probe(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return json.loads(result.stdout)


def verify(date: str) -> dict:
    date = validate_date(date)
    artifact_dir = ROOT / "artifacts" / date
    manifest_path = artifact_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["state"] not in ("rendered", "awaiting_user_confirmation"):
        raise RuntimeError("样本状态不允许执行离线验收")
    for name, record in manifest["artifacts"].items():
        path = Path(record["path"])
        if not path.is_file() or sha256(path) != record["sha256"]:
            raise RuntimeError(f"产物哈希失败: {name}")
    video = Path(manifest["artifacts"]["video"]["path"])
    cover = Path(manifest["artifacts"]["cover"]["path"])
    media = probe(video)
    video_stream = next(stream for stream in media["streams"] if stream["codec_type"] == "video")
    audio_stream = next(stream for stream in media["streams"] if stream["codec_type"] == "audio")
    duration = float(media["format"]["duration"])
    if (
        video_stream["width"],
        video_stream["height"],
        video_stream["codec_name"],
        video_stream.get("r_frame_rate"),
    ) != (1920, 1080, "h264", "30/1"):
        raise RuntimeError("视频规格失败")
    if audio_stream["codec_name"] != "aac" or not 120 <= duration <= 240:
        raise RuntimeError("音频或时长失败")
    with __import__("PIL.Image").Image.open(cover) as image:
        if image.size != (1920, 1080):
            raise RuntimeError("封面规格失败")
    old_video = Path(manifest["old_video_path"])
    if not old_video.is_file() or sha256(old_video) != EXPECTED_OLD_VIDEO_SHA256:
        raise RuntimeError("旧视频不变量改变")
    if sha256(video) == sha256(old_video):
        raise RuntimeError("新旧视频哈希相同")
    for path in OLD_SCRIPT_PATHS:
        if sha256(path) != EXPECTED_OLD_SCRIPT_SHA256:
            raise RuntimeError(f"旧脚本不变量改变: {path}")
    manifest["state"] = advance_after_verification(manifest["state"])
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(manifest_path)
    result = {
        "result": "PASS",
        "duration_seconds": duration,
        "video": str(video),
        "video_sha256": sha256(video),
        "old_video_sha256": sha256(old_video),
        "cover": str(cover),
        "state": manifest["state"],
    }
    report = artifact_dir / "verification.json"
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result["mirror_directory"] = str(mirror_publish_package(artifact_dir))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    verify(args.date)


if __name__ == "__main__":
    main()

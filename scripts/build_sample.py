#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bilibili_daily import (  # noqa: E402
    build_clip_command,
    cache_matches,
    create_cover,
    create_slide,
    fingerprint,
    load_contract,
    record_cache,
    validate_contract,
    validate_date,
    validate_media_probe,
    write_manifest,
)

IMAGE_ENDPOINT = "http://localhost:20128/v1/images/generations"
IMAGE_MODEL = "cx/gpt-5.5"
IMAGE_SIZE = "1536x1024"
VOICE = "zh-CN-XiaoxiaoNeural"
RATE = "+10%"
OLD_VIDEO_TEMPLATE = "/mnt/e/每日新中国/{date}/video/每日新中国_{date}_GPT最终版.mp4"
EXISTING_SHIELD_IMAGE = Path("/mnt/e/每日新中国/2026-07-17/video/gpt_06.png")


def run(command: list[str], *, timeout: int = 600) -> None:
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"命令失败({result.returncode}): {command[0]}\n{detail[-1200:]}")


def image_is_usable(path: Path) -> bool:
    try:
        with Image.open(path) as image:
            image.verify()
        return path.stat().st_size > 0
    except (OSError, ValueError):
        return False


def sha256(path: Path) -> str:
    with path.open("rb") as file_obj:
        return hashlib.file_digest(file_obj, "sha256").hexdigest()


def generate_image(prompt: str, output: Path, retries: int = 8) -> None:
    full_prompt = (
        prompt
        + ", cinematic realistic Chinese engineering documentary, horizontal 16:9 composition, "
        + "main subject inside safe center area, no readable text, no logo, no watermark"
    )
    metadata = output.with_suffix(".input.sha256")
    expected = fingerprint(full_prompt, IMAGE_ENDPOINT, IMAGE_MODEL, IMAGE_SIZE)
    if image_is_usable(output) and cache_matches(output, metadata, expected):
        return
    for attempt in range(1, retries + 1):
        try:
            response = requests.post(
                IMAGE_ENDPOINT,
                headers={"Content-Type": "application/json"},
                json={"model": IMAGE_MODEL, "prompt": full_prompt, "n": 1, "size": IMAGE_SIZE},
                timeout=300,
            )
            if response.status_code == 200:
                payload = response.json()["data"][0]
                if payload.get("b64_json"):
                    output.write_bytes(base64.b64decode(payload["b64_json"]))
                elif payload.get("url"):
                    image_response = requests.get(payload["url"], timeout=120)
                    image_response.raise_for_status()
                    output.write_bytes(image_response.content)
                if image_is_usable(output):
                    record_cache(metadata, expected)
                    return
            if response.status_code not in (429,) and response.status_code < 500:
                raise RuntimeError(f"图片接口HTTP {response.status_code}: {response.text[:300]}")
        except (requests.RequestException, KeyError, ValueError) as error:
            if attempt == retries:
                raise RuntimeError(f"图片生成失败: {error}") from error
        time.sleep(min(5 * attempt, 30))
    raise RuntimeError("图片生成重试耗尽")


def generate_audio(text: str, output: Path) -> None:
    metadata = output.with_suffix(".input.sha256")
    expected = fingerprint(text, VOICE, RATE)
    if cache_matches(output, metadata, expected):
        return
    run(
        [
            "edge-tts",
            "--text",
            text,
            "--voice",
            VOICE,
            "--rate",
            RATE,
            "--write-media",
            str(output),
        ],
        timeout=180,
    )
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError(f"TTS未生成有效音频: {output}")
    record_cache(metadata, expected)


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


def concat_media(paths: list[Path], list_file: Path, output: Path, *, copy_codec: bool) -> None:
    list_file.write_text("".join(f"file '{path.resolve()}'\n" for path in paths), encoding="utf-8")
    command = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file)]
    command += ["-c", "copy"] if copy_codec else ["-c:v", "libx264", "-c:a", "aac"]
    command.append(str(output))
    run(command, timeout=300)


def build(date: str) -> Path:
    date = validate_date(date)
    contract_path = ROOT / "content" / f"{date}-shield-machine.json"
    contract = load_contract(contract_path)
    validate_contract(contract)
    output = ROOT / "artifacts" / date
    work = output / "work"
    output.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)

    clips: list[Path] = []
    audios: list[Path] = []
    images: list[Path] = []
    for index, segment in enumerate(contract["segments"], 1):
        image = work / f"image_{index:02d}.png"
        try:
            generate_image(segment["image_prompt"], image)
        except RuntimeError:
            if index == 1 and image_is_usable(EXISTING_SHIELD_IMAGE):
                shutil.copy2(EXISTING_SHIELD_IMAGE, image)
            else:
                raise
        audio = work / f"audio_{index:02d}.mp3"
        slide = work / f"slide_{index:02d}.png"
        clip = work / f"clip_{index:02d}.mp4"
        generate_audio(segment["narration"], audio)
        create_slide(image, slide, segment["overlay"], index, len(contract["segments"]))
        run(build_clip_command(slide, audio, clip), timeout=600)
        images.append(image)
        audios.append(audio)
        clips.append(clip)

    video = output / f"每日新中国b站_{date}_盾构机.mp4"
    concat_media(clips, work / "clips.txt", video, copy_codec=True)
    combined_audio = output / f"每日新中国b站_{date}_旁白.mp3"
    concat_media(audios, work / "audios.txt", combined_audio, copy_codec=True)
    cover = output / f"每日新中国b站_{date}_封面.png"
    create_cover(images[0], cover, contract["cover_text"])

    media_probe = probe(video)
    duration = validate_media_probe(media_probe, contract["target_duration_seconds"])
    old_video = Path(OLD_VIDEO_TEMPLATE.format(date=date))
    if old_video.is_file() and sha256(old_video) == sha256(video):
        raise RuntimeError("新旧最终视频逐字节相同，拒绝验收")

    manifest = write_manifest(
        contract,
        output / "manifest.json",
        state="rendered",
        artifacts={
            "content_contract": contract_path,
            "source": Path(contract["source_file"]),
            "builder": Path(__file__),
            "audio": combined_audio,
            "cover": cover,
            "video": video,
        },
        extra_fields={
            "media_probe": media_probe,
            "duration_seconds": duration,
            "old_video_path": str(old_video),
        },
    )
    manifest_path = output / "manifest.json"
    print(manifest_path)
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    build(args.date)


if __name__ == "__main__":
    main()

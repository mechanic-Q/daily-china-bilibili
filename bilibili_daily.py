from __future__ import annotations

import hashlib
import json
import shlex
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont


WIDTH = 1920
HEIGHT = 1080
FONT_PATH = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
PHASE_ONE_STATES = (
    "planned",
    "script_frozen",
    "assets_ready",
    "rendered",
    "offline_verified",
    "awaiting_user_confirmation",
)


def load_contract(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_contract(contract: dict) -> None:
    required = {
        "date",
        "slug",
        "source_file",
        "title",
        "description",
        "tid",
        "tags",
        "cover_text",
        "segments",
        "state_ceiling",
        "target_duration_seconds",
    }
    missing = sorted(required - contract.keys())
    if missing:
        raise ValueError(f"内容合同缺少字段: {', '.join(missing)}")
    if not Path(contract["source_file"]).is_file():
        raise ValueError(f"审核源文件不存在: {contract['source_file']}")
    if contract["tid"] != 232:
        raise ValueError("B站分区必须为 tid=232")
    if not 1 <= len(contract["segments"]) <= 8:
        raise ValueError("专版必须包含1至8个分段")
    if contract["state_ceiling"] != "awaiting_user_confirmation":
        raise ValueError("阶段一状态上限必须为 awaiting_user_confirmation")
    low, high = contract["target_duration_seconds"]
    if low < 120 or high > 240 or low >= high:
        raise ValueError("阶段一目标时长必须在2至4分钟内")
    if "欢迎收看" in contract["segments"][0]["narration"][:60]:
        raise ValueError("前5秒不得使用固定栏目问候语")


def _fit_background(image: Image.Image) -> Image.Image:
    ratio = max(WIDTH / image.width, HEIGHT / image.height)
    size = (round(image.width * ratio), round(image.height * ratio))
    resized = image.resize(size, Image.Resampling.LANCZOS)
    left = (resized.width - WIDTH) // 2
    top = (resized.height - HEIGHT) // 2
    return resized.crop((left, top, left + WIDTH, top + HEIGHT))


def create_cover(background: str | Path, output: str | Path, text: str) -> Path:
    with Image.open(background) as source:
        canvas = _fit_background(source.convert("RGB"))
    canvas = ImageEnhance.Brightness(canvas).enhance(0.72)
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rectangle((0, 0, WIDTH, HEIGHT), fill=(0, 0, 0, 64))
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("封面文字不能为空")
    font_size = 220 if len(lines) == 1 else 190
    font = ImageFont.truetype(FONT_PATH, font_size)
    spacing = 28
    boxes = [draw.textbbox((0, 0), line, font=font, stroke_width=4) for line in lines]
    widths = [box[2] - box[0] for box in boxes]
    while max(widths) > WIDTH * 0.9 and font_size > 80:
        font_size -= 6
        font = ImageFont.truetype(FONT_PATH, font_size)
        boxes = [draw.textbbox((0, 0), line, font=font, stroke_width=4) for line in lines]
        widths = [box[2] - box[0] for box in boxes]
    heights = [box[3] - box[1] for box in boxes]
    total_height = sum(heights) + spacing * (len(lines) - 1)
    y = (HEIGHT - total_height) // 2
    for index, line in enumerate(lines):
        x = (WIDTH - widths[index]) // 2
        color = (255, 202, 40) if index == 0 else (255, 255, 255)
        draw.text(
            (x, y),
            line,
            font=font,
            fill=color,
            stroke_width=5,
            stroke_fill=(0, 0, 0),
        )
        y += heights[index] + spacing
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="PNG")
    return output


def create_slide(
    background: str | Path,
    output: str | Path,
    overlay: str,
    index: int,
    total: int,
) -> Path:
    if not overlay.strip():
        raise ValueError("画面信息点不能为空")
    with Image.open(background) as source:
        canvas = _fit_background(source.convert("RGB"))
    canvas = ImageEnhance.Brightness(canvas).enhance(0.68)
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rectangle((0, 0, WIDTH, HEIGHT), fill=(4, 12, 30, 86))
    draw.rectangle((70, 760, 1850, 1000), fill=(0, 0, 0, 150))
    font = ImageFont.truetype(FONT_PATH, 96)
    small = ImageFont.truetype(FONT_PATH, 30)
    draw.text(
        (110, 810),
        overlay,
        font=font,
        fill=(255, 255, 255),
        stroke_width=3,
        stroke_fill=(0, 0, 0),
    )
    draw.text((110, 950), "每日新中国", font=small, fill=(190, 190, 190))
    page = f"{index}/{total}"
    page_box = draw.textbbox((0, 0), page, font=small)
    draw.text((1810 - (page_box[2] - page_box[0]), 950), page, font=small, fill=(190, 190, 190))
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="PNG")
    return output


def build_clip_command(slide: Path, audio: Path, output: Path) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-framerate",
        "30",
        "-i",
        str(slide),
        "-i",
        str(audio),
        "-vf",
        "scale=1920:1080,format=yuv420p",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "22",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(output),
    ]


def validate_media_probe(probe: dict, target_duration_seconds: list[int]) -> float:
    streams = probe.get("streams", [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    if not video or video.get("codec_name") != "h264":
        raise ValueError("视频轨必须为 H.264")
    if (video.get("width"), video.get("height")) != (WIDTH, HEIGHT):
        raise ValueError("视频必须为1920×1080横版")
    if not audio or audio.get("codec_name") != "aac":
        raise ValueError("音频轨必须为 AAC")
    duration = float(probe.get("format", {}).get("duration", 0))
    low, high = target_duration_seconds
    if not low <= duration <= high:
        raise ValueError(f"视频时长不在目标范围: {duration:.3f}s")
    return duration


def transition_state(current: str, target: str) -> str:
    if current not in PHASE_ONE_STATES or target not in PHASE_ONE_STATES:
        raise ValueError("阶段一禁止跨过用户确认门")
    if PHASE_ONE_STATES.index(target) != PHASE_ONE_STATES.index(current) + 1:
        raise ValueError(f"非法状态迁移: {current} -> {target}")
    return target


def _sha256(path: Path) -> str:
    with path.open("rb") as file_obj:
        return hashlib.file_digest(file_obj, "sha256").hexdigest()


def write_manifest(
    contract: dict,
    output: str | Path,
    *,
    state: str,
    artifacts: dict[str, str | Path],
) -> dict:
    validate_contract(contract)
    if state not in PHASE_ONE_STATES:
        raise ValueError("manifest 状态越过阶段一确认门")
    records = {}
    for name, value in artifacts.items():
        path = Path(value).resolve()
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"产物无效: {name}={path}")
        records[name] = {
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
    manifest = {
        "schema_version": 1,
        "state": state,
        "state_ceiling": contract["state_ceiling"],
        "date": contract["date"],
        "slug": contract["slug"],
        "title": contract["title"],
        "description": contract["description"],
        "tid": contract["tid"],
        "tags": contract["tags"],
        "artifacts": records,
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output)
    return manifest


def build_publish_command(manifest_path: str | Path) -> list[str]:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if manifest.get("state") != "awaiting_user_confirmation":
        raise ValueError("离线样本尚未到用户确认门")
    artifacts = manifest.get("artifacts", {})
    for required in ("video", "cover"):
        item = artifacts.get(required, {})
        path = Path(item.get("path", ""))
        if not path.is_file() or _sha256(path) != item.get("sha256"):
            raise ValueError(f"投稿产物缺失或哈希不一致: {required}")
    return [
        "sau",
        "bilibili",
        "upload-video",
        "--account",
        "diyi",
        "--file",
        artifacts["video"]["path"],
        "--title",
        manifest["title"],
        "--desc",
        manifest["description"],
        "--tid",
        str(manifest["tid"]),
        "--tags",
        ",".join(manifest["tags"]),
        "--thumbnail",
        artifacts["cover"]["path"],
    ]


def shell_preview(command: list[str]) -> str:
    return shlex.join(command)

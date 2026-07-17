#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bilibili_daily import (  # noqa: E402
    build_publish_command,
    shell_preview,
    thumbnail_transport_ready,
    validate_date,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="只打印投稿命令，不执行")
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    date = validate_date(args.date)
    manifest = ROOT / "artifacts" / date / "manifest.json"
    sau = Path.home() / "social-auto-upload/.venv/bin/sau"
    help_result = subprocess.run(
        [str(sau), "bilibili", "upload-video", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if help_result.returncode or not thumbnail_transport_ready(help_result.stdout + help_result.stderr):
        raise SystemExit(
            "BLOCKED: 当前 sau bilibili 尚未暴露 --thumbnail；"
            "确认后先补运输层，禁止执行投稿"
        )
    print(shell_preview(build_publish_command(manifest)))
    print("DRY-RUN ONLY: 未执行投稿")


if __name__ == "__main__":
    main()

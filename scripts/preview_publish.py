#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bilibili_daily import build_publish_command, shell_preview  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="只打印投稿命令，不执行")
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    manifest = ROOT / "artifacts" / args.date / "manifest.json"
    print(shell_preview(build_publish_command(manifest)))
    print("DRY-RUN ONLY: 未执行投稿")


if __name__ == "__main__":
    main()

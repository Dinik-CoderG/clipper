"""Campaign folder resolution shared by the reels scripts.

A campaign lives in C:\\Clipper\\campaigns\\<name>\\ with:
  brief/        the campaign PDF and any notes
  source/       official footage (<name>.mp4)
  analysis/     transcripts + contact sheets (analyze.py, subs.py)
  clips.json    the moments to cut (see campaigns/_template/clips.json)
  clips/        rendered Reels (render.py)
  covers/       Reel covers (make_covers.py)
Scripts take the campaign as their first argument: a folder name under campaigns/, or a path.
"""
from __future__ import annotations

import sys
from pathlib import Path

TOOL = Path(__file__).parent
CAMPAIGNS = TOOL.parent / "campaigns"


def resolve(arg: str) -> Path:
    p = Path(arg)
    if not p.is_absolute() and not p.exists():
        p = CAMPAIGNS / arg
    if not p.is_dir():
        sys.exit(f"campaign folder not found: {p}")
    return p.resolve()


def from_argv(usage: str) -> tuple[Path, list[str]]:
    """First CLI argument = campaign; returns (campaign dir, remaining args)."""
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        sys.exit(f"usage: {usage}")
    return resolve(sys.argv[1]), sys.argv[2:]

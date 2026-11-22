"""Video encoding shared by the reels scripts: NVIDIA GPU (h264_nvenc) by default, x264 on the CPU as fallback.

Callers pass a builder that takes the video-codec args and returns the full ffmpeg command, plus the x264 args
they used before (kept as the exact fallback). If the GPU encoder is missing or a GPU encode fails, the same
command is rerun with x264 and the GPU is not tried again in this process.
Set CLIPPER_ENCODER=cpu to always use x264.
"""
from __future__ import annotations

import os
import subprocess
import sys
from typing import Callable

# constant-quality NVENC settings chosen to match the x264 CRF each stage used
NVENC = {
    # 1080p intermediate cut (was x264 crf 12): near-lossless, re-encoded again by the framing step
    "intermediate": ["-c:v", "h264_nvenc", "-preset", "p5", "-tune", "hq", "-rc", "vbr", "-cq", "14", "-b:v", "0",
                     "-profile:v", "high", "-pix_fmt", "yuv420p"],
    # final Reel (was x264 crf 18 slow)
    "final": ["-c:v", "h264_nvenc", "-preset", "p7", "-tune", "hq", "-rc", "vbr", "-cq", "19", "-b:v", "0",
              "-spatial-aq", "1", "-profile:v", "high", "-pix_fmt", "yuv420p"],
}

_gpu: dict[str, bool | None] = {"ok": None}


def gpu_ok() -> bool:
    """Whether ffmpeg can encode on the NVIDIA GPU (checked once per process)."""
    if _gpu["ok"] is None:
        if os.environ.get("CLIPPER_ENCODER", "auto").lower() == "cpu":
            _gpu["ok"] = False
        else:
            probe = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                                    "color=black:s=256x256:d=0.2", "-c:v", "h264_nvenc", "-f", "null", "-"],
                                   capture_output=True)
            _gpu["ok"] = probe.returncode == 0
    return bool(_gpu["ok"])


def run(build: Callable[[list[str]], list[str]], x264: list[str], quality: str = "final", **kwargs) -> str:
    """Run build(codec_args) on the GPU, falling back to build(x264). Returns the encoder used."""
    if gpu_ok():
        try:
            subprocess.run(build(NVENC[quality]), check=True, **kwargs)
            return "h264_nvenc"
        except subprocess.CalledProcessError:
            _gpu["ok"] = False
            print("GPU encode failed; falling back to x264 on the CPU", file=sys.stderr)
    subprocess.run(build(x264), check=True, **kwargs)
    return "libx264"

# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Create the local chart, trend video and spoken summary used in the preview.

Run with Python, Pillow, ffmpeg and the macOS Tingting voice installed.
"""

import math
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
WIDTH, HEIGHT, SCALE = 960, 540, 2
VALUES = [128, 154, 141, 178, 196]
LABELS = ["周一", "周二", "周三", "周四", "周五"]
SUMMARY = "最近五天共完成七百九十七次调用，周五最高，共一百九十六次"
FONT = "/System/Library/Fonts/Hiragino Sans GB.ttc"
BACKGROUND = "#f7f9fc"
TEXT = "#374151"
MUTED = "#7c8799"
GRID = "#e4e9f0"
ACCENT = "#6b87a8"
FILL = "#e7edf5"


def font(size):
    return ImageFont.truetype(FONT, size * SCALE)


def render(progress):
    image = Image.new("RGB", (WIDTH * SCALE, HEIGHT * SCALE), BACKGROUND)
    draw = ImageDraw.Draw(image)

    def text(x, y, value, size=18, color=TEXT, anchor="la"):
        draw.text(
            (x * SCALE, y * SCALE), value, font=font(size), fill=color, anchor=anchor
        )

    def line(points, color=GRID, width=1):
        draw.line(
            [(round(x * SCALE), round(y * SCALE)) for x, y in points],
            fill=color,
            width=width * SCALE,
            joint="curve",
        )

    text(54, 38, "最近五天调用趋势", 28)
    text(54, 82, "调用次数", 16, MUTED)
    text(906, 42, "合计 797 次", 20, MUTED, "ra")

    left, right, top, bottom = 88, 888, 148, 444
    xs = [left + 28 + (right - left - 56) * i / 4 for i in range(5)]
    ys = [bottom - (bottom - top) * value / 220 for value in VALUES]
    for tick in [0, 50, 100, 150, 200]:
        y = bottom - (bottom - top) * tick / 220
        line([(left, y), (right, y)])
        text(left - 18, y, str(tick), 16, MUTED, "rm")
    for x, label in zip(xs, LABELS):
        text(x, bottom + 24, label, 18, MUTED, "ma")

    segment = min(progress * 4, 4)
    completed = min(int(segment), 4)
    points = list(zip(xs[: completed + 1], ys[: completed + 1]))
    if completed < 4:
        t = segment - completed
        points.append(
            (
                xs[completed] + (xs[completed + 1] - xs[completed]) * t,
                ys[completed] + (ys[completed + 1] - ys[completed]) * t,
            )
        )
    if len(points) > 1:
        polygon = [(points[0][0], bottom), *points, (points[-1][0], bottom)]
        draw.polygon([(x * SCALE, y * SCALE) for x, y in polygon], fill=FILL)
        line(points, ACCENT, 3)

    for i in range(completed + 1):
        x, y = xs[i], ys[i]
        radius = 5 * SCALE
        draw.ellipse(
            (
                x * SCALE - radius,
                y * SCALE - radius,
                x * SCALE + radius,
                y * SCALE + radius,
            ),
            fill=BACKGROUND,
            outline=ACCENT,
            width=3 * SCALE,
        )
        text(x, y - 30, str(VALUES[i]), 19, TEXT, "mm")

    return image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)


def run(*args):
    subprocess.run(args, check=True)


def main():
    ffmpeg = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
    ROOT.mkdir(parents=True, exist_ok=True)
    render(1).save(ROOT / "chart.png", optimize=True)

    with TemporaryDirectory(prefix="conversation-media-") as temp_dir:
        temp = Path(temp_dir)
        fps = 24
        for frame in range(5 * fps):
            # The line reveals over three seconds, then holds the final result.
            t = min(1, max(0, (frame / fps - 0.25) / 3.25))
            progress = (1 - math.cos(math.pi * t)) / 2
            render(progress).save(temp / f"frame-{frame:03d}.png")
        run(
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-framerate",
            str(fps),
            "-i",
            str(temp / "frame-%03d.png"),
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "25",
            "-preset",
            "slow",
            "-movflags",
            "+faststart",
            str(ROOT / "trend.mp4"),
        )

        audio = temp / "summary.aiff"
        run("say", "-v", "Tingting", "-r", "175", "-o", str(audio), SUMMARY)
        run(
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(audio),
            "-ac",
            "1",
            "-ar",
            "24000",
            "-c:a",
            "aac",
            "-b:a",
            "48k",
            "-movflags",
            "+faststart",
            str(ROOT / "summary.m4a"),
        )


if __name__ == "__main__":
    main()

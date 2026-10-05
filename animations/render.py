#!/usr/bin/env python3
"""Render a Manim scene into static/ as a scrubbed MP4, WebM and poster PNG.

    ~/.venvs/manim/bin/python animations/render.py tegra_teardown.py \\
        DosStateMachine tegra_teardown/dos_state_machine

writes static/tegra_teardown/dos_state_machine.{mp4,webm,png}. Reference the
.mp4 from Markdown; the image render hook picks up the .webm and the poster
sitting beside it.

    --draft   480p15 into animations/media only, for iterating on a scene

Run it with the Manim virtualenv's Python: the manim binary is found next to
it. Manim reads animations/manim.cfg, so it is run from that directory.

The videos are re-muxed with PyAV rather than copied. Manim stamps every file
"Rendered with Manim Community vX" and FFmpeg adds its own versioned encoder
tag, and a toolchain fingerprint on every post is the same leak hugo.toml
suppresses the generator tag for. The remux copies packets, so the pictures
are untouched. The poster is re-saved through Pillow, which writes no text
chunks.
"""

import argparse
import subprocess
import sys
from pathlib import Path

import av
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MANIM = Path(sys.executable).parent / "manim"


def render(scene_file, scene, name, *flags):
    subprocess.run([str(MANIM), *flags, "-o", name, scene_file, scene],
                   cwd=HERE, check=True)


def newest(pattern):
    hits = sorted(HERE.glob(pattern), key=lambda p: p.stat().st_mtime)
    if not hits:
        sys.exit(f"render.py: nothing matched animations/{pattern}")
    return hits[-1]


def remux_clean(src, dst, **container_options):
    # +bitexact keeps the muxer from writing its version: no encoder tag in
    # MP4, a bare "Lavf" in WebM.
    opts = {"fflags": "+bitexact", **container_options}
    with av.open(str(src)) as inp, \
         av.open(str(dst), "w", container_options=opts) as out:
        ins = inp.streams.video[0]
        outs = out.add_stream_from_template(ins)
        outs.metadata.clear()
        for pkt in inp.demux(ins):
            if pkt.dts is None:         # the demuxer's end-of-stream flush
                continue
            pkt.stream = outs
            out.mux(pkt)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("scene_file", help="scene file, relative to animations/")
    ap.add_argument("scene", help="Scene class to render")
    ap.add_argument("out", help="output path under static/, without extension")
    ap.add_argument("--draft", action="store_true",
                    help="480p15 into animations/media only")
    a = ap.parse_args()

    stem = Path(a.scene_file).stem
    name = Path(a.out).name

    if a.draft:
        render(a.scene_file, a.scene, name, "-ql")
        print(newest(f"media/videos/{stem}/*/{name}.mp4"))
        return

    render(a.scene_file, a.scene, name)
    render(a.scene_file, a.scene, name, "--format", "webm")
    render(a.scene_file, a.scene, name, "-s")       # last frame, the poster

    dst = ROOT / "static" / a.out
    dst.parent.mkdir(parents=True, exist_ok=True)
    # faststart moves the index to the front, so playback can begin before
    # the whole file has downloaded.
    remux_clean(newest(f"media/videos/{stem}/*/{name}.mp4"),
                dst.with_suffix(".mp4"), movflags="+faststart")
    remux_clean(newest(f"media/videos/{stem}/*/{name}.webm"),
                dst.with_suffix(".webm"))
    Image.open(newest(f"media/images/{stem}/{name}*.png")).save(
        dst.with_suffix(".png"), optimize=True)

    for ext in (".mp4", ".webm", ".png"):
        p = dst.with_suffix(ext)
        print(f"  {p.relative_to(ROOT)}  {p.stat().st_size // 1024} KiB")


if __name__ == "__main__":
    main()

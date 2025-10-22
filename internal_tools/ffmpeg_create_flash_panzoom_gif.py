#!/bin/usr/env python3
# Copyright (c) Acconeer AB, 2025
# All rights reserved

import argparse
import math
import subprocess as sp
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("--output", "-o", required=True)
    parser.add_argument("--force", "-f", action="store_true")

    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    force = bool(args.force)

    if not input_path.is_file():
        print(f"ERROR: '{input_path}' is not a file")
        exit(1)
    if not force and output_path.exists():
        print(f"ERROR: Output path '{output_path}' already exists")
        exit(1)

    tmp_dir = Path("./tmp")
    tmp_dir.mkdir(exist_ok=True)

    upscaling = 1000
    total_time_s = 3
    fps = 120

    z_expr = f"min(2.2, 1 + 1.4 * 1/(1 + {math.e}^(7-10*(in_time/{total_time_s}))))"
    x_expr = "0"
    y_expr = "0"
    sp.check_call(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            input_path,
            "-vf",
            f"scale={upscaling}:-1,zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d=1:fps={fps}",
            "-t",
            str(total_time_s),
            tmp_dir / "one.mp4",
        ]
    )
    sp.check_call(
        [
            "ffmpeg",
            "-y",
            "-i",
            tmp_dir / "one.mp4",
            "-vf",
            "tmix=frames=3:weights='.33 .66 1',framestep=1",
            tmp_dir / "two.mp4",
        ]
    )

    # Add flashing square
    square_x = 35
    square_y = 250.0
    square_size = "128x128"
    square_red = 255
    square_green = 255
    square_max_alpha = 50
    square_begin_s = 1.1

    alpha_expr = f"if(lt(T, {square_begin_s}), 0, {square_max_alpha} * abs(sin(20 * (T - {square_begin_s})/{total_time_s})))"

    sp.check_call(
        [
            "ffmpeg",
            "-y",
            "-i",
            tmp_dir / "two.mp4",
            "-filter_complex",
            ";".join(
                [
                    f"color=c=red:s={square_size}:duration=100 [square]",
                    f"[square]format=yuva444p,geq=r={square_red}:g={square_green}:a='{alpha_expr}'[alpha_square]",
                    f"[0:v][alpha_square]overlay=x={square_x}:y={square_y}:shortest=1",
                ]
            ),
            tmp_dir / "three.mp4",
        ]
    )

    # Generate palette
    sp.check_call(
        [
            "ffmpeg",
            "-y",
            "-i",
            tmp_dir / "three.mp4",
            "-vf",
            f"fps={fps},scale=w=in_w/2:-1:flags=lanczos,palettegen",
            tmp_dir / "palette.png",
        ]
    )

    # Generate final GIF
    fps = 24
    sp.check_call(
        [
            "ffmpeg",
            "-y",
            "-i",
            tmp_dir / "three.mp4",
            "-i",
            tmp_dir / "palette.png",
            "-filter_complex",
            f"fps={fps},scale=w=in_w/2:-1:flags=lanczos[x];[x][1:v]paletteuse",
            output_path,
        ]
    )


if __name__ == "__main__":
    main()

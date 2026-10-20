#!/usr/bin/env python3
"""Assemble independently rendered audio clips with exact authored pauses."""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any


DEFAULT_SAMPLE_RATE = 44_100
DEFAULT_CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2  # PCM signed 16-bit


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Assemble speech or other audio clips with exact pauses into one WAV file."
        )
    )
    parser.add_argument("manifest", type=Path, help="JSON assembly manifest")
    parser.add_argument("--out", type=Path, help="Override the manifest output path")
    parser.add_argument(
        "--ffmpeg",
        help="ffmpeg executable name or path; normally detected automatically",
    )
    return parser.parse_args()


def require_nonnegative_ms(value: Any, field: str, index: int) -> float:
    try:
        milliseconds = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Segment {index}: {field} must be a number") from exc
    if not math.isfinite(milliseconds):
        raise ValueError(f"Segment {index}: {field} must be finite")
    if milliseconds < 0:
        raise ValueError(f"Segment {index}: {field} cannot be negative")
    return milliseconds


def write_silence(
    destination: wave.Wave_write,
    milliseconds: float,
    sample_rate: int,
    channels: int,
) -> int:
    frame_count = round(milliseconds * sample_rate / 1000)
    destination.writeframes(b"\x00" * frame_count * channels * SAMPLE_WIDTH_BYTES)
    return frame_count


def resolve_ffmpeg(requested: str | None) -> str:
    if requested:
        executable = shutil.which(requested)
        if executable:
            return executable
        candidate = Path(requested).expanduser()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate.resolve())
        raise RuntimeError(f"ffmpeg was not found at: {requested}")

    executable = shutil.which("ffmpeg")
    if executable:
        return executable

    for common_path in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        candidate = Path(common_path)
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)

    raise RuntimeError(
        "ffmpeg is required but was not found. Install it or pass --ffmpeg PATH."
    )


def normalize_clip(
    ffmpeg: str,
    source: Path,
    destination: Path,
    sample_rate: int,
    channels: int,
) -> None:
    result = subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-y",
            "-i",
            str(source),
            "-ar",
            str(sample_rate),
            "-ac",
            str(channels),
            "-c:a",
            "pcm_s16le",
            str(destination),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "unknown ffmpeg error"
        raise RuntimeError(f"Could not normalize {source}: {detail}")


def load_manifest(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {}, data
    if not isinstance(data, dict):
        raise ValueError("Manifest must be a JSON object or a list of segments")
    segments = data.get("segments")
    if not isinstance(segments, list):
        raise ValueError("Manifest object must contain a segments list")
    return data, segments


def main() -> int:
    args = parse_args()
    manifest_path = args.manifest.expanduser().resolve()
    settings, segments = load_manifest(manifest_path)
    if not segments:
        raise ValueError("Manifest contains no audio segments")

    sample_rate = int(settings.get("sample_rate", DEFAULT_SAMPLE_RATE))
    channels = int(settings.get("channels", DEFAULT_CHANNELS))
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    if channels not in (1, 2):
        raise ValueError("channels must be 1 or 2")

    configured_output = args.out or settings.get("output")
    if not configured_output:
        raise ValueError("Provide --out or an output path in the manifest")
    if not isinstance(configured_output, (str, os.PathLike, Path)):
        raise ValueError("Output path must be a string")
    output_path = Path(configured_output).expanduser()
    if not output_path.is_absolute():
        output_path = manifest_path.parent / output_path
    output_path = output_path.resolve()
    if output_path.suffix.lower() != ".wav":
        raise ValueError("Output must be a .wav file")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = resolve_ffmpeg(args.ffmpeg)
    total_frames = 0
    silence_frames = 0

    with tempfile.TemporaryDirectory(
        prefix="exact-pause-compile-", dir=output_path.parent
    ) as temporary_directory:
        temporary_path = Path(temporary_directory)
        assembled_path = temporary_path / "assembled.wav"

        with wave.open(str(assembled_path), "wb") as assembled:
            assembled.setnchannels(channels)
            assembled.setsampwidth(SAMPLE_WIDTH_BYTES)
            assembled.setframerate(sample_rate)

            for index, segment in enumerate(segments, start=1):
                if not isinstance(segment, dict):
                    raise ValueError(f"Segment {index}: each segment must be an object")
                file_value = segment.get("file")
                if not isinstance(file_value, str) or not file_value.strip():
                    raise ValueError(f"Segment {index}: file is required")

                source_path = Path(file_value).expanduser()
                if not source_path.is_absolute():
                    source_path = manifest_path.parent / source_path
                source_path = source_path.resolve()
                if not source_path.is_file():
                    raise FileNotFoundError(
                        f"Segment {index}: clip not found: {source_path}"
                    )

                pause_before = require_nonnegative_ms(
                    segment.get("pause_before_ms", 0), "pause_before_ms", index
                )
                pause_after = require_nonnegative_ms(
                    segment.get("pause_after_ms", 0), "pause_after_ms", index
                )

                written = write_silence(
                    assembled, pause_before, sample_rate, channels
                )
                total_frames += written
                silence_frames += written

                normalized_path = temporary_path / f"segment-{index:03d}.wav"
                normalize_clip(
                    ffmpeg,
                    source_path,
                    normalized_path,
                    sample_rate,
                    channels,
                )
                with wave.open(str(normalized_path), "rb") as normalized:
                    frame_count = normalized.getnframes()
                    assembled.writeframes(normalized.readframes(frame_count))
                    total_frames += frame_count

                written = write_silence(
                    assembled, pause_after, sample_rate, channels
                )
                total_frames += written
                silence_frames += written

        os.replace(assembled_path, output_path)

    duration_seconds = total_frames / sample_rate
    silence_seconds = silence_frames / sample_rate
    print(f"Wrote {output_path}")
    print(f"Segments: {len(segments)}")
    print(f"Authored silence: {silence_seconds:.3f} seconds")
    print(f"Duration: {duration_seconds:.3f} seconds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

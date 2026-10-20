import json
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compile_exact_pause_audio.py"
SAMPLE_RATE = 44_100
CLIP_FRAMES = 4_410


def find_ffmpeg():
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    for candidate in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        if Path(candidate).is_file():
            return candidate
    return None


def write_constant_clip(path, amplitude):
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(SAMPLE_RATE)
        audio.writeframes(struct.pack("<h", amplitude) * CLIP_FRAMES)


@unittest.skipUnless(find_ffmpeg(), "ffmpeg is required for the end-to-end test")
class CompilerTests(unittest.TestCase):
    def test_inserts_exact_silence_between_clips(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            clips = root / "clips"
            clips.mkdir()

            for index, amplitude in enumerate((1000, 2000, 3000), start=1):
                write_constant_clip(clips / f"{index:03d}.wav", amplitude)

            manifest = {
                "sample_rate": SAMPLE_RATE,
                "channels": 1,
                "output": "assembled.wav",
                "segments": [
                    {"file": "clips/001.wav", "pause_after_ms": 1000},
                    {"file": "clips/002.wav"},
                    {"file": "clips/003.wav", "pause_before_ms": 2000},
                ],
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            subprocess.run(
                [
                    sys.executable,
                    str(COMPILER),
                    str(manifest_path),
                    "--ffmpeg",
                    find_ffmpeg(),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            with wave.open(str(root / "assembled.wav"), "rb") as audio:
                self.assertEqual(audio.getnchannels(), 1)
                self.assertEqual(audio.getsampwidth(), 2)
                self.assertEqual(audio.getframerate(), SAMPLE_RATE)
                self.assertEqual(audio.getnframes(), 145_530)
                samples = struct.unpack(
                    f"<{audio.getnframes()}h",
                    audio.readframes(audio.getnframes()),
                )

            self.assertTrue(all(value != 0 for value in samples[0:4_410]))
            self.assertTrue(all(value == 0 for value in samples[4_410:48_510]))
            self.assertTrue(all(value != 0 for value in samples[48_510:52_920]))
            self.assertTrue(all(value == 0 for value in samples[52_920:141_120]))
            self.assertTrue(all(value != 0 for value in samples[141_120:145_530]))


if __name__ == "__main__":
    unittest.main()

# Exact Pause Audio Compiler

Some text-to-speech services shorten, ignore, or inconsistently interpret long
pauses and SSML break tags. This small local tool uses a more reliable method:

1. Render the spoken sections as separate MP3 or WAV clips.
2. Describe their order and exact pause lengths in a JSON manifest.
3. Assemble them locally into one lossless WAV file.

The TTS service controls delivery **inside** each clip. This compiler controls
elapsed silence **between** clips.

## Privacy

The compiler runs locally and makes no network requests. It contains no TTS
credentials and does not generate speech. The service used to create the source
clips has its own privacy terms, but assembling those downloaded clips happens
entirely on the local computer.

Apart from the public copyright notice, this repository contains no original
script text, audio, credentials, private personal names, private paths, or
source-project metadata.

Common audio formats and the contents of `clips/` are ignored by Git by
default, helping prevent source recordings from being committed accidentally.

## Requirements

- Python 3.9 or newer
- [ffmpeg](https://ffmpeg.org/)

On a Mac with Homebrew:

```sh
brew install ffmpeg
```

On Windows with winget:

```powershell
winget install Gyan.FFmpeg
```

Close and reopen the terminal after installing ffmpeg if the command is not
found immediately.

## Prepare the clips

Render each section separately through the same voice, model, and settings.
Natural paragraph or section boundaries usually produce better continuity than
splitting every short sentence.

Place the downloaded files in `clips/` and give them clear ordered names, such
as:

```text
clips/001-opening.mp3
clips/002-middle.wav
clips/003-closing.mp3
```

If the TTS service adds unwanted silence to a clip itself, trim that clip before
assembly. The compiler never alters the source files and adds only the pauses
listed in the manifest.

## Edit the manifest

Copy `manifest.example.json` or edit it directly:

```json
{
  "sample_rate": 44100,
  "channels": 1,
  "output": "assembled-voice-memo.wav",
  "segments": [
    {
      "file": "clips/001-opening.mp3",
      "pause_after_ms": 1500
    },
    {
      "file": "clips/002-middle.wav",
      "pause_after_ms": 4000
    },
    {
      "file": "clips/003-closing.mp3"
    }
  ]
}
```

Paths are resolved relative to the manifest. Each segment supports:

- `file` — required MP3 or WAV path
- `pause_before_ms` — optional silence before the clip, in milliseconds
- `pause_after_ms` — optional silence after the clip, in milliseconds

If both a clip's `pause_after_ms` and the next clip's `pause_before_ms` are
present, those pauses are added together.

## Run it

From this folder on macOS or Linux:

```sh
python3 compile_exact_pause_audio.py manifest.example.json
```

On Windows:

```powershell
py compile_exact_pause_audio.py manifest.example.json
```

To choose another output location:

```sh
python3 compile_exact_pause_audio.py manifest.example.json --out my-memo.wav
```

If ffmpeg is installed somewhere unusual:

```sh
python3 compile_exact_pause_audio.py manifest.example.json --ffmpeg /path/to/ffmpeg
```

The output is a mono or stereo 16-bit PCM WAV. Pause lengths are converted to
the nearest audio frame at the selected sample rate, giving deterministic timing
rather than asking the TTS model to estimate elapsed silence.

## Test

The repository includes an end-to-end test that creates synthetic clips and
verifies exact one- and two-second silent regions at the audio-frame level:

```sh
python3 -m unittest discover -s tests -v
```

## Practical advice

- Keep the voice, model, and synthesis settings identical across clips.
- Split at natural boundaries where a pause already belongs.
- Use punctuation to shape performance within a clip.
- Use the manifest to control real elapsed time between clips.
- Test a short three-clip passage before compiling a long memo.
- Keep the original clips; the compiler never modifies them.

## License

MIT

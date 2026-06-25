#!/usr/bin/env bash
#
# transcribe_voice_memos.sh — transcribe iPhone Voice Memos on the Mac.
#
# Designed to be triggered remotely from an iPhone via the Shortcuts app
# ("Run Script Over SSH"). It transcribes every voice memo that has speech and
# writes the verbatim 逐字稿 into an iCloud Drive folder, so the results appear
# in the Files app on the phone within seconds.
#
# It is idempotent: --skip-existing means already-transcribed memos are skipped,
# so you can trigger it as often as you like.
#
# Configure via environment variables (or edit the defaults below):
#   VT_VENV      path to the Python venv with voice-transcriber installed
#   VT_OUTPUT    where to write transcripts (default: iCloud Drive/VoiceMemo逐字稿)
#   VT_ENGINE    auto | mlx | faster-whisper (default: auto → MLX/GPU on Apple Silicon)
#   VT_MODEL     whisper model (default: large-v3)
#   VT_LANGUAGE  language code or "auto" (default: auto)
#
# On Apple Silicon this runs on the GPU via MLX: ~7x faster than CPU and far
# cooler/quieter. No system ffmpeg needed — audio is decoded with PyAV.
#
set -euo pipefail

VT_VENV="${VT_VENV:-$HOME/Tian-Finance/.venv}"
VT_OUTPUT="${VT_OUTPUT:-$HOME/Library/Mobile Documents/com~apple~CloudDocs/VoiceMemo逐字稿}"
VT_ENGINE="${VT_ENGINE:-auto}"
VT_MODEL="${VT_MODEL:-large-v3}"
VT_LANGUAGE="${VT_LANGUAGE:-auto}"

# Homebrew bins on PATH if present (not required — kept for convenience).
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

if [ -f "$VT_VENV/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "$VT_VENV/bin/activate"
fi

mkdir -p "$VT_OUTPUT"

echo "▶︎ 转写语音备忘录（引擎 $VT_ENGINE）→ $VT_OUTPUT"
voice-transcriber transcribe \
    --source voicememos \
    --skip-existing \
    --engine "$VT_ENGINE" \
    --model "$VT_MODEL" \
    --language "$VT_LANGUAGE" \
    --output-dir "$VT_OUTPUT" \
    --format txt md

echo "✅ 完成。逐字稿已写入 iCloud Drive，手机「文件」App 即可查看。"

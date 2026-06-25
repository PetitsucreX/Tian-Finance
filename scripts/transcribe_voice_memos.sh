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
#   VT_MODEL     whisper model (default: large-v3)
#   VT_COMPUTE   compute type (default: int8, fast on Apple Silicon CPU)
#   VT_LANGUAGE  language code or "auto" (default: auto)
#
set -euo pipefail

VT_VENV="${VT_VENV:-$HOME/Tian-Finance/.venv}"
VT_OUTPUT="${VT_OUTPUT:-$HOME/Library/Mobile Documents/com~apple~CloudDocs/VoiceMemo逐字稿}"
VT_MODEL="${VT_MODEL:-large-v3}"
VT_COMPUTE="${VT_COMPUTE:-int8}"
VT_LANGUAGE="${VT_LANGUAGE:-auto}"

# ffmpeg lives in /opt/homebrew/bin (Apple Silicon) or /usr/local/bin (Intel);
# SSH non-login shells often have a bare PATH, so add them explicitly.
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

if [ -f "$VT_VENV/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "$VT_VENV/bin/activate"
fi

mkdir -p "$VT_OUTPUT"

echo "▶︎ 转写语音备忘录 → $VT_OUTPUT"
voice-transcriber transcribe \
    --source voicememos \
    --skip-existing \
    --model "$VT_MODEL" \
    --compute-type "$VT_COMPUTE" \
    --language "$VT_LANGUAGE" \
    --output-dir "$VT_OUTPUT" \
    --format txt md

echo "✅ 完成。逐字稿已写入 iCloud Drive，手机「文件」App 即可查看。"

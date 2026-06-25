"""Command-line interface: find recordings and write verbatim transcripts."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence

from . import audio, photos, voicememos
from .formats import FORMATS, render
from .models import MediaItem
from .transcribe import DEFAULT_MODEL, Transcriber


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, pattern)
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"unrecognised date: {value!r} (use YYYY-MM-DD)")


def collect_media(args: argparse.Namespace) -> List[MediaItem]:
    """Find candidate recordings from the chosen source."""
    if args.source == "folder":
        if not args.folder:
            raise SystemExit("error: --source folder requires --folder PATH")
        items = photos.find_in_folder(
            Path(args.folder),
            recursive=not args.no_recursive,
            videos_only=args.videos_only,
            since=args.since,
            until=args.until,
        )
    elif args.source == "voicememos":
        items = voicememos.find_voice_memos(
            recordings_dir=Path(args.recordings_dir) if args.recordings_dir else None,
            since=args.since,
            until=args.until,
        )
    else:
        items = photos.find_in_photos(
            videos_only=args.videos_only,
            since=args.since,
            until=args.until,
            library_path=Path(args.library) if args.library else None,
        )
    return photos.filter_available(items)


def annotate_speech(items: Sequence[MediaItem], detect: bool) -> None:
    """Fill in ``has_audio`` / ``has_speech`` for each item (best effort)."""
    for item in items:
        item.has_audio = audio.has_audio_stream(item.path)
        if detect and item.has_audio:
            item.has_speech, item.speech_seconds = audio.detect_speech(item.path)


def _print_listing(items: Sequence[MediaItem], detect: bool) -> None:
    if not items:
        print("没有找到符合条件的录音/视频。")
        return
    print(f"找到 {len(items)} 个候选录音/视频：\n")
    for i, it in enumerate(items, 1):
        when = it.created.strftime("%Y-%m-%d %H:%M") if it.created else "时间未知"
        flags = []
        if it.has_audio is False:
            flags.append("无音轨")
        if detect and it.has_speech is not None:
            flags.append("有语音" if it.has_speech else "无语音")
            if it.speech_seconds:
                flags.append(f"{it.speech_seconds:.0f}s语音")
        tag = f"  [{', '.join(flags)}]" if flags else ""
        print(f"{i:>3}. {it.filename}  ({when}){tag}")
        print(f"     {it.path}")


def cmd_find(args: argparse.Namespace) -> int:
    items = collect_media(args)
    annotate_speech(items, args.detect_speech)
    if args.detect_speech:
        items = [it for it in items if it.has_speech]
    _print_listing(items, args.detect_speech)
    return 0


def _write_outputs(transcript, out_dir: Path, fmts: Sequence[str]) -> List[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(transcript.media.filename).stem
    written = []
    for fmt in fmts:
        target = out_dir / f"{stem}.{fmt}"
        target.write_text(render(transcript, fmt), encoding="utf-8")
        written.append(target)
    return written


def cmd_transcribe(args: argparse.Namespace) -> int:
    # Inputs can be explicit file paths or discovered from the source.
    if args.inputs:
        items = []
        for raw in args.inputs:
            p = Path(raw).expanduser()
            if not p.exists():
                print(f"跳过（找不到文件）: {raw}", file=sys.stderr)
                continue
            items.append(MediaItem(path=p, filename=p.name, source="folder"))
    else:
        items = collect_media(args)
        annotate_speech(items, detect=True)
        items = [it for it in items if it.has_speech]

    out_dir = Path(args.output_dir)

    if args.skip_existing:
        kept = []
        skipped = 0
        for it in items:
            primary = out_dir / f"{Path(it.filename).stem}.{args.format[0]}"
            if primary.exists():
                skipped += 1
            else:
                kept.append(it)
        if skipped:
            print(f"跳过 {skipped} 个已转写的（--skip-existing）。")
        items = kept

    if not items:
        print("没有可转写的录音/视频。")
        return 1

    if not audio.ffmpeg_available():
        print("错误：未找到 ffmpeg/ffprobe，请先安装（brew install ffmpeg）。", file=sys.stderr)
        return 2

    transcriber = Transcriber(
        model=args.model,
        device=args.device,
        compute_type=args.compute_type,
        beam_size=args.beam_size,
    )
    fmts = args.format

    failures = 0
    for i, item in enumerate(items, 1):
        print(f"[{i}/{len(items)}] 正在转写 {item.filename} …", flush=True)
        try:
            transcript = transcriber.transcribe(
                item,
                language=None if args.language == "auto" else args.language,
                initial_prompt=args.prompt,
            )
        except Exception as exc:  # noqa: BLE001 - report and continue the batch
            print(f"    失败: {exc}", file=sys.stderr)
            failures += 1
            continue
        written = _write_outputs(transcript, out_dir, fmts)
        lang = transcript.language
        chars = len(transcript.full_text)
        print(f"    完成（语言 {lang}，{chars} 字）→ {', '.join(str(w) for w in written)}")

    return 1 if failures and failures == len(items) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="voice-transcriber",
        description="找出相册里的语音视频并生成逐字稿（faster-whisper 本地转写）。",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_source_opts(p: argparse.ArgumentParser) -> None:
        p.add_argument("--source", choices=("photos", "folder", "voicememos"),
                       default="photos",
                       help="数据来源：照片库 / 文件夹 / 语音备忘录（默认 photos）")
        p.add_argument("--folder", help="--source folder 时要扫描的目录")
        p.add_argument("--library", help="自定义 Photos 资料库路径（可选）")
        p.add_argument("--recordings-dir",
                       help="--source voicememos 时自定义语音备忘录目录（可选）")
        p.add_argument("--no-recursive", action="store_true", help="文件夹模式下不递归子目录")
        p.add_argument("--videos-only", action="store_true", default=True,
                       help="只看视频（默认开启）")
        p.add_argument("--include-audio", dest="videos_only", action="store_false",
                       help="也包含纯音频文件（语音备忘录等）")
        p.add_argument("--since", type=_parse_date, help="只看此日期之后 (YYYY-MM-DD)")
        p.add_argument("--until", type=_parse_date, help="只看此日期之前 (YYYY-MM-DD)")

    p_find = sub.add_parser("find", help="列出候选的语音视频，不转写")
    add_source_opts(p_find)
    p_find.add_argument("--detect-speech", action="store_true",
                        help="用 VAD 检测每个文件是否真的有人声（较慢但更准）")
    p_find.set_defaults(func=cmd_find)

    p_tx = sub.add_parser("transcribe", help="生成逐字稿")
    add_source_opts(p_tx)
    p_tx.add_argument("inputs", nargs="*", help="直接给定的视频/音频文件路径（可多个）")
    p_tx.add_argument("--model", default=DEFAULT_MODEL, help=f"Whisper 模型（默认 {DEFAULT_MODEL}）")
    p_tx.add_argument("--language", default="auto",
                      help="语言代码 fr/zh/en…，默认 auto 自动识别")
    p_tx.add_argument("--device", default="auto", help="auto/cpu/cuda")
    p_tx.add_argument("--compute-type", default="auto",
                      help="auto/int8/int8_float16/float16/float32")
    p_tx.add_argument("--beam-size", type=int, default=5, help="beam search 宽度（默认 5）")
    p_tx.add_argument("--prompt", help="初始提示词（可写入专有名词以提升准确度）")
    p_tx.add_argument("--output-dir", default="transcripts", help="逐字稿输出目录")
    p_tx.add_argument("--skip-existing", action="store_true",
                      help="跳过输出目录里已存在逐字稿的录音（手机定时触发时建议开启）")
    p_tx.add_argument("--format", nargs="+", choices=FORMATS, default=["txt", "md"],
                      help=f"输出格式，可多选：{', '.join(FORMATS)}（默认 txt md）")
    p_tx.set_defaults(func=cmd_transcribe)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (RuntimeError, NotADirectoryError, FileNotFoundError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

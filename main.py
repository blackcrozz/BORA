#!/usr/bin/env python3
"""
AI Content Pipeline — main.py
==============================
Automate your content creation workflow:
  Raw Video → Transcribe → Caption → Translate → Clip → Export

Usage:
  # Basic: transcribe + burn captions
  python main.py --input video.mp4

  # Full pipeline: translate + styled captions + auto-clip
  python main.py --input video.mp4 --translate es --style tiktok --clip

  # Word-highlight captions (TikTok-style)
  python main.py --input video.mp4 --style tiktok --word-highlight

  # Use a specific Whisper model
  python main.py --input video.mp4 --model large

  # Generate clips using a local LLM
  python main.py --input video.mp4 --clip --clip-method llm

  # Generate clips using Google Gemini Flash (FREE)
  python main.py --input video.mp4 --clip --clip-method gemini
"""

import argparse
import sys
import time
from pathlib import Path

from pipeline import (
    extract_audio,
    transcribe_audio,
    generate_srt,
    generate_ass,
    translate_srt,
    translate_segments,
    install_language_pack,
    find_highlights,
    find_highlights_gemini,
    cut_clips,
    burn_captions,
    remove_silences,
    generate_word_by_word_ass,
)
from pipeline.srt_generator import generate_word_highlight_ass
from pipeline.smart_clip import find_highlights_llm


def parse_args():
    parser = argparse.ArgumentParser(
        description="AI Content Pipeline — Video → Captions → Translate → Clip",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Required
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Path to the input video file",
    )

    # Output
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output video path (default: output/<input>_captioned.mp4)",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Directory for all outputs (default: output/)",
    )

    # Whisper settings
    parser.add_argument(
        "--model", "-m",
        default="medium",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper model size (default: medium)",
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Source language code (e.g. 'en'). None = auto-detect.",
    )
    
    parser.add_argument(
        "--lang",
        default=None,
        dest="language",
        help="Force language for Whisper: 'id' = Indonesian, 'en' = English. Default: auto-detect",
    )
    parser.add_argument(
        "--no-bilingual-correction",
        action="store_true",
        help="Skip Gemini bilingual correction pass (faster, fully offline)",
    )

    # Caption style
    parser.add_argument(
        "--style", "-s",
        default="tiktok",
        choices=["tiktok", "youtube", "reels", "minimal", "srt"],
        help="Caption style (default: tiktok). Use 'srt' for plain subtitles.",
    )
    parser.add_argument(
        "--word-highlight",
        action="store_true",
        help="Enable per-word karaoke-style highlighting (TikTok effect)",
    )

    # Translation
    parser.add_argument(
        "--translate", "-t",
        default=None,
        metavar="LANG",
        help="Translate captions to this language code (e.g. 'es', 'fr', 'ja')",
    )
    parser.add_argument(
        "--source-lang",
        default="en",
        help="Source language for translation (default: en)",
    )

    # Clipping
    parser.add_argument(
        "--clip",
        action="store_true",
        help="Auto-generate short clips from the video",
    )
    parser.add_argument(
        "--clip-method",
        default="heuristic",
        choices=["heuristic", "llm", "gemini"],
        help="Clip detection method (default: heuristic, gemini = free Google AI)",
    )
    parser.add_argument(
        "--clip-min",
        type=float,
        default=15.0,
        help="Minimum clip duration in seconds (default: 15)",
    )
    parser.add_argument(
        "--clip-max",
        type=float,
        default=60.0,
        help="Maximum clip duration in seconds (default: 60)",
    )
    parser.add_argument(
        "--num-clips",
        type=int,
        default=3,
        help="Number of clips for LLM method (default: 3)",
    )

    # Encoding
    parser.add_argument(
        "--gpu",
        action="store_true",
        help="Use NVIDIA GPU encoding (NVENC) for faster export",
    )
    parser.add_argument(
        "--crf",
        type=int,
        default=23,
        help="Video quality (CRF). Lower = better. Range: 18-28 (default: 23)",
    )

    # Flags
    parser.add_argument(
        "--srt-only",
        action="store_true",
        help="Only generate subtitles (skip video encoding)",
    )
    parser.add_argument(
        "--skip-captions",
        action="store_true",
        help="Skip burning captions (useful with --clip)",
    )
    
    # Silence removal
    parser.add_argument(
        "--remove-silences",
        action="store_true",
        help="Auto-remove silent pauses from video before processing",
    )
    parser.add_argument(
        "--silence-threshold",
        type=float,
        default=-35.0,
        help="dB threshold for silence detection (default: -35)",
    )
    parser.add_argument(
        "--min-silence",
        type=float,
        default=0.5,
        help="Minimum silence duration to remove in seconds (default: 0.5)",
    )
    # Word-by-word captions
    parser.add_argument(
        "--word-by-word",
        action="store_true",
        help="Show captions word-by-word (large font, TikTok style)",
    )
    parser.add_argument(
        "--words-per-line",
        type=int,
        default=2,
        help="Words to show at a time with --word-by-word (default: 2)",
    )
    
    # Filler removal
    parser.add_argument(
        "--remove-fillers",
        action="store_true",
        help="Remove filler words (uh, uhm, err) and repetitions from video",
    )
    # Keyword highlighting
    parser.add_argument(
        "--highlight-keywords",
        action="store_true",
        help="AI-detect and highlight important words in captions (yellow)",
    )

    return parser.parse_args()


def main():
    args = parse_args()
    start_time = time.time()

    # Validate input
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)

    # Setup output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = input_path.stem

    print("=" * 60)
    print("  AI Content Pipeline")
    print("=" * 60)
    print(f"  Input:      {input_path}")
    print(f"  Model:      Whisper {args.model}")
    print(f"  Style:      {args.style}")
    if args.translate:
        print(f"  Translate:  {args.source_lang} → {args.translate}")
    if args.clip:
        print(f"  Clipping:   {args.clip_method} (min={args.clip_min}s, max={args.clip_max}s)")
    print("=" * 60)

   
    
    # ------------------------------------------------------------------
    # Step 0: Remove silences FIRST (before transcription)
    # ------------------------------------------------------------------
    if args.remove_silences:
        print(f"\n[Step 0] Removing silences...")
        clean_path = str(output_dir / f"{stem}_clean.mp4")
        remove_silences(
            str(input_path),
            clean_path,
            silence_threshold=args.silence_threshold,
            min_silence_duration=args.min_silence,
        )
        input_path = Path(clean_path)
        stem = input_path.stem

    # ------------------------------------------------------------------
    # Step 1: Extract audio (from cleaned video if silence removed)
    # ------------------------------------------------------------------
    audio_path = str(output_dir / f"{stem}_audio.wav")
    extract_audio(str(input_path), audio_path)

    # ------------------------------------------------------------------
    # Step 2: Transcribe with Whisper
    # ------------------------------------------------------------------
    result = transcribe_audio(
        audio_path,
        model_name=args.model,
        language=args.language,
        word_timestamps=True,
        bilingual_correction=not args.no_bilingual_correction,
    )
    segments = result["segments"]

    # ------------------------------------------------------------------
    # Step 2b: Remove filler words (optional)
    # ------------------------------------------------------------------
    if args.remove_fillers:
        from pipeline.silence_remover import get_video_duration
        from pipeline.filler_remover import clean_segments, cut_filler_segments
        print("\n[Step 2b] Removing filler words and repetitions...")
        segments, removed_intervals = clean_segments(segments)
        if removed_intervals:
            dur = get_video_duration(str(input_path))
            filler_free_path = str(output_dir / f"{stem}_nofiller.mp4")
            cut_filler_segments(
                str(input_path), filler_free_path,
                removed_intervals, dur
            )
            input_path = Path(filler_free_path)
            stem = input_path.stem
    
    # ------------------------------------------------------------------
    # Step 3: Generate subtitle files
    # ------------------------------------------------------------------
    srt_path = str(output_dir / f"{stem}.srt")
    generate_srt(segments, srt_path)
    burn_subtitle = srt_path

    # Extract keywords if requested
    important_words = set()
    if args.highlight_keywords:
        from pipeline.keyword_extractor import extract_keywords_gemini
        important_words = extract_keywords_gemini(segments)

    if args.style != "srt":
        if args.word_by_word:
            ass_path = str(output_dir / f"{stem}_wbw.ass")
            if args.highlight_keywords and important_words:
                from pipeline.srt_generator import generate_highlighted_word_by_word_ass
                generate_highlighted_word_by_word_ass(
                    segments, ass_path,
                    important_words=important_words,
                    style=args.style,
                    words_per_line=args.words_per_line,
                )
            else:
                generate_word_by_word_ass(
                    segments, ass_path,
                    style=args.style,
                    words_per_line=args.words_per_line,
                )
            burn_subtitle = ass_path
        elif args.word_highlight:
            ass_path = str(output_dir / f"{stem}_highlight.ass")
            generate_word_highlight_ass(segments, ass_path, style=args.style)
            burn_subtitle = ass_path
        else:
            ass_path = str(output_dir / f"{stem}.ass")
            generate_ass(segments, ass_path, style=args.style)
            burn_subtitle = ass_path
            
    # ------------------------------------------------------------------
    # Step 4: Translate (optional)
    # ------------------------------------------------------------------
    if args.translate:
        try:
            install_language_pack(args.source_lang, args.translate)
        except Exception as e:
            print(f"  ⚠ Language pack install: {e}")

        # Translate segments for potential clip captions too
        translated_segments = translate_segments(
            segments, args.source_lang, args.translate
        )

        # Generate translated subtitle files
        trans_srt_path = str(output_dir / f"{stem}_{args.translate}.srt")
        generate_srt(translated_segments, trans_srt_path)

        if args.style != "srt":
            trans_ass_path = str(output_dir / f"{stem}_{args.translate}.ass")
            if args.word_highlight:
                generate_word_highlight_ass(
                    translated_segments, trans_ass_path, style=args.style
                )
            else:
                generate_ass(translated_segments, trans_ass_path, style=args.style)
            burn_subtitle = trans_ass_path
        else:
            burn_subtitle = trans_srt_path

    # ------------------------------------------------------------------
    # Step 5: Auto-clip (optional)
    # ------------------------------------------------------------------
    if args.clip:
        if args.clip_method == "gemini":
            clips = find_highlights_gemini(
                segments,
                num_clips=args.num_clips,
                min_duration=args.clip_min,
                max_duration=args.clip_max,
            )
        elif args.clip_method == "llm":
            clips = find_highlights_llm(
                segments, num_clips=args.num_clips
            )
        else:
            clips = find_highlights(
                segments,
                min_duration=args.clip_min,
                max_duration=args.clip_max,
            )

        if clips:
            clip_dir = str(output_dir / "clips")
            cut_clips(str(input_path), clips, output_dir=clip_dir, prefix=stem)

    # ------------------------------------------------------------------
    # Step 6: Burn captions onto video
    # ------------------------------------------------------------------
    if not args.srt_only and not args.skip_captions:
        if args.output:
            final_output = args.output
        else:
            suffix = f"_{args.translate}" if args.translate else ""
            final_output = str(output_dir / f"{stem}_captioned{suffix}.mp4")

        codec = "h264_nvenc" if args.gpu else "libx264"
        burn_captions(
            str(input_path),
            burn_subtitle,
            final_output,
            video_codec=codec,
            crf=args.crf,
        )

    # ------------------------------------------------------------------
    # Done!
    # ------------------------------------------------------------------
    elapsed = time.time() - start_time
    print()
    print("=" * 60)
    print(f"  ✅ Pipeline complete in {elapsed:.1f}s")
    print(f"  📂 Outputs saved to: {output_dir}/")
    print("=" * 60)


if __name__ == "__main__":
    main()

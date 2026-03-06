"""
Step 3: Generate subtitle files from Whisper segments.

Supports two formats:
  - SRT  — simple, widely compatible
  - ASS  — Advanced SubStation Alpha (styled captions, animations)
"""

from pathlib import Path


# ---------------------------------------------------------------------------
# Time formatting helpers
# ---------------------------------------------------------------------------

def _format_srt_time(seconds: float) -> str:
    """Format seconds as SRT timestamp: HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _format_ass_time(seconds: float) -> str:
    """Format seconds as ASS timestamp: H:MM:SS.cc (centiseconds)"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


# ---------------------------------------------------------------------------
# SRT generation
# ---------------------------------------------------------------------------

def generate_srt(segments: list[dict], output_path: str) -> str:
    """
    Generate an SRT subtitle file from Whisper segments.

    Args:
        segments:     List of segment dicts with "start", "end", "text".
        output_path:  Where to write the .srt file.

    Returns:
        Path to the generated SRT file.
    """
    lines = []
    for i, seg in enumerate(segments, 1):
        start = _format_srt_time(seg["start"])
        end = _format_srt_time(seg["end"])
        text = seg["text"].strip()
        lines.append(f"{i}\n{start} --> {end}\n{text}\n")

    content = "\n".join(lines)
    Path(output_path).write_text(content, encoding="utf-8")

    print(f"[Step 3] SRT saved: {output_path}  ({len(segments)} subtitles)")
    return output_path


# ---------------------------------------------------------------------------
# ASS generation (styled captions)
# ---------------------------------------------------------------------------

# Pre-built style presets
STYLE_PRESETS = {
    "tiktok": {
        "fontname": "Montserrat",
        "fontsize": 28,
        "primary_color": "&H00FFFFFF",   # White
        "outline_color": "&H00000000",   # Black outline
        "bold": 1,
        "outline": 3,
        "shadow": 1,
        "alignment": 2,                  # Bottom center
        "margin_v": 60,
    },
    "youtube": {
        "fontname": "Arial",
        "fontsize": 22,
        "primary_color": "&H00FFFFFF",
        "outline_color": "&H00000000",
        "bold": 0,
        "outline": 2,
        "shadow": 0,
        "alignment": 2,
        "margin_v": 30,
    },
    "reels": {
        "fontname": "Futura",
        "fontsize": 32,
        "primary_color": "&H0000FFFF",   # Yellow (BGR)
        "outline_color": "&H00000000",
        "bold": 1,
        "outline": 4,
        "shadow": 2,
        "alignment": 5,                  # Center of screen
        "margin_v": 0,
    },
    "minimal": {
        "fontname": "Helvetica",
        "fontsize": 20,
        "primary_color": "&H00FFFFFF",
        "outline_color": "&H64000000",
        "bold": 0,
        "outline": 0,
        "shadow": 0,
        "alignment": 2,
        "margin_v": 20,
    },
}


def generate_ass(
    segments: list[dict],
    output_path: str,
    style: str = "tiktok",
    video_width: int = 1080,
    video_height: int = 1920,
    fade_ms: int = 150,
) -> str:
    """
    Generate an ASS subtitle file with styled, animated captions.

    Args:
        segments:      List of segment dicts with "start", "end", "text".
        output_path:   Where to write the .ass file.
        style:         Style preset name ("tiktok", "youtube", "reels", "minimal").
        video_width:   Video width in pixels.
        video_height:  Video height in pixels.
        fade_ms:       Fade in/out duration in milliseconds.

    Returns:
        Path to the generated ASS file.
    """
    preset = STYLE_PRESETS.get(style, STYLE_PRESETS["tiktok"])

    header = f"""[Script Info]
Title: AI Content Pipeline Captions
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{preset["fontname"]},{preset["fontsize"]},{preset["primary_color"]},&H000000FF,{preset["outline_color"]},&H80000000,{preset["bold"]},0,0,0,100,100,0,0,1,{preset["outline"]},{preset["shadow"]},{preset["alignment"]},40,40,{preset["margin_v"]},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []
    for seg in segments:
        start = _format_ass_time(seg["start"])
        end = _format_ass_time(seg["end"])
        text = seg["text"].strip()

        # Add fade animation
        styled_text = f"{{\\fad({fade_ms},{fade_ms})}}{text}"

        events.append(
            f"Dialogue: 0,{start},{end},Default,,0,0,0,,{styled_text}"
        )

    content = header + "\n".join(events) + "\n"
    Path(output_path).write_text(content, encoding="utf-8")

    print(f"[Step 3] ASS saved: {output_path}  (style: {style}, {len(segments)} subtitles)")
    return output_path


def generate_word_highlight_ass(
    segments: list[dict],
    output_path: str,
    style: str = "tiktok",
    highlight_color: str = "&H0000FFFF",  # Yellow (BGR format)
    video_width: int = 1080,
    video_height: int = 1920,
) -> str:
    """
    Generate ASS subtitles with per-word karaoke-style highlighting.

    Each word lights up at its timestamp, creating that TikTok/Reels effect
    where the current word is highlighted in a different color.

    Requires word_timestamps=True in the Whisper transcription.

    Args:
        segments:        Whisper segments with "words" sub-list.
        output_path:     Where to write the .ass file.
        style:           Style preset name.
        highlight_color: ASS color for the highlighted word (BGR format).
        video_width:     Video width.
        video_height:    Video height.

    Returns:
        Path to the generated ASS file.
    """
    preset = STYLE_PRESETS.get(style, STYLE_PRESETS["tiktok"])

    header = f"""[Script Info]
Title: AI Content Pipeline - Word Highlight Captions
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{preset["fontname"]},{preset["fontsize"]},{preset["primary_color"]},&H000000FF,{preset["outline_color"]},&H80000000,{preset["bold"]},0,0,0,100,100,0,0,1,{preset["outline"]},{preset["shadow"]},{preset["alignment"]},40,40,{preset["margin_v"]},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []

    for seg in segments:
        words = seg.get("words", [])
        if not words:
            # Fallback: show the whole segment without word highlighting
            start = _format_ass_time(seg["start"])
            end = _format_ass_time(seg["end"])
            events.append(
                f"Dialogue: 0,{start},{end},Default,,0,0,0,,{seg['text'].strip()}"
            )
            continue

        seg_start = _format_ass_time(seg["start"])
        seg_end = _format_ass_time(seg["end"])

        # Build karaoke-style override tags
        # Each word gets a {\kf<duration>} tag that controls highlight timing
        karaoke_parts = []
        for word_info in words:
            word = word_info.get("word", "").strip()
            if not word:
                continue
            duration_cs = int(
                (word_info.get("end", 0) - word_info.get("start", 0)) * 100
            )
            duration_cs = max(duration_cs, 1)
            karaoke_parts.append(f"{{\\kf{duration_cs}}}{word}")

        line = f"{{\\1c{highlight_color}}}" + " ".join(karaoke_parts)
        events.append(
            f"Dialogue: 0,{seg_start},{seg_end},Default,,0,0,0,,{line}"
        )

    content = header + "\n".join(events) + "\n"
    Path(output_path).write_text(content, encoding="utf-8")

    print(f"[Step 3] Word-highlight ASS saved: {output_path}  ({len(events)} lines)")
    return output_path

def generate_word_by_word_ass(
    segments: list[dict],
    output_path: str,
    style: str = "tiktok",
    words_per_line: int = 2,
    fontsize: int = 52,
    video_width: int = 1080,
    video_height: int = 1920,
) -> str:
    """
    Generate ASS captions showing a few words at a time — TikTok/Reels style.

    Each caption shows only 1-3 words at a time, large font, centered.
    Requires word_timestamps=True in Whisper transcription.

    Args:
        segments:       Whisper segments with "words" sub-list.
        output_path:    Where to write the .ass file.
        style:          Style preset name.
        words_per_line: How many words to show at once (default: 2).
        fontsize:       Font size (default: 52 — big and bold).
        video_width:    Video width.
        video_height:   Video height.

    Returns:
        Path to the generated ASS file.
    """
    preset = STYLE_PRESETS.get(style, STYLE_PRESETS["tiktok"])

    header = f"""[Script Info]
Title: BORA Word-by-Word Captions
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{preset["fontname"]},{fontsize},{preset["primary_color"]},&H000000FF,{preset["outline_color"]},&H80000000,1,0,0,0,100,100,0,0,1,{preset["outline"]},{preset["shadow"]},5,40,40,80,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []

    for seg in segments:
        words = seg.get("words", [])

        if not words:
            # Fallback: show full segment text if no word timestamps
            start = _format_ass_time(seg["start"])
            end = _format_ass_time(seg["end"])
            text = seg["text"].strip().upper()
            events.append(
                f"Dialogue: 0,{start},{end},Default,,0,0,0,,{{\\fad(80,80)}}{text}"
            )
            continue

        # Group words into chunks of words_per_line
        chunks = []
        for i in range(0, len(words), words_per_line):
            chunk = words[i:i + words_per_line]
            if not chunk:
                continue

            chunk_start = chunk[0].get("start", seg["start"])
            chunk_end = chunk[-1].get("end", seg["end"])

            # Make sure end is after start
            if chunk_end <= chunk_start:
                chunk_end = chunk_start + 0.3

            text = " ".join(
                w.get("word", "").strip() for w in chunk if w.get("word", "").strip()
            ).upper()

            if text:
                chunks.append({
                    "start": chunk_start,
                    "end": chunk_end,
                    "text": text,
                })

        for chunk in chunks:
            start = _format_ass_time(chunk["start"])
            end = _format_ass_time(chunk["end"])
            # Bold + fade in/out + scale pop effect
            styled = f"{{\\fad(60,60)\\t(0,80,\\fscx110\\fscy110)\\t(80,160,\\fscx100\\fscy100)}}{chunk['text']}"
            events.append(
                f"Dialogue: 0,{start},{end},Default,,0,0,0,,{styled}"
            )

    content = header + "\n".join(events) + "\n"
    Path(output_path).write_text(content, encoding="utf-8")

    print(f"[Step 3] Word-by-word ASS saved: {output_path}  ({len(events)} caption lines)")
    return output_path
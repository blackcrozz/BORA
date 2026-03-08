"""
Filler Word & Repetition Remover — Indonesian + English Bilingual
Version 2: Strength picker, AI context review, audio-safe cuts, precise timing.
"""

import json
import os
import re
import subprocess
import shutil
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

try:
    from google import genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


def _strength_to_max_duration(strength: int) -> float:
    strength = max(0, min(100, strength))
    if strength <= 50:
        return 0.15 + (strength / 50) * 0.30
    else:
        return 0.45 + ((strength - 50) / 50) * 0.75


def _strength_to_confidence(strength: int) -> str:
    if strength <= 25:
        return "VERY conservative — only flag obvious pure sounds (uh, um, hmm). When in doubt, KEEP."
    elif strength <= 50:
        return "Conservative — flag clear filler sounds and very short meaningless particles. When in doubt, KEEP."
    elif strength <= 75:
        return "Moderate — flag fillers and contextually unnecessary particles. Use judgment."
    else:
        return "Aggressive — flag all fillers, unnecessary particles, and redundant phrases. Prefer removing."


ALWAYS_FILLER = {
    "uh", "uhh", "uhm", "um", "umm", "emmm", "em",
    "eh", "ehm", "eeh", "eehh",
    "hmm", "hm", "hmmm", "hmmmm",
    "ah", "ahh", "ahhh",
    "err", "errr", "errrr",
}

CONTEXT_DEPENDENT_ID = {
    "ya", "yaa", "nah", "kan", "tuh", "nih",
    "dong", "deh", "loh", "lho", "lo",
    "kok", "sih", "gitu", "gini",
}

FILLER_PHRASES = [
    r"\bgimana\s+ya\b", r"\bya\s+kan\b", r"\bkan\s+ya\b",
    r"\bgitu\s+loh\b", r"\bgitu\s+deh\b", r"\bjadi\s+gitu\b",
    r"\byou\s+know\b", r"\bi\s+mean\b",
]
COMPILED_PHRASES = [re.compile(p, re.IGNORECASE) for p in FILLER_PHRASES]


def _is_filler_heuristic(word: dict, idx: int, all_words: list, max_dur: float) -> bool:
    text = re.sub(r"[^\w]", "", word.get("word", "")).lower().strip()
    if not text:
        return False
    duration = word.get("end", 0) - word.get("start", 0)
    if text in ALWAYS_FILLER:
        return True
    if text in CONTEXT_DEPENDENT_ID:
        if duration > max_dur:
            return False
        if idx == 0 or idx == len(all_words) - 1:
            return False
        return True
    if idx > 0:
        prev = re.sub(r"[^\w]", "", all_words[idx-1].get("word", "")).lower()
        if text == prev and text not in {"the", "a", "di", "ke", "dan", ""}:
            return True
    return False


def detect_fillers_heuristic(segments: list[dict], strength: int = 50) -> list[dict]:
    max_dur = _strength_to_max_duration(strength)
    all_words = []
    for seg in segments:
        all_words.extend(seg.get("words", []))
    fillers = [
        w for i, w in enumerate(all_words)
        if _is_filler_heuristic(w, i, all_words, max_dur)
    ]
    print(f"[Filler] Heuristic flagged {len(fillers)} words (strength={strength}, max_dur={max_dur:.2f}s)")
    return fillers


def detect_fillers_gemini(segments: list[dict], strength: int = 50) -> list[dict]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or not GEMINI_AVAILABLE:
        return detect_fillers_heuristic(segments, strength)

    max_dur = _strength_to_max_duration(strength)
    confidence_instruction = _strength_to_confidence(strength)

    candidates = detect_fillers_heuristic(segments, strength=min(strength + 20, 100))
    if not candidates:
        print("[Filler] No filler candidates found.")
        return []

    all_words = []
    for seg in segments:
        all_words.extend(seg.get("words", []))
    word_texts = [w.get("word", "").strip() for w in all_words]

    candidate_contexts = []
    for cand in candidates:
        cand_start = cand.get("start", 0)
        pos = next(
            (i for i, w in enumerate(all_words)
             if abs(w.get("start", 0) - cand_start) < 0.05),
            None
        )
        if pos is None:
            continue
        ctx_start = max(0, pos - 5)
        ctx_end = min(len(word_texts), pos + 6)
        before = " ".join(word_texts[ctx_start:pos])
        after = " ".join(word_texts[pos+1:ctx_end])
        word = word_texts[pos]
        duration = cand.get("end", 0) - cand.get("start", 0)
        candidate_contexts.append({
            "word": word,
            "start": cand_start,
            "duration": round(duration, 3),
            "context": f"...{before} [{word}] {after}...",
            "original": cand,
        })

    if not candidate_contexts:
        return []

    confirmed_fillers = []
    batch_size = 50

    for i in range(0, len(candidate_contexts), batch_size):
        batch = candidate_contexts[i:i + batch_size]
        items = "\n".join(
            f"{j}. word=\"{c['word']}\" duration={c['duration']}s context=\"{c['context']}\""
            for j, c in enumerate(batch)
        )

        prompt = f"""You are reviewing candidate filler words from bilingual Indonesian-English speech for removal.

Strength level: {strength}/100 — {confidence_instruction}

For each candidate, decide: REMOVE or KEEP.
Consider:
- Is it a pure thinking sound (uh, um, hmm)? → REMOVE
- Is it a short meaningless particle given this context? → depends on strength
- Does it carry actual meaning in this sentence? → KEEP
- Is the surrounding speech coherent without it? → helps decide
- Duration threshold: words longer than {max_dur:.2f}s are likely meaningful → prefer KEEP

CANDIDATES:
{items}

Respond ONLY with JSON array of indices to REMOVE (0-based). Empty array if none:
[0, 2, 5]"""

        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model="gemini-3.1-flash-lite-preview",
                contents=prompt,
            )
            text = response.text.strip()
            if "[" in text:
                text = text[text.index("["):text.rindex("]") + 1]
            indices = json.loads(text)
            for idx in indices:
                if 0 <= idx < len(batch):
                    confirmed_fillers.append(batch[idx]["original"])
        except Exception as e:
            print(f"  [Filler] Gemini review error: {e}, using heuristic for batch")
            confirmed_fillers.extend([c["original"] for c in batch])

    print(f"[Filler] Gemini confirmed {len(confirmed_fillers)} fillers (strength={strength})")
    return confirmed_fillers


def clean_segments(
    segments: list[dict],
    strength: int = 50,
    use_gemini: bool = True,
) -> tuple[list[dict], list[dict]]:
    if use_gemini and os.getenv("GEMINI_API_KEY") and GEMINI_AVAILABLE:
        filler_list = detect_fillers_gemini(segments, strength)
    else:
        filler_list = detect_fillers_heuristic(segments, strength)

    if not filler_list:
        return segments, []

    filler_intervals = _merge_intervals([
        {"start": w.get("start", 0), "end": w.get("end", 0)}
        for w in filler_list
        if w.get("end", 0) > w.get("start", 0)
    ], gap=0.08)

    def is_filler_time(start, end):
        for fi in filler_intervals:
            if start >= fi["start"] - 0.05 and end <= fi["end"] + 0.05:
                return True
        return False

    cleaned = []
    for seg in segments:
        words = seg.get("words", [])
        if not words:
            cleaned.append(seg)
            continue
        kept = [w for w in words if not is_filler_time(
            w.get("start", 0), w.get("end", 0)
        )]
        if not kept:
            continue
        new_seg = dict(seg)
        new_seg["words"] = kept
        new_seg["text"] = " ".join(w.get("word", "").strip() for w in kept)
        new_seg["start"] = kept[0].get("start", seg["start"])
        new_seg["end"] = kept[-1].get("end", seg["end"])
        cleaned.append(new_seg)

    print(f"[Filler] {len(filler_intervals)} intervals to remove from video")
    return cleaned, filler_intervals


def remap_timestamps(
    segments: list[dict],
    removed_intervals: list[dict],
) -> list[dict]:
    if not removed_intervals:
        return segments

    sorted_intervals = sorted(removed_intervals, key=lambda x: x["start"])

    def remap_time(t: float) -> float:
        offset = 0.0
        for iv in sorted_intervals:
            if iv["start"] >= t:
                break
            overlap_end = min(iv["end"], t)
            overlap = overlap_end - iv["start"]
            if overlap > 0:
                offset += overlap
        return max(0.0, round(t - offset, 4))

    remapped = []
    for seg in segments:
        new_seg = dict(seg)
        new_seg["start"] = remap_time(seg["start"])
        new_seg["end"] = remap_time(seg["end"])
        new_words = []
        for w in seg.get("words", []):
            new_w = dict(w)
            new_w["start"] = remap_time(w.get("start", seg["start"]))
            new_w["end"] = remap_time(w.get("end", seg["end"]))
            new_words.append(new_w)
        new_seg["words"] = new_words
        remapped.append(new_seg)

    print("[Filler] Timestamps precisely remapped ✓")
    return remapped


def cut_filler_segments(
    video_path: str,
    output_path: str,
    removed_intervals: list[dict],
    total_duration: float,
    padding: float = 0.04,
    crossfade_ms: int = 30,
) -> str:
    if not removed_intervals:
        shutil.copy2(video_path, output_path)
        return output_path

    keep = []
    current = 0.0
    for iv in removed_intervals:
        end = iv["start"] - padding
        if end > current + 0.05:
            keep.append({"start": current, "end": end})
        current = iv["end"] + padding
    if current < total_duration:
        keep.append({"start": current, "end": total_duration})
    keep = [s for s in keep if s["end"] - s["start"] > 0.05]

    if not keep:
        shutil.copy2(video_path, output_path)
        return output_path

    print(f"[Filler] Cutting: {len(keep)} segments kept, {len(removed_intervals)} removed")

    cf_duration = crossfade_ms / 1000.0
    n = len(keep)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    video_filters = []
    audio_filters = []
    for i, seg in enumerate(keep):
        s, e = seg["start"], seg["end"]
        fade_dur = min(cf_duration, (e - s) / 4)
        video_filters.append(
            f"[0:v]trim=start={s}:end={e},setpts=PTS-STARTPTS[v{i}]"
        )
        audio_filters.append(
            f"[0:a]atrim=start={s}:end={e},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d={fade_dur},"
            f"afade=t=out:st={max(0, e-s-fade_dur)}:d={fade_dur}[a{i}]"
        )

    v_labels = "".join(f"[v{i}]" for i in range(n))
    a_labels = "".join(f"[a{i}]" for i in range(n))

    filter_complex = ";".join(video_filters + audio_filters + [
        f"{v_labels}concat=n={n}:v=1:a=0[vout]",
        f"{a_labels}concat=n={n}:v=0:a=1[aout]",
    ])

    cmd = [
        "ffmpeg", "-i", str(video_path),
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-crf", "23", "-preset", "fast",
        "-c:a", "aac", "-b:a", "192k",
        "-y", str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg error:\n{result.stderr[-500:]}")

    size_mb = Path(output_path).stat().st_size / (1024 * 1024)
    print(f"  ✓ Filler-free video: {output_path} ({size_mb:.1f} MB)")
    return output_path


def _merge_intervals(intervals: list[dict], gap: float = 0.05) -> list[dict]:
    if not intervals:
        return []
    sorted_iv = sorted(intervals, key=lambda x: x["start"])
    merged = [sorted_iv[0].copy()]
    for iv in sorted_iv[1:]:
        if iv["start"] <= merged[-1]["end"] + gap:
            merged[-1]["end"] = max(merged[-1]["end"], iv["end"])
        else:
            merged.append(iv.copy())
    return merged
"""
AI Transcript Reviewer — BORA Pipeline
Reviews full transcript before cuts are applied.
Protects sentence meaning and content essence.
"""

import json
import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_MODEL = "gemini-3.1-flash-lite-preview"

try:
    from google import genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


# ─────────────────────────────────────────────
# DATA STRUCTURES
# ─────────────────────────────────────────────

class ReviewResult:
    def __init__(self):
        self.safe_cuts: list[dict] = []          # intervals approved to cut
        self.protected_intervals: list[dict] = [] # intervals that must NOT be cut
        self.sentence_reviews: list[dict] = []    # per-sentence analysis
        self.summary: str = ""                    # overall content summary
        self.warnings: list[str] = []             # sentences at risk


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _segments_to_paragraphs(segments: list[dict]) -> list[dict]:
    """
    Group word-level segments into natural sentence paragraphs
    for easier AI reading. Returns list of paragraph dicts with
    full text, start, end, and words.
    """
    paragraphs = []
    buffer_words = []
    buffer_text = []
    buffer_start = None

    for seg in segments:
        words = seg.get("words", [])
        text = seg.get("text", "").strip()
        seg_start = seg.get("start", 0)
        seg_end = seg.get("end", 0)

        if buffer_start is None:
            buffer_start = seg_start

        buffer_words.extend(words)
        buffer_text.append(text)

        # Paragraph break: segment ends with sentence-ending punctuation
        # or there's a gap >1.5s to the next segment
        ends_sentence = text.endswith((".", "!", "?", "..."))
        if ends_sentence or len(buffer_text) >= 5:
            paragraphs.append({
                "start": buffer_start,
                "end": seg_end,
                "text": " ".join(buffer_text),
                "words": list(buffer_words),
            })
            buffer_words = []
            buffer_text = []
            buffer_start = None

    # flush remaining
    if buffer_text:
        last_end = segments[-1].get("end", 0) if segments else 0
        paragraphs.append({
            "start": buffer_start or 0,
            "end": last_end,
            "text": " ".join(buffer_text),
            "words": list(buffer_words),
        })

    return paragraphs


def _find_silence_gaps(segments: list[dict], min_gap: float = 0.4) -> list[dict]:
    """
    Detect silence gaps between segments that are candidates for removal.
    Returns list of gap dicts: {start, end, duration}.
    """
    gaps = []
    for i in range(1, len(segments)):
        prev_end = segments[i - 1].get("end", 0)
        curr_start = segments[i].get("start", 0)
        gap = curr_start - prev_end
        if gap >= min_gap:
            gaps.append({
                "start": prev_end,
                "end": curr_start,
                "duration": round(gap, 3),
                "before_text": segments[i - 1].get("text", "")[-50:],
                "after_text": segments[i].get("text", "")[:50],
            })
    return gaps


def _find_filler_candidates(segments: list[dict]) -> list[dict]:
    """
    Quick heuristic scan for likely filler words with their context.
    These are passed to AI for contextual review.
    """
    FILLERS = {
        "uh", "uhh", "um", "umm", "hmm", "hm", "ah", "ahh",
        "eh", "ya", "yaa", "kan", "tuh", "nih", "dong", "deh",
        "loh", "sih", "gitu", "kok", "i mean", "you know",
    }
    candidates = []
    for seg in segments:
        words = seg.get("words", [])
        seg_text = seg.get("text", "")
        for i, w in enumerate(words):
            word = w.get("word", "").strip().lower()
            word_clean = "".join(c for c in word if c.isalpha())
            if word_clean in FILLERS:
                before = " ".join(
                    words[j].get("word", "") for j in range(max(0, i-4), i)
                )
                after = " ".join(
                    words[j].get("word", "") for j in range(i+1, min(len(words), i+5))
                )
                duration = w.get("end", 0) - w.get("start", 0)
                candidates.append({
                    "word": word,
                    "start": w.get("start", 0),
                    "end": w.get("end", 0),
                    "duration": round(duration, 3),
                    "context": f"...{before} [{word}] {after}...",
                    "segment_text": seg_text,
                })
    return candidates


# ─────────────────────────────────────────────
# MAIN AI REVIEW
# ─────────────────────────────────────────────

def review_transcript(
    segments: list[dict],
    language: str = "id",
    strength: int = 50,
) -> ReviewResult:
    """
    Full AI review of transcript before any cuts are applied.

    Steps:
    1. Summarize overall content + purpose
    2. Review each sentence for meaning completeness
    3. Evaluate silence gaps — safe to cut or not
    4. Evaluate filler candidates in context
    5. Return ReviewResult with safe_cuts and protected_intervals

    Falls back gracefully if Gemini is unavailable.
    """
    result = ReviewResult()

    if not segments:
        print("[AIReview] No segments to review.")
        return result

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or not GEMINI_AVAILABLE:
        print("[AIReview] Gemini not available, skipping AI review.")
        return result

    paragraphs = _segments_to_paragraphs(segments)
    silence_gaps = _find_silence_gaps(segments, min_gap=0.3)
    filler_candidates = _find_filler_candidates(segments)

    full_transcript = "\n".join(
        f"[{p['start']:.2f}s–{p['end']:.2f}s] {p['text']}"
        for p in paragraphs
    )

    # ── STEP 1: Content Summary + Sentence Review ──
    print("[AIReview] Step 1: Reviewing sentence purposes...")

    sentence_prompt = f"""You are a professional video editor's AI assistant reviewing a transcript before cutting.
Language: {"Indonesian (Bahasa Indonesia)" if language == "id" else "English"}

Your job:
1. Summarize what this video is about in 1-2 sentences
2. For each sentence/paragraph, rate its importance (HIGH/MEDIUM/LOW) and check if it can stand alone after cuts

TRANSCRIPT:
{full_transcript}

Respond ONLY with JSON:
{{
  "summary": "Brief description of video content",
  "sentences": [
    {{
      "start": 0.0,
      "end": 5.0,
      "text": "sentence text",
      "importance": "HIGH",
      "complete_after_cut": true,
      "reason": "Why this matters or doesn't"
    }}
  ]
}}"""

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=sentence_prompt,
        )
        text = response.text.strip()
        if "```" in text:
            text = text[text.index("{"):text.rindex("}") + 1]
        data = json.loads(text)

        result.summary = data.get("summary", "")
        result.sentence_reviews = data.get("sentences", [])

        print(f"  ✓ Summary: {result.summary}")
        print(f"  ✓ Reviewed {len(result.sentence_reviews)} sentences")

        # Mark LOW importance sentences with incomplete cuts as warnings
        for s in result.sentence_reviews:
            if not s.get("complete_after_cut", True):
                result.warnings.append(
                    f"[{s['start']:.1f}s] '{s['text'][:60]}...' — may be incomplete after cut"
                )
                result.protected_intervals.append({
                    "start": s["start"],
                    "end": s["end"],
                    "reason": s.get("reason", "Sentence may be incomplete after cut"),
                })

    except Exception as e:
        print(f"  [AIReview] Sentence review error: {e}")

    # ── STEP 2: Silence Gap Review ──
    if silence_gaps:
        print(f"[AIReview] Step 2: Reviewing {len(silence_gaps)} silence gaps...")

        gaps_text = "\n".join(
            f"{i}. {g['duration']:.2f}s gap between "
            f"'...{g['before_text']}' and '{g['after_text']}...'"
            for i, g in enumerate(silence_gaps)
        )

        gap_prompt = f"""You are reviewing silence gaps in a video transcript for removal.

Content summary: {result.summary}
Language: {"Indonesian" if language == "id" else "English"}
Cut strength: {strength}/100

For each gap, decide: REMOVE or KEEP.
- REMOVE: Pure pause, breath, or hesitation. Content flows naturally without it.
- KEEP: Natural pause for emphasis, paragraph break, or dramatic effect.

GAPS:
{gaps_text}

Respond ONLY with JSON array of indices to REMOVE:
[0, 2, 3]"""

        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=gap_prompt,
            )
            text = response.text.strip()
            if "[" in text:
                text = text[text.index("["):text.rindex("]") + 1]
            remove_indices = json.loads(text)

            for idx in remove_indices:
                if 0 <= idx < len(silence_gaps):
                    gap = silence_gaps[idx]
                    # Only add if not in a protected interval
                    protected = any(
                        p["start"] <= gap["start"] and p["end"] >= gap["end"]
                        for p in result.protected_intervals
                    )
                    if not protected:
                        result.safe_cuts.append({
                            "start": gap["start"],
                            "end": gap["end"],
                            "type": "silence",
                            "duration": gap["duration"],
                        })

            print(f"  ✓ {len(result.safe_cuts)} silence gaps approved for removal")

        except Exception as e:
            print(f"  [AIReview] Gap review error: {e}")

    # ── STEP 3: Filler Word Review ──
    if filler_candidates:
        print(f"[AIReview] Step 3: Reviewing {len(filler_candidates)} filler candidates...")

        batch_size = 40
        filler_cuts = []

        for i in range(0, len(filler_candidates), batch_size):
            batch = filler_candidates[i:i + batch_size]
            items = "\n".join(
                f"{j}. word='{c['word']}' ({c['duration']:.2f}s) context=\"{c['context']}\""
                for j, c in enumerate(batch)
            )

            filler_prompt = f"""Review these filler word candidates in a bilingual Indonesian-English video.

Content: {result.summary}
Strength: {strength}/100 — {"be conservative, only remove obvious fillers" if strength <= 50 else "be moderate, remove fillers and unnecessary particles"}

For each candidate, REMOVE only if:
- It's a pure thinking sound (uh, um, hmm)
- OR it's a context particle that adds no meaning here
- AND removing it does NOT break the sentence delivery or meaning

CANDIDATES:
{items}

Respond ONLY with JSON array of 0-based indices to REMOVE. Empty array if none:
[0, 2]"""

            try:
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=filler_prompt,
                )
                text = response.text.strip()
                if "[" in text:
                    text = text[text.index("["):text.rindex("]") + 1]
                remove_indices = json.loads(text)

                for idx in remove_indices:
                    if 0 <= idx < len(batch):
                        cand = batch[idx]
                        protected = any(
                            p["start"] <= cand["start"] and p["end"] >= cand["end"]
                            for p in result.protected_intervals
                        )
                        if not protected:
                            filler_cuts.append({
                                "start": cand["start"],
                                "end": cand["end"],
                                "type": "filler",
                                "word": cand["word"],
                            })

            except Exception as e:
                print(f"  [AIReview] Filler batch error: {e}")

        result.safe_cuts.extend(filler_cuts)
        print(f"  ✓ {len(filler_cuts)} filler words approved for removal")

    # ── SUMMARY ──
    total_cuts = len(result.safe_cuts)
    total_protected = len(result.protected_intervals)
    total_warnings = len(result.warnings)

    print(f"\n[AIReview] ✓ Review complete:")
    print(f"  • Safe cuts approved: {total_cuts}")
    print(f"  • Protected intervals: {total_protected}")
    print(f"  • Warnings: {total_warnings}")
    if result.summary:
        print(f"  • Content: {result.summary}")
    for w in result.warnings:
        print(f"  ⚠ {w}")

    return result


def apply_review(
    segments: list[dict],
    review: ReviewResult,
) -> tuple[list[dict], list[dict]]:
    """
    Apply AI review results to segments.
    Returns (cleaned_segments, removed_intervals).

    Only removes intervals that were explicitly approved as safe_cuts.
    Protects any interval flagged in review.protected_intervals.
    """
    if not review.safe_cuts:
        return segments, []

    # Sort cuts by start time
    cuts = sorted(review.safe_cuts, key=lambda x: x["start"])

    def is_protected(start, end):
        for p in review.protected_intervals:
            if start >= p["start"] - 0.05 and end <= p["end"] + 0.05:
                return True
        return False

    safe = [c for c in cuts if not is_protected(c["start"], c["end"])]

    if not safe:
        return segments, []

    # Filter segments — remove words that fall entirely within a safe cut
    cut_set = [(c["start"], c["end"]) for c in safe]

    def word_in_cut(start, end):
        for cs, ce in cut_set:
            if start >= cs - 0.03 and end <= ce + 0.03:
                return True
        return False

    cleaned = []
    for seg in segments:
        words = seg.get("words", [])
        kept = [w for w in words if not word_in_cut(
            w.get("start", seg["start"]), w.get("end", seg["end"])
        )]
        if not kept and words:
            continue
        new_seg = dict(seg)
        if kept:
            new_seg["words"] = kept
            new_seg["text"] = " ".join(w.get("word", "").strip() for w in kept)
            new_seg["start"] = kept[0].get("start", seg["start"])
            new_seg["end"] = kept[-1].get("end", seg["end"])
        cleaned.append(new_seg)

    print(f"[AIReview] Applied {len(safe)} cuts to segments")
    return cleaned, safe
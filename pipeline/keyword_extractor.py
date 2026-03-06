"""
Keyword/Important Word Extractor
Uses Gemini Flash (free) or heuristic fallback to identify
the most important words in a transcript for caption highlighting.
"""

import json
import os
import re
from dotenv import load_dotenv
load_dotenv()

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


# Common words to never highlight
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "i", "you", "he", "she", "it", "we", "they",
    "this", "that", "these", "those", "my", "your", "his", "her", "its",
    "so", "if", "then", "than", "as", "up", "out", "about", "into", "just",
    "not", "no", "yes", "ok", "okay", "like", "uh", "um", "ah",
}


def extract_keywords_gemini(
    segments: list[dict],
    max_keywords: int = 30,
) -> set:
    """
    Use Gemini Flash to identify important words in the transcript.

    Args:
        segments:     Whisper segments.
        max_keywords: Maximum keywords to highlight.

    Returns:
        Set of important words (lowercase).
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or not GEMINI_AVAILABLE:
        print("[Keywords] Gemini not available, using heuristic fallback...")
        return extract_keywords_heuristic(segments, max_keywords)

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")

    # Build condensed transcript
    full_text = " ".join(seg["text"].strip() for seg in segments)
    if len(full_text) > 3000:
        full_text = full_text[:3000]

    prompt = f"""Analyze this transcript and identify the {max_keywords} most important/impactful words that should be visually highlighted in video captions. Focus on: key nouns, strong verbs, numbers, names, emotions, and emphasis words.

TRANSCRIPT:
{full_text}

Respond ONLY with a JSON array of lowercase words, no explanation:
["word1", "word2", ...]"""

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        # Extract JSON array
        if "[" in text:
            text = text[text.index("["):text.rindex("]") + 1]
        keywords = set(json.loads(text))
        keywords -= STOPWORDS
        print(f"[Keywords] Gemini identified {len(keywords)} important words")
        return keywords
    except Exception as e:
        print(f"[Keywords] Gemini error: {e}. Using heuristic fallback...")
        return extract_keywords_heuristic(segments, max_keywords)


def extract_keywords_heuristic(
    segments: list[dict],
    max_keywords: int = 30,
) -> set:
    """
    Heuristic keyword extraction — no API needed.
    Scores words by: length, capitalization, numbers, frequency.

    Args:
        segments:     Whisper segments.
        max_keywords: Maximum keywords to return.

    Returns:
        Set of important words (lowercase).
    """
    word_freq = {}
    full_text = " ".join(seg["text"].strip() for seg in segments)
    words = re.findall(r"\b[a-zA-Z0-9']+\b", full_text)

    for word in words:
        lower = word.lower()
        if lower in STOPWORDS or len(lower) < 3:
            continue

        score = word_freq.get(lower, 0)
        # Score boosts
        score += 1                              # Base frequency
        if word[0].isupper():
            score += 2                          # Capitalized = likely important
        if re.match(r"\d", word):
            score += 3                          # Numbers are always important
        if len(word) > 7:
            score += 1                          # Longer words tend to be more specific
        word_freq[lower] = score

    # Sort by score, take top N
    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    keywords = {w for w, _ in sorted_words[:max_keywords]}
    print(f"[Keywords] Heuristic identified {len(keywords)} important words")
    return keywords
"""
Step 4: Translate subtitle text using Argos Translate.

Fully offline translation — no API keys, no rate limits.
Supports 30+ languages.
"""

import re
from pathlib import Path

import argostranslate.package
import argostranslate.translate


def get_available_languages() -> list[dict]:
    """
    List all available translation languages.

    Returns:
        List of dicts with "code" and "name" keys.
    """
    languages = argostranslate.translate.get_installed_languages()
    return [{"code": lang.code, "name": lang.name} for lang in languages]


def install_language_pack(from_code: str = "en", to_code: str = "es"):
    """
    Download and install a language pack for translation.

    This only needs to be done once per language pair.

    Args:
        from_code:  Source language code (e.g. "en").
        to_code:    Target language code (e.g. "es", "fr", "de", "ja", "zh").
    """
    print(f"[Step 4] Installing language pack: {from_code} → {to_code}")
    argostranslate.package.update_package_index()
    available = argostranslate.package.get_available_packages()

    pkg = None
    for p in available:
        if p.from_code == from_code and p.to_code == to_code:
            pkg = p
            break

    if pkg is None:
        available_pairs = [
            f"{p.from_code}→{p.to_code}" for p in available
            if p.from_code == from_code
        ]
        raise ValueError(
            f"No package found for {from_code} → {to_code}.\n"
            f"Available from '{from_code}': {', '.join(available_pairs) or 'none'}"
        )

    download_path = pkg.download()
    argostranslate.package.install_from_path(download_path)
    print(f"  ✓ Language pack installed: {from_code} → {to_code}")


def translate_text(text: str, from_code: str = "en", to_code: str = "es") -> str:
    """Translate a single string."""
    return argostranslate.translate.translate(text, from_code, to_code)


def translate_segments(
    segments: list[dict],
    from_code: str = "en",
    to_code: str = "es",
) -> list[dict]:
    """
    Translate the text in each segment while preserving timestamps.

    Args:
        segments:   Whisper segments list.
        from_code:  Source language code.
        to_code:    Target language code.

    Returns:
        New list of segments with translated text (original timestamps kept).
    """
    print(f"[Step 4] Translating {len(segments)} segments: {from_code} → {to_code}")

    translated = []
    for i, seg in enumerate(segments):
        new_seg = dict(seg)  # shallow copy
        original = seg["text"].strip()
        new_seg["text"] = translate_text(original, from_code, to_code)
        translated.append(new_seg)

        if (i + 1) % 50 == 0:
            print(f"  ... translated {i + 1}/{len(segments)}")

    print(f"  ✓ Translation complete ({len(translated)} segments)")
    return translated


def translate_srt(
    srt_path: str,
    output_path: str,
    from_code: str = "en",
    to_code: str = "es",
) -> str:
    """
    Translate an existing SRT file and write a new one.

    Args:
        srt_path:     Path to the source .srt file.
        output_path:  Path for the translated .srt file.
        from_code:    Source language code.
        to_code:      Target language code.

    Returns:
        Path to the translated SRT file.
    """
    content = Path(srt_path).read_text(encoding="utf-8")

    # SRT format: index, timestamp line, text line(s), blank line
    blocks = re.split(r"\n\n+", content.strip())
    translated_blocks = []

    print(f"[Step 4] Translating SRT: {srt_path} ({from_code} → {to_code})")

    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            translated_blocks.append(block)
            continue

        index = lines[0]
        timestamp = lines[1]
        text = " ".join(lines[2:])

        translated_text = translate_text(text, from_code, to_code)
        translated_blocks.append(f"{index}\n{timestamp}\n{translated_text}")

    output = "\n\n".join(translated_blocks) + "\n"
    Path(output_path).write_text(output, encoding="utf-8")

    print(f"  ✓ Translated SRT saved: {output_path}")
    return output_path

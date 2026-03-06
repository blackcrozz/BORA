from .extract_audio import extract_audio
from .transcribe import transcribe_audio
from .srt_generator import generate_srt, generate_ass, generate_word_highlight_ass
from .translate import translate_segments, translate_srt, install_language_pack
from .smart_clip import find_highlights, find_highlights_llm, cut_clips
from .burn_captions import burn_captions

try:
    from .gemini_clip import gemini_clip, find_highlights_gemini
except ImportError:
    gemini_clip = None
    find_highlights_gemini = None

generate_captions = generate_srt
smart_clip = find_highlights

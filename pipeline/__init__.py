from .extract_audio import extract_audio
from .transcribe import transcribe_audio
from .srt_generator import generate_srt, generate_ass, generate_word_highlight_ass
from .translate import translate_segments
from .smart_clip import smart_clip
from .burn_captions import burn_captions

try:
    from .gemini_clip import gemini_clip
except ImportError:
    gemini_clip = None

# Alias so main.py can use either name
generate_captions = generate_srt

__all__ = [
    "extract_audio",
    "transcribe_audio",
    "generate_srt",
    "generate_ass",
    "generate_word_highlight_ass",
    "generate_captions",
    "translate_segments",
    "smart_clip",
    "gemini_clip",
    "burn_captions",
]
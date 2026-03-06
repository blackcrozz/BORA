from .extract_audio import extract_audio
from .transcribe import transcribe_audio
from .captions import generate_captions
from .translate import translate_segments
from .clip import smart_clip
from .burn import burn_captions

try:
    from .gemini_clip import gemini_clip
except ImportError:
    gemini_clip = None

__all__ = [
    "extract_audio",
    "transcribe_audio",
    "generate_captions",
    "translate_segments",
    "smart_clip",
    "gemini_clip",
    "burn_captions",
]
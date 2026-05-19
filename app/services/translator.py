import logging
import threading
import unicodedata
from functools import lru_cache
from typing import Dict, List

# Attempt to import deep_translator for professional translation
try:
    from deep_translator import GoogleTranslator
    HAS_DEEP_TRANSLATOR = True
except ImportError:
    HAS_DEEP_TRANSLATOR = False

logger = logging.getLogger(__name__)

# Fallback Dictionary (Phase 1 logic) ensures quality on common keywords.
MATERIAL_MAP = {
    "da phien": {"en": "Slate", "zh": "板岩"},
    "da thach anh": {"en": "Quartz", "zh": "石英"},
    "be tong": {"en": "Concrete", "zh": "混凝土"},
    "da song": {"en": "Wave Stone", "zh": "波浪石"},
    "da line": {"en": "Line Stone", "zh": "条纹石"},
    "da san": {"en": "Coral Stone", "zh": "珊瑚石"},
    "da ghep": {"en": "Split Face", "zh": "文化石"},
    "da hat": {"en": "Granule Stone", "zh": "碎石"},
    "da bam": {"en": "Bush Hammered", "zh": "荔枝面"},
    "da xuyen sang": {"en": "Translucent Stone", "zh": "透光石"},
    "vai det": {"en": "Woven Fabric", "zh": "编织纹"},
    "da cam thach": {"en": "Marble", "zh": "大理石"},
    "da hoa cuong": {"en": "Granite", "zh": "花岗岩"},
    "go": {"en": "Wood", "zh": "木材"},
    "da mem": {"en": "Flexible Stone", "zh": "软石"},
}


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────
def normalize_text(text: str) -> str:
    """Strip diacritics + lowercase to match against MATERIAL_MAP keys."""
    if not text:
        return ""
    text = str(text)
    nfkd_form = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd_form if not unicodedata.combining(c)).lower().strip()


# Lock to serialize concurrent calls into the same translator instance
# (deep_translator's internal session is not strictly thread-safe).
_TRANSLATOR_LOCK = threading.Lock()


def _call_google(text: str, target_lang: str) -> str:
    """Single Google Translate API call with mapped lang code."""
    google_lang = "zh-CN" if target_lang == "zh" else target_lang
    with _TRANSLATOR_LOCK:
        return GoogleTranslator(source="vi", target=google_lang).translate(text)


# In-memory cache. (text, lang) -> translated text.
# Limits memory usage; identical strings (eg. category, material) translate once.
@lru_cache(maxsize=2048)
def _cached_translate(text: str, target_lang: str) -> str:
    """Cached wrapper around _call_google. Falls back to original on error."""
    if not HAS_DEEP_TRANSLATOR:
        return text.upper() if target_lang == "en" else text
    try:
        translated = _call_google(text, target_lang)
        return translated or text
    except Exception as exc:  # noqa: BLE001
        logger.error("Google translate error (%s): %s", target_lang, exc)
        return text.upper() if target_lang == "en" else text


def smart_translate(text: str, target_lang: str) -> str:
    """
    Combine dictionary-based translation with cached Google fallback.
    """
    if not text:
        return ""
    if target_lang == "vi":
        return text

    # 1) Dictionary match (fast, high quality for keywords).
    normalized = normalize_text(text)
    for key, trans in MATERIAL_MAP.items():
        if key in normalized and len(normalized) < len(key) + 5:
            return trans.get(target_lang, text)

    # 2) Cached professional API.
    return _cached_translate(text, target_lang)


def translate_object_fields(
    obj_data: Dict,
    fields_to_translate: List[str],
    target_langs: List[str] = ("en", "zh"),
) -> Dict:
    """
    Translate specified fields and add `<field>_<lang>` keys when missing.
    """
    result = obj_data.copy()
    for field in fields_to_translate:
        val = obj_data.get(field)
        if not val or not isinstance(val, str):
            continue

        for lang in target_langs:
            key = f"{field}_{lang}"
            if not result.get(key):
                result[key] = smart_translate(val, lang)

    return result

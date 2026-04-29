import logging
from typing import Dict, List, Optional

# Attempt to import deep_translator for professional translation
try:
    from deep_translator import GoogleTranslator
    HAS_DEEP_TRANSLATOR = True
except ImportError:
    HAS_DEEP_TRANSLATOR = False

logger = logging.getLogger(__name__)

# Fallback Dictionary (from Phase 1 logic) to ensure quality for common terms
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

def normalize_text(text: str) -> str:
    import unicodedata
    if not text: return ""
    text = str(text)
    # Remove diacritics
    nfkd_form = unicodedata.normalize('NFKD', text)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)]).lower().strip()

def smart_translate(text: str, target_lang: str) -> str:
    """
    Combines Dictionary-based translation with professional API fallback.
    """
    if not text: return ""
    if target_lang == "vi": return text
    
    # 1. Try Dictionary Match (Fast & High Quality for keywords)
    normalized = normalize_text(text)
    for key, trans in MATERIAL_MAP.items():
        if key in normalized:
            # Replace the keyword in the original text or just return the mapped value
            # For product names like "Đá phiến đen", it might be better to translate the whole thing
            # but for now let's just return the mapped value if it's a simple term
            if len(normalized) < len(key) + 5:
                return trans.get(target_lang, text)

    # 2. Try Professional API (if library installed)
    if HAS_DEEP_TRANSLATOR:
        try:
            # Convert 'zh' to 'zh-CN' for Google
            google_lang = "zh-CN" if target_lang == "zh" else target_lang
            translated = GoogleTranslator(source='vi', target=google_lang).translate(text)
            if translated:
                return translated
        except Exception as e:
            logger.error(f"Translation error: {e}")

    # 3. Fallback: Return original or normalized
    return text.upper() if target_lang == "en" else text

def translate_object_fields(obj_data: Dict, fields_to_translate: List[str], target_langs: List[str] = ["en", "zh"]) -> Dict:
    """
    Translates specified fields in a dictionary and adds localized keys.
    Example: name -> name_en, name_zh
    """
    result = obj_data.copy()
    for field in fields_to_translate:
        val = obj_data.get(field)
        if not val or not isinstance(val, str):
            continue
            
        for lang in target_langs:
            key = f"{field}_{lang}"
            # Only translate if not already set or empty
            if not result.get(key):
                result[key] = smart_translate(val, lang)
                
    return result

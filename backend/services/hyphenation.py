"""Auto-hyphenation service using pyphen.

Splits plain lyrics into syllables automatically.
Users can then review and correct the hyphenation.
"""

import re
import unicodedata
from utils.logger import log_step

try:
    import pyphen
    PYPHEN_AVAILABLE = True
except ImportError:
    PYPHEN_AVAILABLE = False
    log_step("INIT", "pyphen not installed — auto-hyphenation disabled")

# ── Custom override dictionary ──
# pyphen misses many common English words, especially those starting with
# short vowel prefixes (a-, e-, o-). This dictionary fixes known problems.
# Format: lowercase word → hyphenated form
CUSTOM_HYPHENATION = {
    # a- prefix words
    "away": "a-way",
    "again": "a-gain",
    "against": "a-gainst",
    "alone": "a-lone",
    "alive": "a-live",
    "above": "a-bove",
    "about": "a-bout",
    "around": "a-round",
    "among": "a-mong",
    "across": "a-cross",
    "ahead": "a-head",
    "aside": "a-side",
    "asleep": "a-sleep",
    "awake": "a-wake",
    "aware": "a-ware",
    "arise": "a-rise",
    "arose": "a-rose",
    "amaze": "a-maze",
    "amazed": "a-mazed",
    "amazing": "a-maz-ing",
    "apart": "a-part",
    "appear": "ap-pear",
    "afraid": "a-fraid",
    "agree": "a-gree",
    "allow": "al-low",
    "along": "a-long",
    # e- prefix words
    "enough": "e-nough",
    "eleven": "e-lev-en",
    "escape": "es-cape",
    "except": "ex-cept",
    "elect": "e-lect",
    "erase": "e-rase",
    "event": "e-vent",
    "evolve": "e-volve",
    "exact": "ex-act",
    "exist": "ex-ist",
    # o- prefix words
    "over": "o-ver",
    "open": "o-pen",
    "okay": "o-kay",
    "obey": "o-bey",
    # Common multi-syllable words pyphen gets wrong
    "maybe": "may-be",
    "nowhere": "no-where",
    "somewhere": "some-where",
    "stony": "sto-ny",
    "bony": "bo-ny",
    "lonely": "lone-ly",
    "only": "on-ly",
    "holy": "ho-ly",
    "evening": "eve-ning",
    "even": "e-ven",
    "every": "ev-er-y",
    "colour": "col-our",
    "color": "col-or",
    "favour": "fa-vour",
    "favor": "fa-vor",
    "honour": "hon-our",
    "honor": "hon-or",
    "paradise": "par-a-dise",
    "hallelujah": "hal-le-lu-jah",
    "anywhere": "an-y-where",
    "everyone": "ev-er-y-one",
    "everything": "ev-er-y-thing",
    "everywhere": "ev-er-y-where",
    "crazy": "cra-zy",
    "lazy": "la-zy",
    "hazy": "ha-zy",
    "easy": "ea-sy",
    # Words pyphen over-splits
    "really": "real-ly",
    "truly": "tru-ly",
    "area": "ar-ea",
}

# Preferred pyphen dictionaries where a language has several regional ones. Every other language uses
# whatever dictionary pyphen has for its code (see `dictionary_for`).
LANGUAGE_MAP = {
    "en": "en_US",
    "de": "de_DE",
    "fr": "fr_FR",
    "es": "es_ES",
    "it": "it_IT",
    "pt": "pt_PT",
    "nl": "nl_NL",
    "pl": "pl_PL",
    "sv": "sv_SE",
    "fi": "fi_FI",
    "no": "nb_NO",
    "da": "da_DK",
    "hu": "hu_HU",
    "cs": "cs_CZ",
    "ro": "ro_RO",
    "hr": "hr_HR",
    "sk": "sk_SK",
}

# Languages written without spaces between syllables: one syllable per character.
CHARACTER_LANGUAGES = {"zh", "ja", "ko", "yue"}
# Japanese small kana and the long-vowel mark belong to the character before them (きょ, っ, ー).
JAPANESE_ATTACHED = set("ゃゅょぁぃぅぇぉっゎャュョァィゥェォッヮー")


def dictionary_for(language: str):
    """The pyphen dictionary for an app language code ("ru" → "ru"), or None if pyphen has none."""
    if not PYPHEN_AVAILABLE:
        return None
    for code in (LANGUAGE_MAP.get(language), language):
        if code:
            found = pyphen.language_fallback(code)
            if found:
                return found
    return None


def split_characters(word: str) -> str:
    """CJK word → one syllable per character ("我爱你" → "我-爱-你"); other characters stay together."""
    parts = []
    for char in word:
        cjk = "\u3040" <= char <= "\u30ff" or "\u3400" <= char <= "\u9fff" or "\uac00" <= char <= "\ud7af"
        if parts and (char in JAPANESE_ATTACHED or not cjk and not parts[-1][1]):
            parts[-1] = (parts[-1][0] + char, parts[-1][1])
        else:
            parts.append((char, cjk))
    return "-".join(text for text, _ in parts)


VOWELS = set("aeiouyäöüåæøœéèêëáàâãíìîïóòôõúùûıəāēīōū")


def split_vowel_groups(word: str) -> str:
    """Generic syllables for Latin-script words without a dictionary: one vowel group per syllable,
    a single consonant between vowels starts the next syllable, a cluster splits before its last
    consonant ("habari" → "ha-ba-ri", "merhaba" → "mer-ha-ba"). Other scripts are left whole.
    """
    if not word.isascii() and not all(unicodedata.name(c, "").startswith("LATIN") for c in word if c.isalpha()):
        return word
    lower = word.lower()
    nuclei = []  # (start, end) of each vowel group
    i = 0
    while i < len(lower):
        if lower[i] in VOWELS:
            j = i
            while j < len(lower) and lower[j] in VOWELS:
                j += 1
            nuclei.append((i, j))
            i = j
        else:
            i += 1
    if len(nuclei) < 2:
        return word
    cuts = []
    for (_, end), (next_start, _) in zip(nuclei, nuclei[1:]):
        consonants = next_start - end
        cuts.append(next_start - 1 if consonants >= 1 else next_start)
    parts, last = [], 0
    for cut in cuts:
        parts.append(word[last:cut])
        last = cut
    parts.append(word[last:])
    return "-".join(p for p in parts if p)


def _english_nuclei(part: str, word_end: bool) -> list:
    """(start, end) of the vowel groups that are sung in an English word part: no silent final "e" ("time"),
    "-es"/"-ed" only after s/z/x/ch/sh/ce/ge and t/d ("pie-ces", "want-ed"; "times", "maimed" are one),
    "y" only as a vowel (not at the start or before a vowel)."""
    lower = part.lower()
    vowels = set("aeiouäöüéèêë")
    groups, i = [], 0
    while i < len(lower):
        is_vowel = lower[i] in vowels or (lower[i] == "y" and i > 0 and (i + 1 == len(lower) or lower[i + 1] not in vowels))
        if is_vowel:
            j = i + 1
            while j < len(lower) and (lower[j] in vowels or lower[j] == "y" and (j + 1 == len(lower) or lower[j + 1] not in vowels)):
                j += 1                                     # "day", "toy": the "y" belongs to its vowel
            groups.append((i, j))
            i = j
        else:
            i += 1
    if len(groups) > 1:
        last = groups[-1]
        tail = lower[last[0]:]
        before = lower[:last[0]]
        if tail == "e" and not (before.endswith("l") and len(before) > 1 and before[-2] not in vowels):
            groups.pop()                                   # "time", "love-ly", but "ta-ble"
        elif not word_end:
            pass
        elif tail == "es" and not re.search(r"(s|z|x|ch|sh|c|g)$", before):
            groups.pop()                                   # "times", but "pie-ces", "ban-da-ges"
        elif tail == "ed" and not re.search(r"[td]$", before):
            groups.pop()                                   # "maimed", but "want-ed"
    return groups


def english_sung_syllables(hyphenated: str) -> str:
    """Split parts pyphen left with more than one sung vowel (pyphen hyphenates for typesetting): "singing" →
    "sing-ing", "pieces" → "pie-ces", "ban-dages" → "ban-da-ges". A single consonant between vowels starts the
    next syllable, a cluster splits before its last consonant, "-ing" is its own syllable."""
    parts = hyphenated.split("-")
    out = []
    for k, part in enumerate(parts):
        word_end = k == len(parts) - 1
        m = re.match(r"^(.*[^aeiouy])(ing)$", part, re.IGNORECASE) if word_end else None
        if m and len(_english_nuclei(m.group(1), False)) >= 1 and len(m.group(1)) > 1:
            out.append(english_sung_syllables(m.group(1)).replace("-", "\x00") if len(_english_nuclei(m.group(1), False)) > 1 else m.group(1))
            out.append(m.group(2))
            continue
        nuclei = _english_nuclei(part, word_end)
        if len(nuclei) < 2:
            out.append(part)
            continue
        cuts = []
        for (_, end), (start, _) in zip(nuclei, nuclei[1:]):
            consonants = start - end
            cut = start - 1 if consonants >= 1 else start
            if part[start:].lower() == "e" and part[start - 1:start].lower() == "l" and consonants >= 2:
                cut = start - 2                            # "ta-ble", "lit-tle": consonant + "le" together
            cuts.append(cut)
        last = 0
        for cut in cuts:
            out.append(part[last:cut])
            last = cut
        out.append(part[last:])
    return "-".join(p for p in out if p).replace("\x00", "-")


def get_supported_languages():
    """Language codes with automatic hyphenation (a pyphen dictionary or one syllable per character)."""
    if not PYPHEN_AVAILABLE:
        return sorted(CHARACTER_LANGUAGES)
    return sorted({code.split("_")[0] for code in pyphen.LANGUAGES} | set(LANGUAGE_MAP) | CHARACTER_LANGUAGES)


LINE_LANGUAGE_MARGIN = 3.0   # below this log-likelihood margin a line takes its neighbour's language


def _language_scorer():
    """langdetect's character n-gram profiles, to compare a line between two given languages; None if missing."""
    try:
        from langdetect import detector_factory
        detector_factory.init_factory()
        return detector_factory._factory
    except Exception:
        return None


def line_languages(lines: list, language: str, language2: str = None) -> list:
    """Per lyrics line, which of the song's two languages it is in (a duet in English and Italian): the one whose
    letter statistics (langdetect's n-gram profiles) fit the line better, only between these two, so short lines
    work ("Sto pensando a te": Italian; langdetect alone says Portuguese). A line too close to call ("oh oh") takes
    the language of the line before. One language (or no profiles for one of them): every line in `language`."""
    import math
    factory = _language_scorer() if language2 and language2 != language else None
    if factory is None or language not in factory.langlist or language2 not in factory.langlist:
        return [language] * len(lines)
    first, second = factory.langlist.index(language), factory.langlist.index(language2)
    out, previous = [], language
    for line in lines:
        detector = factory.create()
        detector.append(line)
        margin = 0.0
        for gram in detector._extract_ngrams():
            probs = factory.word_lang_prob_map.get(gram)
            if probs:
                margin += math.log(probs[first] + 1e-7) - math.log(probs[second] + 1e-7)
        chosen = previous if abs(margin) < LINE_LANGUAGE_MARGIN else (language if margin > 0 else language2)
        out.append(chosen)
        previous = chosen
    return out


def _rules(language: str) -> dict:
    by_character = language in CHARACTER_LANGUAGES
    locale = None if by_character else dictionary_for(language)
    generic = not by_character and not locale
    if generic:
        # No dictionary: a generic vowel rule is closer than another language's rules.
        log_step("HYPHEN", f"No hyphenation dictionary for '{language}', using the generic vowel rule")
    return {"language": language, "by_character": by_character, "locale": locale, "generic": generic,
            "dic": pyphen.Pyphen(lang=locale) if locale else None}


def hyphenate_lyrics(lyrics: str, language: str = "en", language2: str = None) -> dict:
    """Auto-hyphenate plain lyrics text.

    Args:
        lyrics: Plain text lyrics (one line per phrase).
        language: Language code (e.g., 'en', 'de').

    Returns:
        dict with:
            - hyphenated: Full hyphenated text
            - lines: List of { original, hyphenated, syllable_count }
            - total_syllables: Total syllable count
            - language: Language used
            - method: 'pyphen' or 'fallback'
    """
    # Two languages (language2): each line is hyphenated with the rules of the language it is in.
    raw_lines = lyrics.strip().split("\n")
    per_line = line_languages([l.strip() for l in raw_lines], language, language2)
    rule_sets = {code: _rules(code) for code in dict.fromkeys(per_line or [language])}
    main = rule_sets.get(language) or _rules(language)
    by_character, locale, generic = main["by_character"], main["locale"], main["generic"]

    result_lines = []
    total_syllables = 0

    for line, line_language in zip(raw_lines, per_line):
        line = line.strip()
        rules = rule_sets[line_language]
        line_by_character, line_generic, dic = rules["by_character"], rules["generic"], rules["dic"]
        if not line:
            result_lines.append({
                "original": "",
                "hyphenated": "",
                "syllable_count": 0,
            })
            continue

        # Skip marker lines like [RAP], [/RAP]
        if re.match(r"^\[.*\]$", line):
            result_lines.append({
                "original": line,
                "hyphenated": line,
                "syllable_count": 0,
            })
            continue

        # Hyphenate each word. Words the user already split ("beau-ti-ful", "oh-oh-oh") stay as they are,
        # the rest of the line is still hyphenated.
        hyphenated_words = []
        for word in line.split():
            # Preserve punctuation
            prefix, core, suffix = _split_punctuation(word)
            if "-" in word:
                hyphenated_words.append(word)
            elif core and line_by_character:
                hyphenated_words.append(f"{prefix}{split_characters(core)}{suffix}")
            elif core and line_generic:
                hyphenated_words.append(f"{prefix}{split_vowel_groups(core)}{suffix}")
            elif core:
                # Check custom overrides first (case-insensitive); they are English words
                core_lower = core.lower()
                if line_language == "en" and core_lower in CUSTOM_HYPHENATION:
                    custom = CUSTOM_HYPHENATION[core_lower]
                    # Preserve original casing of first letter
                    if core[0].isupper() and custom[0].islower():
                        custom = custom[0].upper() + custom[1:]
                    hyphenated = custom
                else:
                    hyphenated = dic.inserted(core, hyphen="-")
                    if line_language == "en":
                        hyphenated = english_sung_syllables(hyphenated)
                hyphenated_words.append(f"{prefix}{hyphenated}{suffix}")
            else:
                hyphenated_words.append(word)

        hyphenated_line = " ".join(hyphenated_words)
        syl_count = _count_syllables_in_hyphenated(hyphenated_line)
        total_syllables += syl_count

        result_lines.append({
            "language": line_language,
            "original": line,
            "hyphenated": hyphenated_line,
            "syllable_count": syl_count,
        })

    log_step("HYPHEN", f"Hyphenated {len(result_lines)} lines, {total_syllables} syllables ({language})")

    return {
        "hyphenated": "\n".join(l["hyphenated"] for l in result_lines),
        "lines": result_lines,
        "total_syllables": total_syllables,
        "language": language,
        "method": ("one syllable per character" if by_character
                   else "generic vowel rule (no dictionary for this language)" if generic else f"pyphen ({locale})"),
    }


def _hyphenate_fallback(lyrics: str, language: str) -> dict:
    """Simple fallback: treat each word as one syllable."""
    result_lines = []
    total_syllables = 0

    for line in lyrics.strip().split("\n"):
        line = line.strip()
        if not line or re.match(r"^\[.*\]$", line):
            result_lines.append({
                "original": line,
                "hyphenated": line,
                "syllable_count": 0,
            })
            continue

        syl_count = len(line.split())
        total_syllables += syl_count
        result_lines.append({
            "original": line,
            "hyphenated": line,
            "syllable_count": syl_count,
        })

    return {
        "hyphenated": "\n".join(l["hyphenated"] for l in result_lines),
        "lines": result_lines,
        "total_syllables": total_syllables,
        "language": language,
        "method": "none: no hyphenation rules for this language, split syllables yourself",
    }


def _split_punctuation(word: str):
    """Split leading/trailing punctuation from a word core."""
    match = re.match(r"^([^\w]*)(\w.*\w|\w)([^\w]*)$", word)
    if match:
        return match.group(1), match.group(2), match.group(3)
    return "", word, ""


def _count_syllables_in_hyphenated(line: str) -> int:
    """Count syllables in a hyphenated line. Each hyphen-separated part is one syllable."""
    count = 0
    for word in line.split():
        if re.match(r"^\[.*\]$", word):
            continue
        # Count parts separated by hyphens
        parts = word.split("-")
        count += len(parts)
    return count

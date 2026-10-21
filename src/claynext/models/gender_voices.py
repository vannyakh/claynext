"""
Character gender detection and gender-matched TTS voice assignment for dubbing.

Auto-detects Male / Female / Unknown from speaker labels and dialogue cues,
then maps each character to the best available TTS voice of that gender.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

GENDERS = ("Female", "Male", "Unknown")

_FEMALE_HINTS = (
    "female", "woman", "girl", "lady", "she", "her", "hers", "mrs", "miss", "ms",
    "mother", "mom", "mum", "wife", "daughter", "sister", "aunt", "grandma",
    "sreymom", "hoaimy", "ava", "nanami", "sunhi", "xiaoxiao", "bella", "luna",
    "rosie", "kiki", "sarah", "mary", "elena", "emily", "anna", "emma", "olivia",
    "sophia", "mia", "charlotte", "amelia", "harper", "evelyn", "abigail", "alice",
    "grace", "chloe", "victoria", "claire", "lucy", "lily", "zoe", "stella",
    "她", "小姐", "女士", "妈妈", "姐姐", "妹妹", "娘", "娘娘", "皇后", "太后", "贵妃",
    "皇贵妃", "公主", "郡主", "格格", "夫人", "姑娘", "闺女", "千金", "丫鬟", "侍女",
    "嬷嬷", "姑姑", "姨娘", "姨妈", "大娘", "大婶", "婆婆", "师姐", "师妹", "师娘",
    "媳妇", "内子", "娘子", "母亲", "娘亲", "阿娘", "奶奶", "姥姥", "外婆", "表姐",
    "堂妹", "女侠", "仙女", "仙子", "圣女", "女官", "才人", "美人", "贵人", "答应",
    "常在", "臣妾", "民女", "妾身", "奴婢", "奴家", "小女", "本宫", "为娘", "愚妹",
)
_MALE_HINTS = (
    "male", "man", "boy", "gentleman", "he", "him", "his", "mr", "sir",
    "father", "dad", "husband", "son", "brother", "uncle", "grandpa",
    "piseth", "andrew", "namminh", "jasper", "bruno", "hugo", "leo",
    "john", "peter", "david", "michael", "james", "robert", "william",
    "richard", "joseph", "thomas", "charles", "daniel", "matthew",
    "anthony", "mark", "donald", "steven", "paul", "joshua", "arthur",
    "kenneth", "kevin", "brian", "george", "edward", "ronald", "timothy",
    "jason", "jeffrey", "ryan", "jacob", "gary", "nicholas", "eric", "jonathan",
    "marcus", "alex", "bruce", "jack", "sam", "tony", "steve", "tom",
    "他", "先生", "爸爸", "哥哥", "弟弟", "爷", "通判", "官员", "属官", "大人",
    "下官", "微臣", "末将", "在下", "卑职", "草民", "贫僧", "老衲", "老夫", "老朽",
    "朕", "孤", "本王", "寡人", "为父", "愚兄", "小弟", "知府", "巡抚", "总督",
    "丞相", "宰相", "太守", "县令", "尚书", "侍郎", "知县", "提督", "都督", "将军",
    "统领", "侍卫", "校尉", "捕头", "差役", "师爷", "太医", "国师", "道长", "方丈",
    "和尚", "法师", "王爷", "侯爷", "公公", "中官", "圣上", "陛下", "皇上", "皇阿玛",
    "殿下", "公子", "少爷", "老爷", "少主", "庄主", "掌门", "大侠", "少侠", "仁兄",
    "兄台", "贤弟", "兄长", "大哥", "二哥", "师兄", "师弟", "师父", "相公", "郎君",
    "夫君", "丈夫", "岳父", "丈人", "父亲", "爹爹", "阿爹", "叔叔", "伯伯", "舅舅",
    "表哥", "堂兄", "小生", "秀才", "举人", "状元", "教头",
)

_MALE_CHINESE_CUES = {
    "下官", "微臣", "末将", "在下", "卑职", "草民", "贫僧", "老衲", "老夫", "老朽",
    "朕", "孤", "本王", "寡人", "为父", "愚兄", "通判", "知府", "巡抚", "总督",
    "丞相", "宰相", "太守", "县令", "尚书", "侍郎", "知县", "提督", "都督", "将军",
    "统领", "侍卫", "校尉", "捕头", "差役", "师爷", "太医", "国师", "道长", "方丈",
    "和尚", "法师", "王爷", "侯爷", "公公", "中官", "圣上", "陛下", "皇上", "皇阿玛",
    "殿下", "公子", "少爷", "老爷", "少主", "庄主", "掌门", "大侠", "少侠", "仁兄",
    "兄台", "贤弟", "兄长", "师兄", "师弟", "师父", "相公", "郎君", "夫君", "丈夫",
    "岳父", "丈人", "爹爹", "阿爹", "叔叔", "伯伯", "舅舅", "表哥", "堂兄", "小生",
    "秀才", "举人", "状元", "教头", "大人", "属官", "官员",
}

_FEMALE_CHINESE_CUES = {
    "臣妾", "民女", "妾身", "奴婢", "奴家", "小女", "本宫", "为娘", "愚妹", "娘娘",
    "皇后", "太后", "贵妃", "皇贵妃", "公主", "郡主", "格格", "夫人", "姑娘", "闺女",
    "千金", "丫鬟", "侍女", "嬷嬷", "姑姑", "姨娘", "姨妈", "大娘", "大婶", "婆婆",
    "师姐", "师妹", "师娘", "媳妇", "内子", "娘子", "娘亲", "阿娘", "奶奶", "姥姥",
    "外婆", "表姐", "堂妹", "女侠", "仙女", "仙子", "圣女", "女官", "才人", "美人",
    "贵人", "答应", "常在", "小姐", "女士", "妈妈", "姐姐", "妹妹",
}


def normalize_gender(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw or raw in {"unknown", "?", "n/a", "na", "other"}:
        return "Unknown"
    if raw.startswith("f") or raw in {"woman", "girl", "female"}:
        return "Female"
    if raw.startswith("m") or raw in {"man", "boy", "male"}:
        return "Male"
    return "Unknown"


def voice_entry_gender(voice: dict[str, Any] | str) -> str:
    if isinstance(voice, str):
        blob = voice.lower()
    else:
        explicit = normalize_gender(voice.get("gender"))
        if explicit != "Unknown":
            return explicit
        blob = f"{voice.get('name', '')} {voice.get('id', '')} {voice.get('alias', '')}".lower()
    if "female" in blob or "woman" in blob:
        return "Female"
    if "male" in blob or " man" in blob or blob.endswith(" man"):
        return "Male"
    return "Unknown"


_MALE_SELF_REFS = {
    "下官", "微臣", "末将", "在下", "卑职", "草民", "贫僧", "老衲", "老夫", "老朽",
    "朕", "孤", "本王", "寡人", "为父", "愚兄", "小弟",
}

_FEMALE_SELF_REFS = {
    "臣妾", "民女", "妾身", "奴婢", "奴家", "小女", "本宫", "为娘", "愚妹",
}


def infer_gender_from_text(text: str) -> str:
    """Lightweight pronoun / kinship cues from dialogue (source or dub)."""
    raw = str(text or "").strip()
    if not raw:
        return "Unknown"

    # 1. 1st-person self-references take highest priority (speaker identifies own gender)
    if any(ref in raw for ref in _MALE_SELF_REFS):
        return "Male"
    if any(ref in raw for ref in _FEMALE_SELF_REFS):
        return "Female"

    # Prioritize Chinese historical, official, imperial, and drama cues
    c_male = sum(1 for c in _MALE_CHINESE_CUES if c in raw)
    c_female = sum(1 for c in _FEMALE_CHINESE_CUES if c in raw)
    if c_male > c_female and c_male > 0:
        return "Male"
    if c_female > c_male and c_female > 0:
        return "Female"

    blob = f" {raw.lower()} "
    female = sum(1 for hint in _FEMALE_HINTS if f" {hint} " in blob or hint in blob)
    male = sum(1 for hint in _MALE_HINTS if f" {hint} " in blob or hint in blob)
    # Prefer whole-word-ish English pronouns.
    for token, gender in ((" she ", "Female"), (" her ", "Female"), (" he ", "Male"), (" him ", "Male")):
        if token in blob:
            return gender
    if "她" in raw:
        return "Female"
    if "他" in raw and "她" not in raw:
        return "Male"
    if female > male and female > 0:
        return "Female"
    if male > female and male > 0:
        return "Male"
    return "Unknown"


def infer_gender_from_speaker(speaker: str) -> str:
    name = str(speaker or "").strip()
    if is_generic_speaker(name):
        return "Unknown"
    low = name.lower()
    tokens = set(re.findall(r"\w+", low))
    if any(h in tokens or h in low for h in _FEMALE_HINTS if len(h) >= 3):
        return "Female"
    if any(h in tokens or h in low for h in _MALE_HINTS if len(h) >= 3):
        return "Male"
    # WhisperX / pyannote SPEAKER_00 / SPEAKER_01 — no reliable gender; leave Unknown.
    return "Unknown"


def detect_segment_gender(seg: dict[str, Any], *, honor_manual: bool = True) -> str:
    """Best-effort gender for one line (manual → audio model → text cues)."""
    if honor_manual and seg.get("gender_manual"):
        return normalize_gender(seg.get("gender"))
    existing = normalize_gender(seg.get("gender"))
    if existing != "Unknown" and seg.get("gender_manual"):
        return existing
    # Wav2Vec2 Common-Voice gender classifier (ASR analysis).
    audio_g = normalize_gender(seg.get("audio_gender"))
    if audio_g != "Unknown":
        return audio_g
    if existing != "Unknown" and seg.get("gender_source") in ("audio", "llm"):
        return existing
    speaker_g = infer_gender_from_speaker(str(seg.get("speaker") or ""))
    if speaker_g != "Unknown":
        return speaker_g
    text = " ".join(
        part for part in (
            str(seg.get("original_text") or ""),
            str(seg.get("text") or ""),
            str(seg.get("translated_text") or ""),
        ) if part
    )
    text_g = infer_gender_from_text(text)
    if text_g != "Unknown":
        return text_g
    if existing != "Unknown":
        return existing
    return "Unknown"


_GENERIC_SPEAKER = re.compile(
    r"^(?:character|speaker|unknown|spk|voice)[\s_\-]?\d*$",
    re.IGNORECASE,
)
_INTRO = re.compile(
    r"(?:i am|i'm|i’m|my name is|this is|call me|我是|我叫|名叫)\s*"
    r"([A-Z][\w'’\-]{1,18}|[\u4e00-\u9fff]{2,4})",
    re.IGNORECASE,
)
_CHINESE_OFFICIAL_INTRO = re.compile(
    r"(?:下官|微臣|末将|在下|卑职|草民|贫僧|老衲)"
    r"(?:[\u4e00-\u9fff]{2,6}?(?:通判|知府|巡抚|总督|尚书|侍郎|将军|都督|提督|统领|知县|县令|大人|侍卫|太医|捕头|推官|官员|学士))?"
    r"([\u4e00-\u9fff]{2,3})(?:[，,、\s]|$|率|恭迎|拜见|启奏|参见|领命|告退)"
)
_CHINESE_FEMALE_INTRO = re.compile(
    r"(?:臣妾|民女|妾身|奴婢|奴家|小女|本宫)"
    r"(?:[\u4e00-\u9fff]{2,6}?(?:娘娘|皇后|贵妃|公主|郡主|夫人|小姐|姑娘))?"
    r"([\u4e00-\u9fff]{2,3})(?:[，,、\s]|$|参见|拜见|叩见)"
)
_VOCATIVE = re.compile(r"^([A-Z][\w'’\-]{1,16})[,，]\s")
_VOCATIVE_TAIL = re.compile(r"[,，]\s*([A-Z][\w'’\-]{1,16})[!?\.。！？]*$")
_VOCATIVE_MID = re.compile(
    r"(?:^|[\.!?。！？\s])(?:yes|no|oh|ah|hey|wait|well|listen|look|hello|hi|thanks|thank you|sorry)[,，]\s*([A-Z][\w'’\-]{1,16})\b",
    re.IGNORECASE,
)

_TITLES = (
    r"Detective|Doctor|Dr\.|Captain|Capt\.|Officer|Professor|Prof\.|Sergeant|Sgt\.|"
    r"Lieutenant|Lt\.|Agent|Inspector|Commander|Chief|Mr\.|Mrs\.|Miss|Ms\.|Lord|Lady|"
    r"Father|Brother|Sister|Master|Uncle|Aunt|Grandpa|Grandma|Judge|Mayor|President|King|Queen"
)
_TITLED_NAME = re.compile(rf"\b({_TITLES})\s+([A-Z][\w'’\-]{{1,18}})\b", re.IGNORECASE)
_KINSHIP_NAME = re.compile(
    r"\b(?:my\s+(?:husband|wife|son|daughter|brother|sister|dad|mom|father|mother|partner|boss|uncle|aunt))\s*,?\s*([A-Z][\w'’\-]{1,18})\b",
    re.IGNORECASE,
)
_CHINESE_TITLES = (
    r"(?:总|队长|警官|主任|局长|教授|医生|老师|律师|师傅|大哥|大姐|小姐|大叔|阿姨|爷爷|奶奶|老板|会长|司令|"
    r"通判|大人|知府|巡抚|总督|尚书|侍郎|将军|提督|都督|统领|知县|县令|公公|太医|国师|道长|方丈|王爷|侯爷|"
    r"圣上|陛下|皇上|殿下|公子|少爷|老爷|少主|庄主|掌门|大侠|少侠|兄台|仁兄|兄长|师兄|师弟|师父|相公|"
    r"娘娘|皇后|太后|贵妃|公主|郡主|夫人|姑娘|姑姑|姨娘|师姐|师妹|师娘)"
)
_CHINESE_TITLED_NAME = re.compile(rf"([\u4e00-\u9fff]{{1,2}})({_CHINESE_TITLES})")

_NON_NAMES = {
    "wait", "look", "listen", "stop", "please", "thanks", "thank", "sorry",
    "hello", "hi", "bye", "goodbye", "yeah", "yes", "no", "okay", "ok", "right",
    "well", "oh", "ah", "hey", "man", "dude", "bro", "guys", "everyone", "somebody",
    "nobody", "anyone", "today", "tomorrow", "yesterday", "nothing", "something",
    "maybe", "actually", "suddenly", "here", "there", "where", "when", "what", "why",
    "how", "who", "which", "come", "go", "help", "sure", "fine", "never", "always",
    "again", "now", "then", "just", "see", "watch", "tell", "say", "know", "think",
    "good", "bad", "great", "god", "lord", "damn", "shit", "fuck", "hold", "take",
    "leave", "back", "away", "ready", "remember", "forget", "believe", "careful",
    "请安", "叩安", "问安", "谢恩", "领旨", "告退", "遵旨", "启奏", "万福", "参见",
    "拜见", "领命", "恕罪", "知错", "吉祥", "遵命", "禀告", "回禀", "回话", "属实",
    "明白", "知道", "救命",
}

_EXPR_CUES = (
    ("laugh", ("haha", "ha ha", "hehe", "laugh", "lol", "chuckle", "giggle", "哈哈", "呵呵", "嘿嘿", "笑")),
    ("whisper", ("whisper", "psst", "quietly", "shh", "hush", "小声", "悄悄", "嘘")),
    ("sigh", ("sigh", "phew", "alas", "唉", "叹气")),
    ("gasp", ("gasp", "whoa", "oh my god", "my god", "天哪", "哇", "倒吸")),
    ("sad", ("sob", "cry", "crying", "tears", "please don't", "呜", "哭", "流泪", "求求你")),
    ("shout", ("shut up", "get out", "stop it", "run!", "watch out!", "look out!", "滚", "闭嘴", "快跑", "小心")),
    ("angry", ("damn it", "bastard", "how dare you", "curse", "可恶", "混蛋", "竟敢", "气死")),
    ("excited", ("amazing", "incredible", "fantastic", "we did it", "hurray", "太棒了", "太好了", "成功了")),
    ("calm", ("relax", "calm down", "breathe", "it's okay", "别紧张", "冷静", "放轻松")),
)


def is_generic_speaker(name: str) -> bool:
    clean = str(name or "").strip()
    return not clean or bool(_GENERIC_SPEAKER.match(clean))


def detect_line_expression(text: str) -> str:
    """A short delivery cue from the spoken line. Empty when the line is plain."""
    raw = str(text or "")
    low = f" {raw.lower()} "
    for label, cues in _EXPR_CUES:
        if any(cue in low or cue in raw for cue in cues):
            return label
    if raw.count("!") >= 2 or raw.count("！") >= 2:
        return "shout"
    return ""


def expression_tag(expression: str) -> str:
    token = {
        "laugh": "[laugh]",
        "sigh": "[sigh]",
        "whisper": "[whisper]",
        "sad": "[sad]",
        "shout": "[shout]",
        "angry": "[angry]",
        "gasp": "[gasp]",
        "excited": "[excited]",
        "calm": "[calm]",
    }.get(str(expression or "").strip().lower(), "")
    return token


def _is_valid_character_name(candidate: str) -> bool:
    clean = str(candidate or "").strip(" ,，.。!！？?\"'’`")
    if not clean or len(clean) < 2 or len(clean) > 24:
        return False
    if clean.casefold() in _NON_NAMES:
        return False
    if any(non in clean for non in ("恭迎", "参见", "拜见", "启奏", "叩见", "请安", "叩安", "问安", "谢恩", "领旨", "告退", "遵旨", "万福", "领命", "恕罪", "回禀", "禀报")):
        return False
    if is_generic_speaker(clean):
        return False
    # Avoid numbers or code symbols
    if any(char.isdigit() for char in clean):
        return False
    return True


def apply_character_cast(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Name each speaker from the transcript and mark the line's expression.

    Analyzes multi-turn dialogue context:
    - Self-introductions ("My name is John")
    - Titled address ("Detective Miller", "Captain Jack", "李警官")
    - Sentence-start and sentence-end vocatives ("Hey Sarah,", "Where are you, Peter?")
    - Turn alternation: direct address is linked to the adjacent conversational partner.
    """
    if not segments:
        return segments
    speakers: list[str] = []
    for seg in segments:
        name = str(seg.get("speaker") or "").strip() or "Character 1"
        seg["speaker"] = name
        if name not in speakers:
            speakers.append(name)
        text = str(seg.get("text") or seg.get("original_text") or "")
        if not str(seg.get("expression") or "").strip():
            seg["expression"] = detect_line_expression(text)

    intros: dict[str, Counter[str]] = {sp: Counter() for sp in speakers}
    addressed: dict[str, Counter[str]] = {sp: Counter() for sp in speakers}

    for index, seg in enumerate(segments):
        speaker = str(seg.get("speaker") or "")
        text = str(seg.get("text") or seg.get("original_text") or "").strip()
        if not text:
            continue

        # 1. Self-introduction
        intro = _INTRO.search(text)
        if intro:
            candidate = intro.group(1).strip(" ,，.。")
            if _is_valid_character_name(candidate):
                intros[speaker][candidate] += 5

        # 1b. Chinese official / historical self-introduction ("下官秦州通判莫宗明")
        off_intro = _CHINESE_OFFICIAL_INTRO.search(text)
        if off_intro:
            candidate = off_intro.group(1).strip(" ,，.。")
            if _is_valid_character_name(candidate):
                intros[speaker][candidate] += 8
                seg["gender"] = "Male"
                seg["gender_source"] = "text_intro"

        # 1c. Chinese female self-introduction ("臣妾甄嬛", "民女窦娥")
        fem_intro = _CHINESE_FEMALE_INTRO.search(text)
        if fem_intro:
            candidate = fem_intro.group(1).strip(" ,，.。")
            if _is_valid_character_name(candidate):
                intros[speaker][candidate] += 8
                seg["gender"] = "Female"
                seg["gender_source"] = "text_intro"

        # Adjacent conversation partner
        other = ""
        if index + 1 < len(segments):
            nxt = str(segments[index + 1].get("speaker") or "")
            if nxt and nxt != speaker:
                other = nxt
        if not other and index > 0:
            prev = str(segments[index - 1].get("speaker") or "")
            if prev and prev != speaker:
                other = prev

        if not other:
            continue

        # 2. Titled address ("Detective Miller")
        for match in _TITLED_NAME.finditer(text):
            title, name_part = match.group(1), match.group(2)
            full_titled = f"{title.rstrip('.')} {name_part}"
            if _is_valid_character_name(name_part):
                addressed[other][full_titled] += 4
                addressed[other][name_part] += 2

        # 3. Kinship reference ("my husband, Mark")
        kin_match = _KINSHIP_NAME.search(text)
        if kin_match:
            candidate = kin_match.group(1).strip()
            if _is_valid_character_name(candidate):
                addressed[other][candidate] += 4

        self_spans = []
        if intro:
            self_spans.append(intro.span())
        if off_intro:
            self_spans.append(off_intro.span())
        if fem_intro:
            self_spans.append(fem_intro.span())

        # 4. Chinese titled address ("李队长")
        for cn_match in _CHINESE_TITLED_NAME.finditer(text):
            start_pos = cn_match.start()
            if any(s_s <= start_pos < s_e for s_s, s_e in self_spans):
                continue
            cand_cn = cn_match.group(0)
            if len(cand_cn) >= 2 and _is_valid_character_name(cand_cn):
                addressed[other][cand_cn] += 4

        # 5. Leading vocative ("Elena, look at this")
        call = _VOCATIVE.match(text)
        if call:
            called = call.group(1).strip()
            if _is_valid_character_name(called):
                addressed[other][called] += 3

        # 6. Conversational vocative ("Yes, Sarah.", "Wait, John!")
        for mid_match in _VOCATIVE_MID.finditer(text):
            called_mid = mid_match.group(1).strip()
            if _is_valid_character_name(called_mid):
                addressed[other][called_mid] += 3

        # 7. Trailing vocative ("What do you think, Marcus?")
        tail = _VOCATIVE_TAIL.search(text)
        if tail:
            called_tail = tail.group(1).strip()
            if _is_valid_character_name(called_tail):
                addressed[other][called_tail] += 2

    used = {sp for sp in speakers if not is_generic_speaker(sp)}
    rename: dict[str, str] = {}
    for speaker in speakers:
        if speaker in used:
            continue
        votes = intros[speaker] + addressed[speaker]
        picked = ""
        for candidate, _count in votes.most_common():
            clean = candidate.strip()
            if clean and clean not in used and not is_generic_speaker(clean) and _is_valid_character_name(clean):
                picked = clean
                break
        if picked:
            used.add(picked)
            rename[speaker] = picked

    for seg in segments:
        speaker = str(seg.get("speaker") or "")
        if speaker in rename:
            seg["speaker"] = rename[speaker]
        seg["character"] = seg.get("speaker") or ""
    return segments


def character_gender_map(segments: list[dict[str, Any]]) -> dict[str, str]:
    """Majority gender per character name."""
    votes: dict[str, Counter[str]] = {}
    for seg in segments:
        name = str(seg.get("speaker") or "").strip() or "Character 1"
        g = detect_segment_gender(seg)
        votes.setdefault(name, Counter())[g] += 1
    out: dict[str, str] = {}
    for name, counter in votes.items():
        # Ignore Unknown ties unless that is all we have.
        ranked = [g for g, _ in counter.most_common() if g != "Unknown"]
        out[name] = ranked[0] if ranked else "Unknown"
    return out


def _catalog_voices(lang: str = "") -> list[dict[str, Any]]:
    try:
        from claynext.models.tts_service import TTSEngine

        voices = list(TTSEngine.VOICE_PRESETS)
        if lang:
            matched = [v for v in voices if str(v.get("lang") or "") == lang]
            if matched:
                return matched
        return voices
    except Exception:
        return []


def _lookup_voice_gender(voice_id: str) -> str:
    try:
        from claynext.models.tts_service import TTSEngine

        for voice in TTSEngine.VOICE_PRESETS:
            if voice.get("id") == voice_id:
                return voice_entry_gender(voice)
    except Exception:
        pass
    return voice_entry_gender(voice_id)


def voice_display_name(voice_id: str) -> str:
    """Short cast name from a TTS voice id (e.g. Sreymom, Bella, Andrew)."""
    from claynext.models.tts_service import TTSEngine

    return TTSEngine.voice_label(voice_id)


def voices_for_lang(lang: str = "") -> list[dict[str, Any]]:
    """TTS presets for a language, each with ``id``, ``label``, ``gender``."""
    from claynext.models.tts_service import TTSEngine

    out: list[dict[str, Any]] = []
    for voice in TTSEngine.list_voices(lang or None):
        out.append({
            "id": voice["id"],
            "label": voice["name"],
            "gender": voice.get("gender") or voice_entry_gender(voice),
            "name": voice["name"],
            "tag": voice.get("tag") or "",
            "lang": voice.get("lang") or "",
        })
    return out


def _unique_cast_name(base: str, used: set[str]) -> str:
    name = (base or "Voice").strip() or "Voice"
    if name not in used:
        used.add(name)
        return name
    n = 2
    while f"{name} {n}" in used:
        n += 1
    label = f"{name} {n}"
    used.add(label)
    return label


def pick_voice_for_gender(
    gender: str,
    *,
    primary: str = "",
    secondary: str = "",
    lang: str = "",
    used: set[str] | None = None,
) -> str:
    """
    Choose a TTS voice id matching ``gender``.

    Prefers primary/secondary when their gender matches, then other catalog
    voices for the target language. Rotates away from ``used`` when possible.
    """
    target = normalize_gender(gender)
    used = used or set()
    catalog = _catalog_voices(lang)

    preferred: list[str] = []
    for vid in (primary, secondary):
        if vid and _lookup_voice_gender(vid) == target:
            preferred.append(vid)
    for voice in catalog:
        vid = str(voice.get("id") or "")
        if not vid or vid in preferred:
            continue
        if voice_entry_gender(voice) == target:
            preferred.append(vid)

    if target == "Unknown":
        for vid in (primary, secondary):
            if vid and vid not in preferred:
                preferred.append(vid)
        for voice in catalog:
            vid = str(voice.get("id") or "")
            if vid and vid not in preferred:
                preferred.append(vid)

    if not preferred:
        return primary or secondary or ""

    for vid in preferred:
        if vid not in used:
            return vid
    return preferred[0]


def assign_gender_and_voices(
    segments: list[dict[str, Any]],
    *,
    primary_voice: str,
    secondary_voice: str = "",
    lang: str = "",
    force_redetect: bool = False,
) -> list[dict[str, Any]]:
    """
    Fill ``gender``, ``tts_voice_hint``, and ``voice_id`` per line.

    Distinct characters share a stable voice; different characters of the same
    gender rotate through available voices when the catalog allows.
    """
    if not segments:
        return []

    # Detect / refresh gender on lines (keep manual overrides).
    for seg in segments:
        if seg.get("gender_manual"):
            seg["gender"] = normalize_gender(seg.get("gender"))
            continue
        if force_redetect and seg.get("gender_source") not in {"llm", "audio", "text_intro"}:
            seg.pop("gender", None)
        seg["gender"] = detect_segment_gender(seg, honor_manual=False)

    char_gender = character_gender_map(segments)
    # If still Unknown, analyze entire character dialogue and fallback to primary voice gender.
    primary_g = voice_entry_gender(primary_voice)
    lead_fallback = primary_g if primary_g != "Unknown" else "Male"
    alt_fallback = "Female" if lead_fallback == "Male" else "Male"

    order: list[str] = []
    for seg in segments:
        name = str(seg.get("speaker") or "").strip() or "Character 1"
        if name not in order:
            order.append(name)
    for idx, name in enumerate(order):
        if char_gender.get(name, "Unknown") == "Unknown":
            char_lines = " ".join(
                str(s.get("original_text") or s.get("text") or "")
                for s in segments
                if (str(s.get("speaker") or "").strip() or "Character 1") == name
            )
            g = infer_gender_from_text(char_lines)
            if g != "Unknown":
                char_gender[name] = g
            else:
                char_gender[name] = lead_fallback if idx == 0 else alt_fallback

    # Assign one voice per character, rotating within gender.
    used_voices: set[str] = set()
    char_voice: dict[str, str] = {}
    for name in order:
        g = char_gender[name]
        voice = pick_voice_for_gender(
            g,
            primary=primary_voice,
            secondary=secondary_voice or primary_voice,
            lang=lang,
            used=used_voices,
        )
        if not voice:
            voice = primary_voice if g != "Male" else (secondary_voice or primary_voice)
        char_voice[name] = voice
        if voice:
            used_voices.add(voice)

    # Rename cast to TTS voice names (Sreymom, Piseth, …) instead of Character N.
    used_labels: set[str] = set()
    rename: dict[str, str] = {}
    for name in order:
        voice = char_voice.get(name) or primary_voice
        # Keep a custom name if the user already set a non-generic speaker.
        generic = (
            not name
            or name.startswith("Character ")
            or name.startswith("SPEAKER_")
            or name in {"UNKNOWN_SPEAKER", "Unknown", "Speaker 1", "Speaker 2"}
        )
        if generic:
            rename[name] = _unique_cast_name(voice_display_name(voice), used_labels)
        else:
            rename[name] = _unique_cast_name(name, used_labels)

    for seg in segments:
        old = str(seg.get("speaker") or "").strip() or "Character 1"
        name = rename.get(old, old)
        g = char_gender.get(old, "Unknown")
        if not seg.get("gender_manual"):
            seg["gender"] = g
        voice = char_voice.get(old) or primary_voice
        seg["speaker"] = name
        # Keep a movie clone already built for this line — character detection owns TTS.
        existing = str(seg.get("voice_id") or seg.get("tts_voice_hint") or "")
        if existing.startswith("clone:") and (seg.get("reference_wav") or seg.get("clone_voice")):
            seg["tts_voice_hint"] = existing
            seg["voice_id"] = existing
            continue
        seg["tts_voice_hint"] = voice
        seg["voice_id"] = voice

    return segments


def apply_manual_gender(
    segments: list[dict[str, Any]],
    rows: list[int],
    gender: str,
    *,
    primary_voice: str,
    secondary_voice: str = "",
    lang: str = "",
    apply_to_character: bool = True,
) -> None:
    """Set gender manually on rows (and optionally whole character), then refresh voices."""
    target = normalize_gender(gender)
    names: set[str] = set()
    for row in rows:
        if not (0 <= row < len(segments)):
            continue
        seg = segments[row]
        seg["gender"] = target
        seg["gender_manual"] = True
        names.add(str(seg.get("speaker") or "").strip() or "Character 1")

    if apply_to_character and names:
        for seg in segments:
            name = str(seg.get("speaker") or "").strip() or "Character 1"
            if name in names:
                seg["gender"] = target
                seg["gender_manual"] = True

    assign_gender_and_voices(
        segments,
        primary_voice=primary_voice,
        secondary_voice=secondary_voice,
        lang=lang,
        force_redetect=False,
    )


def _apply_llm_cast_result(segments: list[dict[str, Any]], res: dict[str, Any]) -> bool:
    if not isinstance(res, dict):
        return False
    chars = res.get("characters")
    if not isinstance(chars, list):
        chars = []

    applied_any = False
    for char in chars:
        if not isinstance(char, dict):
            continue
        c_name = str(char.get("name") or "").strip()
        c_gender = normalize_gender(char.get("gender"))
        c_role = str(char.get("role") or "")
        indices = char.get("line_indices") or []
        for idx in indices:
            if isinstance(idx, int) and 0 <= idx < len(segments):
                seg = segments[idx]
                if c_name and not seg.get("speaker_manual"):
                    seg["speaker"] = c_name
                    seg["character"] = c_name
                if c_gender != "Unknown" and not seg.get("gender_manual"):
                    seg["gender"] = c_gender
                    seg["gender_source"] = "llm"
                if c_role:
                    seg["character_role"] = c_role
                applied_any = True
    if _apply_llm_line_reads(segments, res.get("lines")):
        applied_any = True
    return applied_any


_LINE_EXPRESSIONS = {
    "laugh", "sigh", "whisper", "sad", "shout", "angry", "gasp", "excited", "calm",
}
_LINE_INTENTS = {
    "question", "answer", "command", "plea", "aside", "narration", "statement",
}


def _apply_llm_line_reads(segments: list[dict[str, Any]], lines: Any) -> bool:
    """Intent, gender, and expression for each spoken turn."""
    if not isinstance(lines, list):
        return False
    applied = False
    for row in lines:
        if not isinstance(row, dict):
            continue
        try:
            index = int(row.get("index"))
        except (TypeError, ValueError):
            continue
        if not 0 <= index < len(segments):
            continue
        seg = segments[index]
        gender = normalize_gender(row.get("gender"))
        if gender != "Unknown" and not seg.get("gender_manual"):
            seg["gender"] = gender
            seg["gender_source"] = "llm"
        expr = str(row.get("expression") or "").strip().lower()
        if expr in _LINE_EXPRESSIONS and not seg.get("expression_manual"):
            seg["expression"] = expr
        intent = str(row.get("intent") or "").strip().lower()
        if intent in _LINE_INTENTS:
            seg["intent"] = intent
        name = str(row.get("character") or "").strip()
        if name and not seg.get("speaker_manual") and _is_valid_character_name(name):
            seg["speaker"] = name
            seg["character"] = name
        if gender != "Unknown" or expr in _LINE_EXPRESSIONS or intent in _LINE_INTENTS:
            applied = True
    return applied


def llm_analyze_cast_and_gender(
    segments: list[dict[str, Any]],
    *,
    progress_callback: Any = None,
) -> bool:
    """Use Gemini Flash AI or Ollama to classify characters, true genders, and dialogue lines."""
    if not segments:
        return False
    import json
    import os
    import urllib.request
    import urllib.error
    import urllib.parse
    from claynext.models.llm_keys import get_key_pool, InvalidKeyError, RateLimitError

    # Prepare compact transcript for LLM
    lines_summary = []
    for i, s in enumerate(segments[:120]):
        spk = str(s.get("speaker") or f"Speaker_{i+1}")
        txt = str(s.get("text") or s.get("original_text") or s.get("translated_text") or "").strip()
        if txt:
            lines_summary.append({"index": i, "speaker": spk, "text": txt})

    if not lines_summary:
        return False

    prompt = (
        "You are a film dialogue analyst. The transcript is already finished. "
        "Read the turns in order and decide who is speaking, whether that person is male or female, "
        "what they intend, and how the line should be delivered. Voices are chosen later from the "
        "studio voice collection using the gender you assign, so the gender must match the speaker of that turn.\n\n"
        "For every line index, set:\n"
        "- character: the speaker's name when the dialogue reveals it, otherwise a stable label such as Man or Woman\n"
        "- gender: Male or Female for the person who speaks that turn\n"
        "- intent: one of question, answer, command, plea, aside, narration, statement\n"
        "- expression: one of laugh, sigh, whisper, sad, shout, angry, gasp, excited, calm, or empty when the line is plain speech\n\n"
        "Also group the same people into characters.\n"
        "Chinese costume and modern drama cues:\n"
        "Male: 下官, 通判, 大人, 微臣, 末将, 在下, 朕, 本王, 陛下, 皇上, 公子, 少爷, 丈夫.\n"
        "Female: 臣妾, 娘娘, 皇后, 公主, 民女, 小姐, 姑娘, 夫人, 奴婢, 妾身, 丫鬟, 娘子.\n"
        "A self-introduction such as '下官秦州通判莫宗明' is name 莫宗明, gender Male.\n"
        "Never mark an official, general, emperor, or clearly male speaker as Female.\n\n"
        "Input lines:\n"
        + json.dumps(lines_summary, ensure_ascii=False, indent=2)
        + "\n\nReturn ONLY JSON:\n"
        "{\n"
        '  "characters": [\n'
        '    {"name": "莫宗明", "gender": "Male", "role": "Lead", "line_indices": [0, 2]}\n'
        "  ],\n"
        '  "lines": [\n'
        '    {"index": 0, "character": "莫宗明", "gender": "Male", "intent": "statement", "expression": ""}\n'
        "  ]\n"
        "}\n"
    )

    # 1. Try Gemini rotation if keys available
    pool = get_key_pool()
    gemini_keys = pool.secrets("gemini")
    if gemini_keys:
        if progress_callback:
            try:
                progress_callback(20, "Calling Gemini Flash AI for character cast & gender…")
            except Exception:
                pass

        def _do_gemini(api_key: str) -> dict:
            models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
            last_err = None
            for model in models:
                url = (
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
                    f"?key={urllib.parse.quote(api_key)}"
                )
                body = json.dumps({
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
                }).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req, timeout=45) as resp:
                        raw = json.loads(resp.read().decode("utf-8"))
                        from claynext.models.llm_keys import note_llm_usage
                        note_llm_usage(model, raw)
                        text_res = (
                            raw.get("candidates", [{}])[0]
                            .get("content", {})
                            .get("parts", [{}])[0]
                            .get("text", "")
                        )
                        return json.loads(text_res)
                except urllib.error.HTTPError as exc:
                    detail = exc.read().decode("utf-8", errors="replace")
                    if exc.code in (401, 403):
                        raise InvalidKeyError(f"{model}: {exc.code}") from exc
                    from claynext.models.llm_keys import is_rate_limit, parse_retry_after
                    if is_rate_limit(exc.code, detail):
                        raise RateLimitError(f"{model}: rate limited", parse_retry_after(exc.headers, detail)) from exc
                    last_err = exc
                except Exception as exc:
                    last_err = exc
            if last_err:
                raise last_err
            return {}

        try:
            res = pool.call_with_rotation("gemini", _do_gemini, progress=progress_callback)
            if _apply_llm_cast_result(segments, res):
                return True
        except Exception:
            pass

    # Stored cloud keys other than Gemini (Qwen, DeepSeek, Groq, …).
    try:
        from claynext.models.llm_chat import chat_text, json_from_text
        from claynext.models.llm_providers import CHAT_ORDER

        for pid in CHAT_ORDER:
            if pool.ready_count(pid) <= 0:
                continue
            if progress_callback:
                try:
                    progress_callback(22, f"Calling {pid} for character cast…")
                except Exception:
                    pass
            try:
                res = json_from_text(chat_text(pid, prompt, progress=progress_callback, temperature=0.2))
            except Exception:
                continue
            if isinstance(res, dict) and _apply_llm_cast_result(segments, res):
                return True
    except Exception:
        pass

    # 2. Try Ollama local LLM if running
    try:
        from claynext.models.translate_service import TranslateEngine
        if TranslateEngine.ollama_available():
            if progress_callback:
                try:
                    progress_callback(25, "Calling local Ollama LLM for character cast…")
                except Exception:
                    pass
            host = TranslateEngine.ollama_host()
            model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
            req = urllib.request.Request(
                f"{host}/api/generate",
                data=json.dumps({"model": model, "prompt": prompt, "format": "json", "stream": False}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                res = json.loads(data.get("response", "{}"))
                if _apply_llm_cast_result(segments, res):
                    return True
    except Exception:
        pass

    return False


def ai_analyze_movie_cast(
    segments: list[dict[str, Any]],
    *,
    lang: str = "",
    primary_voice: str = "",
    secondary_voice: str = "",
    target_lang: str = "",
    progress_callback: Any = None,
) -> dict[str, Any]:
    """
    AI Character Cast & Neural Voice Profiler.

    1. Analyzes dialogue turns, self-introductions, vocatives, titles and honorifics.
    2. Identifies character roles (Lead, Supporting, Minor, Narrator) based on dialogue share.
    3. Detects emotion delivery tags ([laugh], [sigh], [whisper], etc.) per line and character.
    4. Auto-detects gender and casts complementary, non-overlapping neural voices.
    5. Returns enriched segments and structured character profiles for the studio shelf.
    """
    if not segments:
        return {"segments": [], "characters": [], "count": 0}

    def _ping(pct: int, msg: str):
        if progress_callback:
            try:
                progress_callback(pct, msg)
            except Exception:
                pass

    _ping(15, "Analyzing dialogue context, names, and titles…")
    # Step 0: Try high-precision LLM cast detection first (Gemini Flash / Ollama)
    llm_analyze_cast_and_gender(segments, progress_callback=_ping)
    # Step 1: Detect and assign character names + line expressions
    apply_character_cast(segments)

    _ping(45, "Classifying character roles and delivery traits…")
    total_lines = len(segments)
    speaker_lines: Counter[str] = Counter()
    speaker_durations: dict[str, float] = {}
    speaker_exprs: dict[str, Counter[str]] = {}

    for seg in segments:
        name = str(seg.get("speaker") or "").strip() or "Character 1"
        speaker_lines[name] += 1
        dur = float(seg.get("duration_sec") or 0.0)
        if dur <= 0.0:
            from claynext.models.dubbing_service import timestamp_to_sec
            start = timestamp_to_sec(seg.get("start", ""))
            end = timestamp_to_sec(seg.get("end", ""))
            dur = max(0.2, end - start) if end > start else 2.0
        speaker_durations[name] = speaker_durations.get(name, 0.0) + dur

        expr = str(seg.get("expression") or "")
        if expr:
            speaker_exprs.setdefault(name, Counter())[expr] += 1

    # Classify roles
    char_roles: dict[str, str] = {}
    ranked_speakers = [name for name, _ in speaker_lines.most_common()]
    for idx, name in enumerate(ranked_speakers):
        count = speaker_lines[name]
        ratio = count / max(1, total_lines)
        if idx == 0 and ratio >= 0.20:
            char_roles[name] = "Lead"
        elif idx == 1 and ratio >= 0.15:
            char_roles[name] = "Co-Star"
        elif ratio >= 0.05 or count >= 4:
            char_roles[name] = "Supporting"
        else:
            char_roles[name] = "Minor"

    # Step 2: Gender and Voice Assignment
    _ping(70, "Casting distinct neural voices per character…")
    eff_lang = lang or target_lang or ""
    assign_gender_and_voices(
        segments,
        primary_voice=primary_voice,
        secondary_voice=secondary_voice or primary_voice,
        lang=eff_lang,
        force_redetect=True,
    )

    # Attach roles back onto lines
    for seg in segments:
        name = str(seg.get("speaker") or "").strip()
        if name in char_roles:
            seg["character_role"] = char_roles[name]

    # Assemble structured character profiles
    _ping(90, "Building cast profiles…")
    characters: list[dict[str, Any]] = []
    seen: set[str] = set()

    for name in ranked_speakers:
        if name in seen:
            continue
        seen.add(name)

        # Retrieve voice and gender from assigned segments
        voice_id = ""
        gender = "Unknown"
        for seg in segments:
            if str(seg.get("speaker") or "") == name:
                voice_id = str(seg.get("tts_voice_hint") or seg.get("voice_id") or "")
                gender = str(seg.get("gender") or "Unknown")
                break

        expr_counter = speaker_exprs.get(name, Counter())
        top_exprs = [e for e, _ in expr_counter.most_common(2)]
        expr_label = ", ".join(top_exprs)

        characters.append({
            "name": name,
            "gender": gender,
            "role": char_roles.get(name, "Supporting"),
            "voice_id": voice_id,
            "lines": speaker_lines[name],
            "expression": expr_label,
            "duration_sec": round(speaker_durations.get(name, 0.0), 2),
            "in_script": True,
        })

    _ping(100, f"AI Cast complete: {len(characters)} characters profiled.")
    return {
        "segments": segments,
        "characters": characters,
        "count": len(characters),
    }



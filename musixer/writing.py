"""Songwriting / style / script helpers. Uses the configured LLM, with offline fallbacks."""
import random
import re

from .engines import llm

STYLE_BANK = [
    "Funk pop, groovy bassline, syncopated rhythm, danceable beat, retro funk elements, modern production, 120 BPM, rhythmic vocals",
    "Dreamy synthwave, lush analog pads, gated reverb drums, nostalgic 80s melody, airy female vocals, 98 BPM",
    "Acoustic folk, fingerpicked guitar, warm intimate male vocals, soft harmonica, storytelling, 84 BPM",
    "Lo-fi hip hop, dusty vinyl crackle, mellow Rhodes chords, laid-back boom bap drums, chill study vibe, 82 BPM",
    "Epic cinematic orchestral, soaring strings, thunderous taiko drums, heroic brass, choir, 100 BPM",
    "Indie rock, jangly guitars, driving drums, anthemic chorus, raw energetic vocals, 132 BPM",
    "Deep house, warm sub bass, four-on-the-floor kick, hypnotic chords, soulful vocal chops, 122 BPM",
    "R&B slow jam, silky falsetto, lush keys, 808 bass, intimate late-night mood, 70 BPM",
    "K-pop dance, punchy synths, bright hooks, rap verse, explosive chorus, polished production, 126 BPM",
    "Country pop, twangy telecaster, heartfelt female vocals, steady backbeat, singalong chorus, 104 BPM",
    "Jazz lounge, brushed drums, upright bass, smoky saxophone, smooth crooner vocals, 92 BPM",
    "Reggaeton, dembow rhythm, latin percussion, catchy Spanish vocals, tropical synths, 95 BPM",
    "Pop punk, distorted power chords, fast drums, youthful angsty vocals, gang vocals, 168 BPM",
    "Ambient electronica, evolving textures, glassy arpeggios, gentle pulse, spacious reverb, 90 BPM",
    "Afrobeats, log drum, bouncy percussion, warm guitar riffs, smooth melodic vocals, 108 BPM",
    "Gospel soul, Hammond organ, powerful choir, uplifting lead vocals, handclaps, 76 BPM",
    "Melodic dubstep, emotional piano intro, huge supersaw drop, female vocals, 140 BPM",
    "Bossa nova, nylon guitar, soft shaker, gentle Portuguese vocals, breezy summer feel, 88 BPM",
    "Heavy metal, chugging riffs, double kick drums, guitar solo, powerful male vocals, 150 BPM",
    "Celtic folk, tin whistle, fiddle, bodhran, lilting melody, warm vocals, 112 BPM",
]

SYSTEM_SONG = (
    "You are an award-winning songwriter and music producer. You write original, singable lyrics with "
    "strong hooks, natural rhyme and clear song structure using section tags like [Verse 1], [Pre-Chorus], "
    "[Chorus], [Bridge], [Outro]. Style descriptions are comma-separated tags: genre, sub-genre, instruments, "
    "mood, vocal type, production, tempo in BPM."
)


def _offline_title(text):
    words = keywords(text)
    return " ".join(w.capitalize() for w in words[:3]) or "Untitled Song"


_LINES = {
    "verse": [
        "I keep {a} like a secret in my chest", "Walking through the {b} where the shadows rest",
        "Every little thing reminds me of {a}", "The city hums a song about {b}",
        "I wrote your name on a window pane", "Counting every heartbeat in the rain",
        "Morning comes and paints the sky in gold", "Holding on to stories never told",
    ],
    "pre": ["And I can feel it rising slow", "Don't let go, don't let go", "Something's changing, now I know"],
    "chorus": [
        "Oh, {a}, you light me up tonight", "We're running wild, we're running right",
        "{A}, {A}, never let it fade", "This is the moment that we made",
    ],
    "bridge": ["When the music stops and the lights go low", "I'll still be here, I want you to know"],
}


STOP = set("about after again along also always away back been being came come could down every from going have into just like letting more most much never only other over really should some such than that their them then there these they thing this those through under very want what when where which while with would your yours".split())


def keywords(text):
    return [w.lower() for w in re.findall(r"[A-Za-z']+", text or "") if len(w) > 3 and w.lower() not in STOP and not w.lower().endswith("ing")]


def offline_lyrics(idea, structure=None):
    words = keywords(idea) or ["midnight", "tomorrow"]
    a = words[0]
    b = words[1] if len(words) > 1 else "midnight"
    fmt = lambda s: s.format(a=a, b=b, A=a.capitalize())  # noqa: E731
    rnd = random.Random(idea)

    def pick(kind, n):
        pool = _LINES[kind][:]
        rnd.shuffle(pool)
        return [fmt(x) for x in (pool * 2)[:n]]

    chorus = pick("chorus", 4)
    parts = [
        "[Verse 1]", *pick("verse", 4), "", "[Pre-Chorus]", *pick("pre", 2), "", "[Chorus]", *chorus, "",
        "[Verse 2]", *pick("verse", 4), "", "[Chorus]", *chorus, "", "[Bridge]", *pick("bridge", 2), "",
        "[Final Chorus]", *chorus, "", "[Outro]", chorus[0],
    ]
    return "\n".join(parts)


def write_song(description, instrumental=False, language="English", style_hint=""):
    inst = 'Instrumental: no lyrics, return lyrics as "[Instrumental]".' if instrumental else ""
    hint = f"Style hint: {style_hint}" if style_hint else ""
    try:
        d = llm.chat_json(
            SYSTEM_SONG,
            f"Write an original song from this idea: {description}\n"
            f"Language: {language}. {inst}\n{hint}\n"
            'Return {"title": str, "style": str (max 200 chars), "lyrics": str}.',
        )
        return {"title": d.get("title", ""), "style": d.get("style", style_hint), "lyrics": d.get("lyrics", ""), "source": "llm"}
    except llm.LLMUnavailable:
        return None


def enhance_style(style):
    try:
        out = llm.chat(
            SYSTEM_SONG,
            f"Expand this music style into one rich, comma-separated style description (max 300 chars). "
            f"Keep the user's intent. Return only the description.\nStyle: {style}",
            temperature=0.8, max_tokens=200,
        )
        return out.strip().strip('"')[:1000]
    except llm.LLMUnavailable:
        base = style.strip().rstrip(",")
        extras = ["polished modern production", "wide stereo mix", "memorable hook", "dynamic arrangement"]
        if "bpm" not in base.lower():
            extras.append("110 BPM")
        return ", ".join([base] + [e for e in extras if e.split()[0] not in base.lower()]) if base else random.choice(STYLE_BANK)


def random_style():
    return random.choice(STYLE_BANK)


def guided_style(genre="", subgenre="", era="", instruments="", mood="", tempo="", complexity=50, custom=""):
    parts = {k: v for k, v in dict(genre=genre, subgenre=subgenre, era=era, instruments=instruments, mood=mood, tempo=tempo).items() if v}
    try:
        return llm.chat(
            SYSTEM_SONG,
            "Write a detailed, conversational music style description (2-3 sentences, max 400 chars) for an AI "
            f"music model. Complexity {complexity}/100 (higher = richer arrangement detail). "
            f"Parameters: {parts}. Extra notes: {custom}. Return only the description.",
            temperature=0.9, max_tokens=250,
        ).strip().strip('"')
    except llm.LLMUnavailable:
        bpm = {"slow": "72 BPM", "medium": "105 BPM", "fast": "130 BPM"}.get((tempo or "").split(" ")[0].lower(), "")
        detail = "intricate layered arrangement, evolving dynamics" if complexity > 66 else (
            "balanced arrangement" if complexity > 33 else "minimal, sparse arrangement")
        bits = [f"{subgenre} {genre}".strip(), f"{era} influences" if era else "", instruments, f"{mood} mood" if mood else "", detail, bpm, custom]
        return ", ".join(b for b in bits if b)


def generate_lyrics(idea, genre="", mood="", structure="", language="English", rhyme=""):
    try:
        return llm.chat(
            SYSTEM_SONG,
            f"Write complete, original song lyrics about: {idea}\nGenre: {genre}\nMood: {mood}\n"
            f"Structure: {structure or 'Verse, Pre-Chorus, Chorus, Verse, Chorus, Bridge, Chorus, Outro'}\n"
            f"Rhyme scheme: {rhyme or 'natural'}\nLanguage: {language}\n"
            "Use section tags in square brackets. Return only the lyrics.",
            temperature=0.95,
        ).strip()
    except llm.LLMUnavailable:
        return offline_lyrics(idea)


STUDIO_ACTIONS = {
    "opening_lines": "Suggest 5 different opening lines for a song about the idea.",
    "full_draft": "Write 5 short alternative directions; each item is a complete first draft (verse + chorus) with section tags.",
    "next_line": "Suggest 5 alternative next lines that continue right after the cursor, matching meter and rhyme.",
    "rewrite": "Rewrite the selected lyrics in 5 different, stronger ways, keeping the original intent and syllable count close.",
    "continue_section": "Continue the current section with 5 alternative 2-line continuations.",
    "add_verse": "Write 5 alternative new verses (4 lines each, start with [Verse]) that move the story forward.",
    "add_chorus": "Write 5 alternative choruses (4 lines each, start with [Chorus]) with a strong, repeatable hook.",
    "add_bridge": "Write 5 alternative bridges (2-4 lines each, start with [Bridge]) that add contrast.",
    "strengthen_hook": "Give 5 stronger, catchier versions of the hook / selected lines.",
    "refine_rhyme": "Give 5 versions of the selected lines with better rhyme and cadence.",
    "deepen_emotion": "Give 5 versions of the selected lines with deeper, more specific emotion and imagery.",
    "simplify": "Give 5 simpler, more conversational versions of the selected lines without losing meaning.",
    "title": "Suggest 5 song titles for these lyrics.",
}


def studio(action, lyrics="", selection="", before="", after="", idea=""):
    instruction = STUDIO_ACTIONS.get(action, STUDIO_ACTIONS["next_line"])
    prompt = (
        f"Song idea: {idea or '(not given)'}\n\nFull lyrics so far:\n{lyrics or '(empty)'}\n\n"
        f"Text right before the cursor:\n{before[-600:]}\n\nSelected text:\n{selection or '(none)'}\n\n"
        f"Text after the cursor:\n{after[:300]}\n\nTask: {instruction}\n"
        'Return {"suggestions": [5 strings]}. Each suggestion is ready to insert (use \\n for line breaks).'
    )
    try:
        d = llm.chat_json(SYSTEM_SONG, prompt, temperature=1.0)
        items = d.get("suggestions", d) if isinstance(d, dict) else d
        return [str(x).strip() for x in items if str(x).strip()][:5], "llm"
    except llm.LLMUnavailable:
        return _offline_studio(action, idea or lyrics or selection), "offline"


def _offline_studio(action, seed):
    rnd = random.Random(f"{action}|{seed}|{random.random()}")
    words = keywords(seed) or ["love", "night"]
    a, b = rnd.choice(words), rnd.choice(words)
    fmt = lambda s: s.format(a=a, b=b, A=a.capitalize())  # noqa: E731
    if action == "title":
        return [f"{a.capitalize()} {x}" for x in ("Tonight", "Forever", "In Blue", "Again", "Heart")]
    kind = {"add_chorus": "chorus", "strengthen_hook": "chorus", "add_bridge": "bridge", "continue_section": "pre"}.get(action, "verse")
    out = []
    for _ in range(5):
        pool = _LINES[kind][:]
        rnd.shuffle(pool)
        n = 4 if action in ("add_verse", "add_chorus", "full_draft") else (2 if action in ("continue_section", "add_bridge") else 1)
        lines = [fmt(x) for x in (pool * 3)[:n]]
        tag = {"add_verse": "[Verse]\n", "add_chorus": "[Chorus]\n", "add_bridge": "[Bridge]\n"}.get(action, "")
        out.append(tag + "\n".join(lines))
    return out


SPEECH_PRESETS = {
    "voiceover": {"tone": "Clear, friendly and confident", "music": "light modern corporate, soft keys, gentle pulse", "voice": "af_heart", "speed": 1.0},
    "asmr": {"tone": "Whispery, slow, very soft and close", "music": "ambient soft pads, gentle rain texture, no drums", "voice": "af_nicole", "speed": 0.85},
    "bedtime-story": {"tone": "Warm, calm storyteller, slow and soothing", "music": "music box lullaby, soft celesta, warm strings, no drums", "voice": "bf_emma", "speed": 0.9},
    "meditation": {"tone": "Calm, grounded, spacious with long pauses", "music": "ambient drone, singing bowls, slow evolving pads, no drums", "voice": "am_michael", "speed": 0.82},
    "podcast": {"tone": "Energetic, conversational host", "music": "upbeat lo-fi hip hop groove, warm keys", "voice": "am_puck", "speed": 1.05},
    "story": {"tone": "Expressive narrator", "music": "cinematic underscore, soft piano and strings", "voice": "bm_george", "speed": 0.95},
}


def speech_script(description, preset="voiceover", length="short"):
    p = SPEECH_PRESETS.get(preset, SPEECH_PRESETS["voiceover"])
    words = {"short": 90, "medium": 180, "long": 350}.get(length, 120)
    try:
        d = llm.chat_json(
            "You write spoken-word scripts for voice overs, podcasts, stories, ASMR and guided meditations. "
            "Scripts read naturally aloud: short sentences, clear punctuation, paragraph breaks for pauses.",
            f"Brief: {description}\nKind: {preset}\nTarget length: about {words} words.\n"
            'Return {"title": str, "script": str, "tone": str, "music_style": str (background music tags)}.',
        )
        return {"title": d.get("title") or _offline_title(description), "script": d.get("script", ""),
                "tone": d.get("tone") or p["tone"], "music_style": d.get("music_style") or p["music"], "source": "llm"}
    except llm.LLMUnavailable:
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", description) if s.strip()]
        opener = {
            "asmr": "Hey. Settle in. Let's slow everything down together.",
            "bedtime-story": "Once upon a time, in a quiet place far from here, a story was waiting to be told.",
            "meditation": "Find a comfortable position. Close your eyes, and take a slow, deep breath in.\n\nAnd gently let it go.",
            "podcast": "Hey everyone, and welcome back to the show!",
        }.get(preset, "Hello, and welcome.")
        body = "\n\n".join(sentences) if sentences else description
        return {"title": _offline_title(description), "script": f"{opener}\n\n{body}\n\nThank you for listening.",
                "tone": p["tone"], "music_style": p["music"], "source": "offline"}

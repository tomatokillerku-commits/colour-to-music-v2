#!/usr/bin/env python3
"""
suno_prompt.py — 融合层: 颜色数值 + AI 情感 → 英文音乐生成 prompt

设计原则:
  · 优先使用 AI 视觉情感 (ai_vision 输出的 mood / valence / arousal / tension
    / narrative / musical_hint), 因为语义情感是规则公式无法推算的
  · 颜色数值负责可量化、可复现的部分: 调式 / BPM / 音区 / 音色 / 张力
  · AI 的 narrative 与 musical_hint 直接进 prompt, 这是音乐"情感"的真实来源

输出语言: 全部英文 (界面展示与 Suno 生成均使用英文)
"""

import re

# ---- 调式 → 英文 ----
MODE_EN = {"大调": "major key", "小调": "minor key"}

# ---- 音色 → 英文乐器 ----
TIMBRE_EN = {
    "中音弦乐": "viola-led strings",
    "高音铜管(短笛/小号)": "high brass, piccolo and trumpet",
    "长笛/中音弦乐": "flute with viola strings",
    "大提琴/巴松管/管风琴": "cello, bassoon and organ",
    "大提琴": "cello",
    "巴松管": "bassoon",
    "管风琴": "organ",
    "长笛": "flute",
    "小提琴": "violin",
    "铜管": "brass",
    "小号": "trumpet",
}

# ---- 音区 → 英文 ----
PITCH_EN = {
    "C5–C7 (高音区)": "high register, C5-C7",
    "C2–C4 (低音区)": "low register, C2-C4",
    "C4–C5 (中音区)": "mid register, C4-C5",
}

# ---- arousal → 速度/能量 ----
AROUSAL_EN = [
    (0.78, "fast, driving and relentless"),
    (0.60, "brisk and animated"),
    (0.42, "unhurried and flowing"),
    (0.0,  "slow, still and sustained"),
]

# ---- valence → 情绪色彩 ----
VALENCE_EN = [
    (0.40, "bright and uplifting"),
    (0.15, "neutral and balanced"),
    (-0.15, "somber and introspective"),
    (-1.0, "dark and anguished"),
]

# ---- tension → 和声 ----
TENSION_EN = [
    (0.66, "sharp dissonance, tritone clashes, unresolved harmonic tension"),
    (0.33, "mild dissonance, uneasy colour, suspended harmony"),
    (0.0,  "consonant harmony, open fifths, calm resolution"),
]

# ---- persona(主色性格) → 英文 ----
PERSONA_EN = {
    "红": "red", "橙": "orange", "黄": "yellow",
    "绿": "green", "蓝": "blue", "紫": "violet",
}


def _pick(table, value):
    for thr, txt in table:
        if value >= thr:
            return txt
    return table[-1][1]


def _main_timbre(cn: str) -> str:
    """取拼接音色串的第一项(先查整串, 再查首项, 避免 '/' 破坏键名)"""
    cn = cn.strip()
    if cn in TIMBRE_EN:
        return cn
    return cn.split("/")[0].strip()


def motif_clause(names: list) -> str:
    """五音动机的英文句子（生成时拼到 prompt 尾部，画廊与上传共用）。"""
    if not names:
        return ""
    return (
        "Opening motif, five notes read top band to bottom: "
        + " ".join(names)
        + ", each note a sparse plucked entry from one horizontal band of the painting; "
          "the contour is fixed, do not transpose it."
    )


def build_suno_prompt(metrics: dict, emotion: dict, ai: dict = None,
                     mapping: dict = None, image_path: str = None) -> dict:
    """
    输入:
      metrics : color_extractor.extract_color_metrics 的返回值
      emotion : emotion_model.color_metrics_to_emotion 的返回值(无 AI 时的兜底)
      ai      : ai_vision.analyze_painting 的返回值(优先使用)
      mapping : mapping_rules.build 的返回值(有则按文献规则层输出, 优先于旧字段)

    输出: 全英文字典, 含 style_en / full_en 等
    """
    wc = metrics["warm_cold"]
    sat = metrics["saturation"]
    br = metrics["brightness"]
    rg = metrics["red_green_index"]
    dh = metrics["dominant_hue"]

    # ---- 颜色数值(客观, 始终来自测量) ----
    mode_en = MODE_EN.get(wc["mode"], wc.get("mode_en", "major key"))
    timbre_en = TIMBRE_EN.get(_main_timbre(dh["timbre"]),
                              dh.get("timbre_en", "strings"))
    pitch_en = PITCH_EN.get(br["pitch_range"], br.get("pitch_range_en", "mid register"))

    nums = re.findall(r"(\d+)", sat["tempo_range"])
    bpm = int(nums[0]) if nums else 90

    rgi = abs(rg.get("RGI_lab", 0.0))

    # ---- 有 mapping 时, 用规则层的输出覆盖旧字段 ----
    rule_line = ""
    if mapping:
        p = mapping["params"]
        from mapping_rules import pitch_to_note
        pitch_en = f"anchor {p['pitch_note']} ({p['register']})"
        mode_en = p["mode"]
        bpm = p["bpm"]
        if p["instrument_candidates"]:
            timbre_en = ", ".join(p["instrument_candidates"])
        rule_line = (
            f"Rule basis [{', '.join(r['rule_id'] for r in mapping['evidence'])}]: "
            f"lightness L*={p['mean_L']} -> register/pitch; "
            f"saturation S={p['mean_S']} -> loudness {p['loudness_target_db']} dBFS; "
            f"lightness -> timbre brightness ~{p['brightness_target_hz']} Hz centroid."
        )

    # ---- 情感: 优先 AI, 否则用规则模型兜底 ----
    if ai:
        valence = float(ai.get("valence", emotion.get("valence", 0.0)))
        arousal = float(ai.get("arousal", emotion.get("arousal", 0.5)))
        tension = float(ai.get("tension", 0.0))
        mood = ai.get("mood", "")
        narrative = ai.get("narrative", "")
        musical_hint = ai.get("musical_hint", "")
        source = "ai"
    else:
        valence = float(emotion.get("valence", 0.0))
        arousal = float(emotion.get("arousal", 0.5))
        tension = min(1.0, rgi / 12.0)
        mood = ""
        narrative = emotion.get("narrative", "")
        musical_hint = ""
        source = "rule"

    persona_en = PERSONA_EN.get(emotion.get("persona", ""), emotion.get("persona", ""))

    arousal_en = _pick(AROUSAL_EN, arousal)
    valence_en = _pick(VALENCE_EN, valence)
    tension_en = _pick(TENSION_EN, tension)

    # ---- style 行: Suno 的 Style of Music 字段 ----
    style_en = (
        f"Instrumental, {timbre_en}, {mode_en}, {pitch_en}, "
        f"around {bpm} BPM, {arousal_en}, {valence_en}, {tension_en}."
    )

    # ---- 完整 prompt: style + 情绪 + AI 叙事 + AI 音乐建议 ----
    parts = [style_en]
    if rule_line:
        parts.append(rule_line)

    head = "Mood: "
    if mood:
        head += f"{mood.capitalize()} — "
    head += f"a {persona_en}-toned painting translated into sound, " \
            f"{valence_en}, {arousal_en}."
    parts.append(head)

    if narrative:
        parts.append(f"Color story: {narrative}")
    if musical_hint:
        parts.append(f"Musical direction: {musical_hint}")

    # ---- 五音动机：把签名层的旋律写进 prompt ----
    # 之前 prompt 里只有"E4 附近 / 85 BPM / 小号+小提琴"，两幅画的 prompt 七项相同，
    # Suno 没有任何理由把它们做成不同的东西。这里把五个音直接写进去。
    motif_en = ""
    motif_names: list = []
    if image_path:
        try:
            import synth
            bm = synth.band_motif(image_path)
            motif_names = bm.get("names") or []
            if motif_names:
                motif_en = (
                    "Opening motif, five notes read top band to bottom: "
                    + " ".join(motif_names)
                    + ", each note a sparse plucked entry from one horizontal band of the "
                      "painting; the contour is fixed, do not transpose it."
                )
                parts.append(motif_en)
        except Exception:
            motif_en = ""

    full_en = "\n".join(parts)

    return {
        # 给 Suno 用
        "style_en": style_en,
        "full_en": full_en,
        "motif_en": motif_en,
        "motif_notes": motif_names,
        # 展示用
        "mood": mood,
        "narrative": narrative,
        "musical_hint": musical_hint,
        "persona_en": persona_en,
        "mode_en": mode_en,
        "timbre_en": timbre_en,
        "pitch_en": pitch_en,
        "tension_en": tension_en,
        "arousal_en": arousal_en,
        "valence_en": valence_en,
        # 数值
        "bpm": bpm,
        "valence": round(valence, 3),
        "arousal": round(arousal, 3),
        "tension": round(tension, 3),
        "rgi": round(rgi, 3),
        "source": source,
        "rule_basis": rule_line,
    }


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    from color_extractor import load_and_preprocess, extract_color_metrics
    from emotion_model import color_metrics_to_emotion

    img_dir = Path(__file__).parent / "artworks"
    cache_f = Path(__file__).parent / "ai_emotion_cache.json"
    cache = json.loads(cache_f.read_text(encoding="utf-8")) if cache_f.exists() else {}

    target = sys.argv[1] if len(sys.argv) > 1 else "赵无极-20-03-60.jpeg"
    p = img_dir / target
    if not p.exists():
        print(f"not found: {p}")
        sys.exit(1)

    m = extract_color_metrics(load_and_preprocess(str(p)))
    emo = color_metrics_to_emotion(m)
    ai = cache.get(p.name)

    out = build_suno_prompt(m, emo, ai)
    print(f"=== {p.name}  (source: {out['source']}) ===")
    print(out["full_en"])

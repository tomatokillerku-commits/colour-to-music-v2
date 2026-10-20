#!/usr/bin/env python3
"""
music_prompt_ai.py — 用 Gemini 把「颜色数据 + AI 情感」转译成专业音乐生成 prompt

定位: 融合层的最后一步
  ① 颜色数值 (客观测量)  ─┐
  ② AI 画面情感 (语义理解)─┼→ ③ Gemini 转译 → ④ 音乐 prompt → ⑤ Suno API
                          ─┘

为什么要这一步 AI 转译:
  规则模板只能机械拼接关键词("minor key, 70 BPM, dark")，
  而 Gemini 懂音乐术语，能写出真正对生成有用的描述
  ("Presto agitato with unresolved cluster chords in low brass,
    aggressive string tremolos, relentless timpani roll")。
  这正是用户反馈"缺少情感"的解药。

输出: outputs/music_prompts.json
"""

import os
import sys
import json
import time
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ai_vision import get_api_key, _extract_json, DEFAULT_MODEL, _call_gemini

API_BASE = "https://generativelanguage.googleapis.com/v1beta"

HERE = Path(__file__).parent
INPUT = HERE / "outputs" / "prompts.json"
CACHE = HERE / "ai_emotion_cache.json"
OUT = HERE / "outputs" / "music_prompts.json"

# 目标时长: 60-120 秒
TRANSLATE_PROMPT = """You are a composer and music producer writing a generation prompt
for an AI music model (Suno). Your prompt will directly determine the quality of the output.

You are given:
  1. Objective COLOR MEASUREMENTS extracted from a painting
  2. An AI EMOTIONAL READING of that painting

Your task: translate these into a precise, evocative music generation prompt.

Requirements:
  - Output ONLY the prompt itself, no explanation, no preamble
  - Target duration: EXACTLY 60 seconds. State "Duration: 60 seconds"
  - INSTRUMENTAL ONLY - no vocals, no lyrics
  - Style line first: genre, key, tempo in BPM, instrumentation, register
  - Then 2-4 sentences of musical direction: dynamics, harmonic language,
    texture, articulation, development arc
  - Use real musical terminology (e.g. "Presto agitato", "cluster chords",
    "subito forte", "ostinato", "rubato", "tritone", "tremolo", "sul ponticello")
  - The music MUST express the painting's emotional reading, not just its colors
  - Be specific and concrete, avoid vague adjectives

CRITICAL — Historical style matching:
  The music style MUST match the artwork's historical period and movement.
  A 19th-century Post-Impressionist painting should sound like 19th-century
  music. A 1957 abstract painting must NOT sound like Romantic orchestral music.
    · era_style_label : the target genre/style — put this genre in your style line
    · era_style_hint  : what the idiom SHOULD sound like
    · era_style_avoid : HARD CONSTRAINTS — you must NOT include these

  The AVOID list is binding. If it says "NO melody", write no melody.
  If it says "NO orchestral strings", use no strings.
  Do not fall back on generic cinematic orchestral language — that is the
  most common failure mode and it is explicitly rejected here.

Ground rules:
  - The COLOR DATA gives you objective anchors (key, tempo range, brightness=register,
    saturation=energy, RGI=counterpoint tension). Respect them.
  - The EMOTIONAL READING is the soul. Prioritize it when it conflicts with raw color stats
    (e.g. a warm-hued painting that reads as anguished should sound dark, not bright).
  - The ERA STYLE constrains genre and instrumentation. A 1892 Gauguin must not
    sound like a 1968 Vasarely synth piece.

INPUT DATA:
--- ARTWORK ---
Title: {title}
Artist: {artist}
Year: {year}
Movement: {movement}

--- COLOR MEASUREMENTS ---
{color_block}

--- ERA STYLE (historical matching — binding) ---
Genre / style: {era_label}
Sound like this: {era_hint}
MUST AVOID: {era_avoid}

--- AI EMOTIONAL READING ---
Mood: {mood}
Valence: {valence}  (-1 anguished .. 1 joyful)
Arousal: {arousal}  (0 still .. 1 agitated)
Tension: {tension}  (0 harmonious .. 1 conflicting)
Narrative: {narrative}
Musical hint: {musical_hint}

{rules_block}

--- OUTPUT ---
Write the music generation prompt now (plain text, no JSON, no quotes):
"""


def build_color_block(d: dict) -> str:
    return (
        f"Dominant hue: {d.get('dominant_hue_en','?')}\n"
        f"Timbre mapping: {d.get('timbre_en','?')}\n"
        f"Musical mode: {d.get('mode_en','?')}\n"
        f"Pitch register: {d.get('pitch_en','?')}\n"
        f"Mean saturation (energy): {d.get('mean_S','?')}\n"
        f"Mean brightness (register): {d.get('mean_V','?')}\n"
        f"Warm ratio: {d.get('warm_ratio','?')}\n"
        f"RGI (red-green counterpoint tension): {d.get('rgi','?')}\n"
        f"Suggested BPM: {d.get('bpm','?')}"
    )


def build_rules_block(mapping: dict) -> str:
    """把文献规则层写成 Gemini 必须遵守的约束块。

    为什么需要: 只给颜色数值时, 模型会自己发明一套颜色→音乐对应
    (实测给赵无极写出 "viola-led strings, mid-to-high register", 与规则层
    的 D3 音高和 trumpet/violin 候选直接冲突)。这里把 evidence 规则写成硬约束。
    """
    p = mapping["params"]
    cands = ", ".join(p.get("instrument_candidates") or []) or "free choice of the ensemble"
    lines = [
        "--- RULE LAYER (BINDING — the style line must obey these numbers) ---",
        "Only these three mappings have experimental support. They fix direction;",
        "the numeric ranges are project settings, not formulas from the papers.",
        f"  [R1] lightness L* = {p['mean_L']}  ->  pitch anchor {p.get('pitch_note','')} "
        f"(MIDI {p['pitch_anchor_midi']}), {p.get('register','')}",
        f"  [R2] saturation S = {p['mean_S']}  ->  target loudness {p['loudness_target_db']} dBFS RMS",
        f"  [R3] lightness L* = {p['mean_L']}  ->  target timbre brightness "
        f"~{p['brightness_target_hz']} Hz spectral centroid",
        "Project design choices you may orchestrate within:",
        f"  tempo {p['bpm']} BPM, mode {p['mode']}, harmonic tension {p['harmony']},",
        f"  instrument candidates: {cands}",
        "",
        "HARD CONSTRAINTS:",
        f"  1. The style line MUST state all of: {p['bpm']} BPM, anchor {p.get('pitch_note','')}, "
        f"{p['mode']}, about {p['loudness_target_db']} dBFS, brightness near {p['brightness_target_hz']} Hz.",
        "  2. Do NOT move the pitch centre by an octave or more, and do NOT replace the instrument",
        "     candidates with a different family (if candidates are listed, use them).",
        "  3. Do NOT invent new colour-to-music correspondences. Anything beyond R1-R3 must be",
        "     phrased as an arrangement choice, not as a mapping rule.",
    ]
    return "\n".join(lines)


def translate(data: dict, ai: dict, api_key: str, model: str = DEFAULT_MODEL,
              era: dict = None, mapping: dict = None) -> str:
    era = era or {}
    rules_block = build_rules_block(mapping) if mapping else (
        "--- RULE LAYER ---\n(no mapping layer supplied; keep colour claims minimal)"
    )
    prompt = TRANSLATE_PROMPT.format(
        title=data.get("title", ""),
        artist=data.get("artist", ""),
        year=data.get("year", ""),
        movement=data.get("movement", ""),
        color_block=build_color_block(data),
        rules_block=rules_block,
        era_label=era.get("label", "Contemporary instrumental"),
        era_hint=era.get("hint", "Contemporary instrumental writing."),
        era_avoid=era.get("avoid", "No vocals. No pop song structure."),
        mood=ai.get("mood", ""),
        valence=ai.get("valence", 0),
        arousal=ai.get("arousal", 0),
        tension=ai.get("tension", 0),
        narrative=ai.get("narrative", ""),
        musical_hint=ai.get("musical_hint", ""),
    )
    url = f"{API_BASE}/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7},
    }
    r, _used = _call_gemini(payload, api_key, model, timeout=120)
    try:
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        raise RuntimeError(f"解析失败: {r.text[:250]}")


def main():
    key = get_api_key()
    if not key:
        print("错误: 请设置 GEMINI_API_KEY", file=sys.stderr)
        sys.exit(1)

    data = json.loads(INPUT.read_text(encoding="utf-8"))
    cache = json.loads(CACHE.read_text(encoding="utf-8"))

    out = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}

    targets = sys.argv[1:] if len(sys.argv) > 1 else list(data.keys())
    targets = [t if t in data else k for t in targets for k in data if t in k]

    ok = 0
    for i, name in enumerate(targets, 1):
        if name in out and out[name].get("music_prompt"):
            print(f"[{i}/{len(targets)}] 跳过(已有): {name}")
            ok += 1
            continue

        d = data[name]
        ai = cache.get(name)
        if not ai or "error" in ai:
            print(f"[{i}/{len(targets)}] ❌ 无 AI 情感数据: {name}")
            continue

        print(f"[{i}/{len(targets)}] {d.get('title','')} ...", flush=True)

        # 按年代/流派取音乐风格
        try:
            import server
            era = server.get_era_style({"artist": d.get("artist", ""),
                                        "movement": d.get("movement", ""),
                                        "year": d.get("year", "")})
        except Exception:
            era = {"label": "Contemporary instrumental",
                   "hint": "Contemporary instrumental writing."}

        for attempt in range(4):
            try:
                mp = translate(d, ai, key, era=era)
                out[name] = {
                    "file": name,
                    "artist": d.get("artist", ""),
                    "title": d.get("title", ""),
                    "mood": ai.get("mood", ""),
                    "music_prompt": mp,
                }
                OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"    ✓ {len(mp)} chars", flush=True)
                ok += 1
                break
            except Exception as e:
                msg = str(e)
                if "429" in msg or "quota" in msg.lower():
                    wait = 40 * (attempt + 1)
                    print(f"    限流, 等 {wait}s 重试...", flush=True)
                    time.sleep(wait)
                else:
                    print(f"    ❌ {msg[:120]}", flush=True)
                    break
        time.sleep(6)

    print(f"\n完成 {ok}/{len(targets)} -> {OUT}", flush=True)


if __name__ == "__main__":
    main()

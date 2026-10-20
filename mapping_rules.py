#!/usr/bin/env python3
"""
mapping_rules.py — 文献驱动的映射层（需求书 §2 / P0-3）

核心原则
--------
1. 只有 3 条规则算「有实验证据支持的映射」(evidence)：
     R1  L*     ↑ → 音高 Pitch          ↑   [R1][R2]
     R2  S(HSV) ↑ → 响度 Loudness       ↑   [R1]
     R3  L*     ↑ → 音色明亮度 Spectral Brightness ↑ [R1][R3]
   这三条只固定「方向」，不提供任何通用数值公式。

2. 其余一律 `design`（项目设计选择），与 evidence 分开输出、分开展示：
   BPM / 调式 / 乐器 / 和声张力 / 音区边界 / dB 区间 / Hz 区间。

3. 每条规则都必须可追溯：
     rule_id · 输入名与数值 · 输出参数与数值 · 参考编号 · 是否设计假设

4. 需求书 §2 明确删除或降级的旧规则，全部列在 DEPRECATED 里并写明理由，
   不参与计算（只保留旧数值供「修正前/后」对照）。

数值区间的出处：全部是本项目设定的。L*=75→C5 这类公式论文里没有，
论文只支持「越高越偏高音」这个方向。
"""

import math

# ── 参考文献（UI 与汇报材料共用） ──────────────────────────────────────────────
REFS = {
    "R1": "Anikin & Johansson (2019), Atten. Percept. Psychophys. — 明度→音高、饱和度→响度",
    "R2": "Sun et al. (2018), PMC5835347 — 明度→音高的直接实验依据",
    "R3": "Saitis & Wallmark (2024), PMC11410849 — 视觉明度→音色明亮度",
    "R4": "Reymore & Lindsey (2025), Front. Psychol. — 颜色与乐器的群体匹配倾向（仅候选）",
    "R5": "Itti, Koch & Niebur (1998), IEEE TPAMI — 视觉显著性",
    "R6": "Hamilton-Fletcher et al. (2016) — 跨模态对应的感官替代评价思路",
    "R7": "National Eye Institute — 色觉异常类型与感知能力",
    "R8": "Raffel & Ellis (2014), pretty_midi — MIDI 技术实现",
}

# ── 旧版规则：需求书要求删除或降级 ────────────────────────────────────────────
DEPRECATED = [
    {
        "id": "OLD-1",
        "old_rule": "暖色占比 W > 0.5 → 大调；否则小调",
        "why": "没有颜色-调式的直接实验证据；且暖色区间只占色环 33%，用 0.5 作阈值会把"
               "几乎所有画判成小调（旧版实测多处误判）。",
        "now": "调式由 AI 语义判定 valence 决定，标为 design",
    },
    {
        "id": "OLD-2",
        "old_rule": "RGI（红绿对比指数）→ 不协和音程 / 和声张力",
        "why": "RGI 只覆盖红-绿轴，红-黑、橙-蓝型画面的张力测不出来；且不存在"
               "「红绿对比→小二度/三全音」的实验依据。",
        "now": "和声张力改由 AI 判定的 tension 决定，标为 design；RGI 仅作画面统计量保留",
    },
    {
        "id": "OLD-3",
        "old_rule": "色相扇区 → 固定乐器（红橙→中音弦乐、黄→高音铜管、蓝紫→大提琴+管风琴）",
        "why": "R4 只给出特定实验条件下的群体匹配倾向，不能当普遍规律。",
        "now": "改为 instrument_candidates（候选，最多 2 个），标为 design",
    },
    {
        "id": "OLD-4",
        "old_rule": "平均饱和度 S → BPM（快/中/慢三档）",
        "why": "文献支持的是饱和度→响度，不是饱和度→速度。",
        "now": "饱和度改接响度；BPM 由 arousal 决定，标为 design",
    },
    {
        "id": "OLD-5",
        "old_rule": "HSV-V 平均明度 → 音高区（C2-C4 / C4-C5 / C5-C7）",
        "why": "HSV-V 不是感知明度，在饱和色上高估亮度（旧版最大偏差 19.2 点）。",
        "now": "改用 CIELAB L*；分档边界 40/65 是本项目设定",
    },
]

# ── 乐器候选：R4 的群体匹配倾向，仅作候选 ─────────────────────────────────────
INSTRUMENT_CANDIDATES = {
    "red / orange": ["trumpet", "violin"],
    "yellow":       ["trumpet"],
    "green":        [],
    "blue / violet": ["clarinet"],
}

# ── 参数映射区间（全部为项目设计参数） ────────────────────────────────────────
MIDI_MIN, MIDI_MAX = 36.0, 84.0      # C2 .. C6
LOUD_DB_MIN, LOUD_DB_MAX = -30.0, -18.0   # 目标 RMS dBFS
CENTROID_HZ_MIN, CENTROID_HZ_MAX = 700.0, 3500.0


def _rule(rule_id, kind, sentence, in_name, in_val, in_unit,
          out_name, out_val, out_unit, refs, note=""):
    return {
        "rule_id": rule_id,
        "kind": kind,                       # evidence | design
        "sentence": sentence,               # 「A ↑ → B ↑」这种可读的一句话
        "input": {"name": in_name, "value": in_val, "unit": in_unit},
        "output": {"name": out_name, "value": out_val, "unit": out_unit},
        "refs": refs,
        "note": note,
    }


def build(metrics: dict, ai: dict = None) -> dict:
    """把颜色测量值 + AI 语义 → 一组带编号、带出处的映射规则

    metrics: color_extractor.extract_color_metrics() 的返回
    ai     : ai_vision.analyze_full() 的返回（可为 None，此时语义类规则降级）
    """
    ai = ai or {}
    br = metrics["brightness"]
    sat = metrics["saturation"]

    L = float(br.get("mean_L", 50.0))
    S = float(sat.get("mean_S", 0.0))
    L_clamped = max(0.0, min(100.0, L))

    evidence = []
    design = []

    # ── R1: L* → 音高（方向有证据，数值区间是本项目设定） ──────────────────
    anchor = MIDI_MIN + (L_clamped / 100.0) * (MIDI_MAX - MIDI_MIN)
    anchor = round(anchor, 1)
    note_name = pitch_to_note(anchor)
    register = "low register" if anchor < 48 else ("high register" if anchor > 66 else "mid register")
    evidence.append(_rule(
        "R1", "evidence",
        "Lightness (CIELAB L*) ↑ → Pitch ↑",
        "mean_L*", round(L, 2), "L* 0–100",
        "pitch_anchor", anchor, f"MIDI ≈ {note_name} ({register})",
        ["R1", "R2"],
        "方向有实验依据；C2–C6 的音域与线性斜率是本项目设定，不是论文公式",
    ))

    # ── R2: S → 响度（不是 BPM） ───────────────────────────────────────────
    loud = LOUD_DB_MIN + S * (LOUD_DB_MAX - LOUD_DB_MIN)
    loud = round(loud, 1)
    evidence.append(_rule(
        "R2", "evidence",
        "Saturation (HSV S) ↑ → Loudness ↑",
        "mean_S", round(S, 3), "HSV S 0–1",
        "loudness_target", loud, "dBFS (RMS)",
        ["R1"],
        f"—30…−18 dBFS 的目标区间为项目设定；MIDI velocity ≠ 实际响度，需对音频测量（见 synth.py）",
    ))

    # ── R3: L* → 音色明亮度（频谱重心） ────────────────────────────────────
    cen = CENTROID_HZ_MIN + (L_clamped / 100.0) * (CENTROID_HZ_MAX - CENTROID_HZ_MIN)
    cen = round(cen, 0)
    evidence.append(_rule(
        "R3", "evidence",
        "Lightness (L*) ↑ → Spectral Brightness ↑（音色，≠ 音符音高）",
        "mean_L*", round(L, 2), "L* 0–100",
        "target_centroid", int(cen), "Hz (频谱重心)",
        ["R1", "R3"],
        "700–3500 Hz 区间为项目设定；由合成器的谐波衰减实现，可对输出音频测频谱重心验证",
    ))

    # ── D1: arousal → BPM（AI 语义，非颜色公式） ───────────────────────────
    if ai:
        arousal = float(ai.get("arousal", 0.5) or 0.5)
        src = "AI semantic reading"
    else:
        # 无 AI 时不要假装知道情绪：取中性值，并明确标注
        arousal = 0.5
        src = "no AI available → neutral default"
    bpm = int(round(50 + arousal * 70))  # 50..120
    design.append(_rule(
        "D1", "design",
        "Arousal ↑ → Tempo ↑",
        "arousal", round(arousal, 2), "0–1", "tempo", bpm, "BPM",
        [], f"来源: {src}。旧版的 S→BPM 已废弃",
    ))

    # ── D2: valence → 调式 ────────────────────────────────────────────────
    val = float(ai.get("valence", 0.0) or 0.0) if ai else 0.0
    if val > 0.15:
        mode = "major key"
    elif val < -0.15:
        mode = "minor key"
    else:
        mode = "modal / ambiguous"   # 中性时不要硬塞大小调
    design.append(_rule(
        "D2", "design",
        "Valence → Mode",
        "valence", round(val, 2), "-1–1", "mode", mode, "—",
        [], "±0.15 为项目阈值；旧版「暖色→大调」已废弃",
    ))

    # ── D3: 主导色相 → 乐器候选（R4 只支持候选） ──────────────────────────
    hue_label = metrics["dominant_hue"].get("label_en", "")
    cands = INSTRUMENT_CANDIDATES.get(hue_label, [])
    design.append(_rule(
        "D3", "design",
        "Dominant hue → Instrument candidates (not binding)",
        "dominant_hue", hue_label, "—",
        "instrument_candidates", ", ".join(cands) or "free choice", "—",
        ["R4"],
        "R4 是特定实验条件下的群体匹配倾向；不得写成固定对应",
    ))

    # ── D4: tension → 和声张力 ────────────────────────────────────────────
    tension = float(ai.get("tension", 0.0) or 0.0) if ai else 0.0
    if tension > 0.66:
        harm = "sharp dissonance, unresolved tension"
    elif tension > 0.33:
        harm = "mild dissonance, suspended harmony"
    else:
        harm = "consonant harmony, open fifths"
    design.append(_rule(
        "D4", "design",
        "Tension → Harmonic tension",
        "tension", round(tension, 2), "0–1", "harmony", harm, "—",
        [], "旧版 RGI→不协和 已废弃",
    ))

    params = {
        "pitch_anchor_midi": anchor,
        "pitch_note": note_name,
        "register": register,
        "loudness_target_db": loud,
        "brightness_target_hz": int(cen),
        "bpm": bpm,
        "mode": mode,
        "instrument_candidates": cands,
        "harmony": harm,
        "mean_L": round(L, 2),
        "mean_S": round(S, 3),
        "mean_V_hsv_legacy": br.get("mean_V"),
        "pitch_range_hsv_legacy": br.get("pitch_range_hsv_en", ""),
    }

    return {
        "evidence": evidence,
        "design": design,
        "params": params,
        "deprecated": DEPRECATED,
        "refs": REFS,
        "notes": [
            "evidence = 有颜色-声音实验支持的方向；数值区间仍是本项目设定",
            "design   = 项目/AI 的编排选择，不得当作文献结论",
            "所有阈值集中在 color_extractor.THRESHOLDS 与本文件顶部常量",
        ],
    }


def pitch_to_note(midi: float) -> str:
    """MIDI 音高 → 音名（仅用于展示）"""
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    n = int(round(midi))
    return f"{names[n % 12]}{n // 12 - 1}"


def summary_lines(mapping: dict) -> list:
    """给汇报材料/终端用的一行一条摘要"""
    out = []
    for r in mapping["evidence"]:
        out.append(
            f"[{r['rule_id']}] EVIDENCE  {r['input']['name']}={r['input']['value']}"
            f" → {r['output']['name']}={r['output']['value']} {r['output']['unit']}"
            f"  refs={','.join(r['refs'])}"
        )
    for r in mapping["design"]:
        out.append(
            f"[{r['rule_id']}] DESIGN    {r['input']['name']}={r['input']['value']}"
            f" → {r['output']['name']}={r['output']['value']} {r['output']['unit']}"
        )
    return out


if __name__ == "__main__":
    import sys
    import json
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    from color_extractor import load_and_preprocess, extract_color_metrics

    p = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).parent / "artworks" / "赵无极-20-03-60.jpeg")
    m = extract_color_metrics(load_and_preprocess(p))
    mp = build(m, None)
    print(f"== {Path(p).name}")
    print(f"L*={mp['params']['mean_L']}  S={mp['params']['mean_S']}  "
          f"→ {pitch_to_note(mp['params']['pitch_anchor_midi'])}")
    for line in summary_lines(mp):
        print(line)
    print(json.dumps(mp["params"], ensure_ascii=False, indent=2))

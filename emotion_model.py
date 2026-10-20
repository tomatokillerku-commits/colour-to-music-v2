#!/usr/bin/env python3
"""
emotion_model.py — 情感层 (任务: 颜色 → 情感坐标 → 演奏表情)

理论依据 (B 艺术直觉派):
  · 康定斯基《论艺术的精神》(1911): 黄=尖锐刺耳/急躁(高唤醒·偏刺激),
    红=温暖·有重量·内在张力, 蓝=宁静深远, 绿=平和静止, 白=静默孕育, 黑=消亡沉寂。
  · 歌德《色彩论》(1810): 暖色(红橙黄)=活泼向外, 冷色(蓝绿紫)=安静向内;
    绿=满足宁静; 暖=主动, 冷=被动。

情感坐标采用 Russell 环形模型的两个轴:
  · valence (效价)  [-1, 1]: 负向(沉重/刺激) ↔ 正向(愉悦/明亮)
  · arousal (唤醒)  [ 0, 1]: 低(静) ↔ 高(动)

颜色指标 → 情感坐标的映射思路:
  - 主导色相 Hue 提供"性格基调" (hue_valence, hue_arousal)
  - 暖色占比 W 推动 arousal 与 valence 的暖向偏移 (歌德暖=活泼向外)
  - 平均饱和度 S̄ 提升 arousal (越饱和越"响")
  - 平均明度 V̄ 提升 valence (越明亮越积极)
  - RGI (红绿对立) 提升 arousal 并带"紧张"色彩 (与既有 tension 一致)

本模块产出一组"演奏表情参数", 供 music_pipeline 消费:
  contour      : 旋律轮廓形状 ('rising'|'falling'|'arch'|'wave'|'flat')
  dynamics_curve: 力度曲线 ('cresc'|'dim'|'pulse'|'steady')
  articulation : 奏法 ('staccato'|'legato'|'tenuto')
  vibrato_depth: 颤音深度系数 [0,1]
  breath       : 句法呼吸强度 [0,1] (乐句间的留白/停顿比例)
  valence, arousal: 回传原始坐标, 便于文字解读
"""

import numpy as np

# ============================================================
# 1. 色相性格表 (康定斯基 + 歌德 综合)
#    每个色相给出 (valence, arousal) 基线, 范围 valence∈[-1,1], arousal∈[0,1]
# ============================================================
HUE_PERSONA = [
    # (色相中心°, 容忍半宽°, 名称, valence, arousal)
    (15,  35, "红",     +0.10, 0.78),   # 红: 温暖有重量·内在张力
    (45,  25, "橙",     +0.45, 0.70),   # 橙: 暖而愉悦·活跃
    (60,  20, "黄",     -0.15, 0.92),   # 黄: 尖锐刺耳·急躁(高唤醒偏刺激)
    (120, 40, "绿",     +0.25, 0.22),   # 绿: 平和静止·满足
    (210, 40, "蓝",     +0.15, 0.15),   # 蓝: 宁静深远
    (275, 35, "紫",     -0.10, 0.40),   # 紫: 内省·神秘
    (0,   0,  "中性/无彩", 0.00, 0.30),  # 退化项, 实际用明度主导
]


def _nearest_persona(hue: float) -> tuple:
    """按色相角找最近性格基线 (环形距离)"""
    best = None
    best_d = 1e9
    for c, half, name, v, a in HUE_PERSONA:
        if c == 0:
            continue
        d = min(abs(hue - c), 360 - abs(hue - c))
        if d < best_d:
            best_d, best = d, (name, v, a)
    return best


def color_metrics_to_emotion(metrics: dict) -> dict:
    """
    输入 color_extractor.extract_color_metrics 的返回值,
    输出情感坐标 + 演奏表情参数。
    """
    dh = metrics["dominant_hue"]
    wc = metrics["warm_cold"]
    sat = metrics["saturation"]
    br = metrics["brightness"]
    rg = metrics["red_green_index"]

    W = wc["warm_ratio_W"]                      # 暖色占比 [0,1]
    S = sat["mean_S"]                            # 平均饱和 [0,1]
    V = br["mean_V"]                             # 平均明度 [0,1]
    RGI = abs(rg.get("RGI_lab", 0.0))            # 红绿对立强度(取绝对值)

    # ---- 主导色相性格 ----
    # 用色相分布里占比最大的扇区中心近似主导 hue
    dist = dh.get("hue_distribution", {})
    label_map = {
        "红/橙": 20, "黄": 60, "绿": 120, "蓝/紫": 240,
    }
    dominant_label = dh.get("label", "红/橙")
    hue_center = label_map.get(dominant_label, 20)
    name, pv, pa = _nearest_persona(hue_center)

    # ---- Russell 坐标合成 ----
    # valence: 色相基线 + 暖(正向) + 明度(正向)
    valence = pv + 0.25 * (W - 0.5) * 2 + 0.30 * (V - 0.5) * 2
    # arousal: 色相基线 + 饱和(增强) + 暖(增强) + RGI(紧张增强)
    arousal = pa + 0.35 * S + 0.15 * W + 0.04 * min(RGI, 5.0)
    valence = float(np.clip(valence, -1.0, 1.0))
    arousal = float(np.clip(arousal, 0.0, 1.0))

    # ---- 演奏表情映射 ----
    # 轮廓: 高 arousal→上升/波动(向外冲); 低 arousal→下降/平缓(向内收)
    #       高 valence→上行明亮; 低 valence→下行沉重
    if arousal >= 0.7:
        contour = "wave" if valence >= 0 else "rising"
    elif arousal >= 0.45:
        contour = "arch" if valence >= 0 else "rising"
    else:
        contour = "falling" if valence < 0.2 else "flat"

    # 力度曲线: 高 arousal→pulse(起伏脉冲); 中→cresc(渐强); 低→steady/dim
    if arousal >= 0.7:
        dynamics_curve = "pulse"
    elif arousal >= 0.45:
        dynamics_curve = "cresc"
    else:
        dynamics_curve = "dim" if valence < 0 else "steady"

    # 奏法: 高 arousal + 黄系急躁 → staccato(断奏); 蓝绿静 → legato(连奏); 其他 tenuto
    if arousal >= 0.7 and name in ("黄", "红", "橙"):
        articulation = "staccato"
    elif arousal <= 0.3:
        articulation = "legato"
    else:
        articulation = "tenuto"

    # 颤音深度: 紧张(RGI)与中高 arousal 推深; 极静则浅
    vibrato_depth = float(np.clip(0.2 + 0.12 * RGI + 0.3 * (arousal - 0.4), 0.0, 1.0))

    # 句法呼吸: arousal 越低, 留白越多(更"呼吸")
    breath = float(np.clip(0.15 + 0.5 * (1 - arousal), 0.1, 0.7))

    return {
        "valence": round(valence, 3),
        "arousal": round(arousal, 3),
        "persona": name,
        "expression": {
            "contour": contour,
            "dynamics_curve": dynamics_curve,
            "articulation": articulation,
            "vibrato_depth": round(vibrato_depth, 3),
            "breath": round(breath, 3),
        },
        # 文字解读用 (B 派叙事)
        "narrative": _narrative(name, valence, arousal, W, S, V, RGI),
    }


def _narrative(name, valence, arousal, W, S, V, RGI) -> str:
    """Fallback narrative (used when no AI vision result is available).
    Output is English to match the project's display language."""
    base = {
        "红": "Red, as Kandinsky wrote, is warm and weighty, carrying an inward vital tension",
        "橙": "Orange fuses red and yellow — warm, lively, expanding outward",
        "黄": "Yellow is the most piercing and restless hue, like a shrill trumpet (Kandinsky)",
        "绿": "Green is the contentment and stillness Goethe described, peaceful and at rest",
        "蓝": "Blue recedes into infinite depth, growing quieter the deeper it goes (Kandinsky)",
        "紫": "Violet is the introspection of red and blue held in balance — mysterious, ambiguous",
    }.get(name, "The dominant hue sets a stable emotional ground")
    mood = ("high arousal, bursting outward" if arousal >= 0.7
            else "low arousal, settling inward" if arousal <= 0.35
            else "a moderate emotional flow")
    tone = ("bright and positive" if valence >= 0.2
            else "heavy and negative" if valence <= -0.2
            else "neutral and even")
    rgi_note = f"; red-green opposition (RGI={RGI:.2f}) adds tension" if RGI > 3 else ""
    return f"{base}. Overall the work reads as {mood} and {tone}{rgi_note}."


# ============================================================
# 2. 把表情参数翻译为具体音乐生成参数 (供 music_pipeline 调用)
# ============================================================

CONTOUR_SHAPES = {
    # 相对 base 的半音偏移序列 (按小节内拍点), 长度任意, 会循环/截断
    "rising":  [0, 2, 4, 7, 9],
    "falling": [9, 7, 4, 2, 0],
    "arch":    [0, 4, 7, 4, 0],
    "wave":    [0, 7, 2, 9, 4],
    "flat":    [4, 4, 4, 4, 4],
}

ARTICULATION = {
    # (音符占拍比例, 是否带轻微重叠)
    "staccato": (0.45, False),
    "tenuto":   (0.85, False),
    "legato":   (1.00, True),
}

DYNAMICS_CURVE = {
    # 把基础 velocity 按拍索引缩放的系数序列 (循环)
    "pulse":  [1.0, 0.6, 0.95, 0.55, 1.0],
    "cresc":  [0.6, 0.7, 0.82, 0.92, 1.0],
    "dim":    [1.0, 0.85, 0.7, 0.55, 0.45],
    "steady": [0.85, 0.85, 0.85, 0.85, 0.85],
}


def expression_to_musical(expr: dict) -> dict:
    """把 expression 字典展开成生成器直接用的具体参数"""
    e = expr["expression"] if "expression" in expr else expr
    contour = e["contour"]
    artic = e["articulation"]
    dyn = e["dynamics_curve"]
    return {
        "contour_offsets": CONTOUR_SHAPES.get(contour, CONTOUR_SHAPES["flat"]),
        "artic_ratio": ARTICULATION[artic][0],
        "artic_overlap": ARTICULATION[artic][1],
        "dyn_curve": DYNAMICS_CURVE.get(dyn, DYNAMICS_CURVE["steady"]),
        "vibrato_depth": e["vibrato_depth"],
        "breath": e["breath"],
        "contour": contour,
        "articulation": artic,
        "dynamics_curve": dyn,
    }


if __name__ == "__main__":
    import json
    from pathlib import Path
    here = Path(__file__).parent
    jf = here / "color_output_gauguin.json"
    if jf.exists():
        m = json.loads(jf.read_text(encoding="utf-8"))
        emo = color_metrics_to_emotion(m)
        print(json.dumps(emo, ensure_ascii=False, indent=2))

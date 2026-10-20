#!/usr/bin/env python3
"""
颜色数值提取器 — AI 色彩→音乐 项目
对应文档 §4.1 量化公式与可调阈值
输入：图片文件 → 输出：所有颜色标量 + 音乐参数映射
"""

import json
import sys
from pathlib import Path
from collections import Counter

import numpy as np
from PIL import Image

# ============================================================
# 可调阈值（集中管理，与 §4.1 一致）
# ============================================================
THRESHOLDS = {
    "tau_lab":       15,        # Lab a* "明显偏红/偏绿"阈值
    "tau_rg":        30,        # RGB R-G 备选阈值
    "sat_neutral":   0.08,      # 饱和度低于此视为无色相
    "val_low":       0.05,      # 明度过低视为无效
    "val_high":      0.97,      # 明度过高视为无效
    "hue_warm_cold": 60,        # 暖冷分界色相角 (°)
    "sat_low":       0.3,       # 饱和三档 - 低
    "sat_mid_high":  0.6,       # 饱和三档 - 中高分界
    "val_low_tone":  0.3,       # [legacy] HSV-V 音高 - 低
    "val_high_tone": 0.7,       # [legacy] HSV-V 音高 - 高
    # ---- 项目设计参数 (非文献给定): 感知明度 L* 的分档边界 ----
    # 与 mapping_rules 的连续音高公式对齐: anchor = C2(36) + 0.48*L*
    #   L*<25 → anchor<C3.5   L*25-75 → C3.5-C5   L*>75 → >C5
    "L_low":         25.0,
    "L_high":        75.0,
}

# ============================================================
# 色相扇区 → 音色映射（行 1-4）
# ============================================================
HUE_TO_TIMBRE = [
    ((0, 45),     "中音弦乐",         "红/橙"),
    ((330, 360),  "中音弦乐",         "红/橙"),
    ((45, 70),    "高音铜管(短笛/小号)", "黄"),
    ((70, 170),   "长笛/中音弦乐",      "绿"),
    ((170, 330),  "大提琴/巴松管/管风琴", "蓝/紫"),
]

# ============================================================
# 英文标签映射 (项目展示语言为英文)
#   内部计算仍用中文 key, 对外输出时统一转成英文
# ============================================================
EN_HUE_LABEL = {
    "红/橙": "red / orange",
    "黄": "yellow",
    "绿": "green",
    "蓝/紫": "blue / violet",
}

EN_TIMBRE = {
    "中音弦乐": "viola-led strings",
    "高音铜管(短笛/小号)": "high brass (piccolo / trumpet)",
    "长笛/中音弦乐": "flute and viola strings",
    "大提琴/巴松管/管风琴": "cello / bassoon / organ",
    "大提琴": "cello",
    "巴松管": "bassoon",
    "管风琴": "organ",
    "长笛": "flute",
    "小提琴": "violin",
    "铜管": "brass",
    "小号": "trumpet",
}

EN_MODE = {"大调": "major key", "小调": "minor key"}

EN_PITCH = {
    "C5–C7 (高音区)": "C5-C7 (high register)",
    "C2–C4 (低音区)": "C2-C4 (low register)",
    "C4–C5 (中音区)": "C4-C5 (mid register)",
}

EN_HARMONY_LEVEL = {"平静": "calm", "中紧张": "moderate tension", "高紧张": "high tension"}

EN_HARMONY_DESC = {
    "不协和音程（小二度/三全音）= 紧张":
        "dissonant intervals (minor second / tritone) = tense",
    "中度不协和": "moderately dissonant",
    "协和音程（纯五度/大三度）= 平静":
        "consonant intervals (perfect fifth / major third) = calm",
}

EN_EMOTION = {
    "兴奋 / 高唤醒": "excited / high arousal",
    "平静 / 低唤醒": "calm / low arousal",
    "中性 / 中等唤醒": "neutral / moderate arousal",
}


def _en_timbre(cn: str) -> str:
    """音色: 中文拼接串(用 / 分隔) → 英文
    注意: 键名本身含 '/' (如 '长笛/中音弦乐'), 必须先查整串再拆分"""
    cn = cn.strip()
    if cn in EN_TIMBRE:
        return EN_TIMBRE[cn]
    parts = [p.strip() for p in cn.split("/") if p.strip()]
    return " / ".join(EN_TIMBRE.get(p, p) for p in parts)


def load_and_preprocess(path: str, max_side: int = 512) -> np.ndarray:
    """读图 → 缩放 → RGB float [0,1]"""
    img = Image.open(path).convert("RGB")
    w, h = img.size
    if max(w, h) > max_side:
        scale = max_side / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    return np.array(img, dtype=np.float64) / 255.0


def rgb_to_hsv(rgb: np.ndarray) -> tuple:
    """RGB [H,W,3] → H/S/V 各 [H,W], H∈[0,360), S,V∈[0,1]"""
    from colorsys import rgb_to_hsv
    hsv = np.apply_along_axis(
        lambda px: rgb_to_hsv(px[0], px[1], px[2]), -1, rgb
    )
    H = hsv[..., 0] * 360.0   # 转角度
    S = hsv[..., 1]
    V = hsv[..., 2]
    return H, S, V


def rgb_to_lab(rgb: np.ndarray) -> tuple:
    """
    RGB [0,1] → Lab L*, a*, b*
    近似实现（D65 白点），a* ∈ [-100,100]，正=红，负=绿
    """
    # 线性化
    def linearize(c):
        c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
        return c

    r, g, b = linearize(rgb[..., 0]), linearize(rgb[..., 1]), linearize(rgb[..., 2])

    # RGB → XYZ (sRGB D65)
    X = r * 0.4124564 + g * 0.3575761 + b * 0.1804375
    Y = r * 0.2126729 + g * 0.7151522 + b * 0.0721750
    Z = r * 0.0193339 + g * 0.1191920 + b * 0.9503041

    # 参考白 D95
    Xn, Yn, Zn = 0.95047, 1.0, 1.08883

    def f(t):
        delta = 6.0 / 29.0
        return np.where(t > delta ** 3, t ** (1.0 / 3.0), t / (3 * delta ** 2) + 4.0 / 29.0)

    fx, fy, fz = f(X / Xn), f(Y / Yn), f(Z / Zn)

    L_star = 116.0 * fy - 16.0
    a_star = 500.0 * (fx - fy)
    b_star = 200.0 * (fy - fz)

    return L_star, a_star, b_star


def extract_color_metrics(rgb: np.ndarray) -> dict:
    """按 §4.1 公式提取全部颜色标量"""

    H, S, V = rgb_to_hsv(rgb)
    Ls, a_star, b_star = rgb_to_lab(rgb)

    th = THRESHOLDS

    # ---- 中性像素掩码 ----
    valid = (S >= th["sat_neutral"]) & (V >= th["val_low"]) & (V <= th["val_high"])
    N_valid = int(valid.sum())
    N_total = int(valid.size)

    # ---- 1-4 色相→音色 ----
    H_flat = H[valid].flatten()
    hue_bins = []
    for (lo, hi), timbre, label in HUE_TO_TIMBRE:
        if lo < hi:
            mask = (H_flat >= lo) & (H_flat < hi)
        else:  # 跨 0° 的区间如 [330,360)
            mask = (H_flat >= lo) | (H_flat < hi)
        count = int(mask.sum())
        hue_bins.append((label, timbre, count))

    # 合并同名牌区: (0,45) 与 (330,360) 都叫"红/橙", 必须累加而非覆盖
    hue_distribution = {}
    for _label, _timbre, _count in hue_bins:
        hue_distribution[_label] = hue_distribution.get(_label, 0) + _count

    dominant_label, dominant_timbre, _ = max(hue_bins, key=lambda x: x[2])

    # ---- 5-6 冷暖→调式 ----
    warm_mask = valid & (((H >= 0) & (H < th["hue_warm_cold"])) |
                          ((H >= 360 - th["hue_warm_cold"]) & (H < 360)))
    cold_mask = valid & (H >= th["hue_warm_cold"]) & (H < 360 - th["hue_warm_cold"])
    N_warm = int(warm_mask.sum())
    N_cold = int(cold_mask.sum())
    W = N_warm / N_valid if N_valid > 0 else 0.5
    mode_str = "大调" if W > 0.5 else "小调"

    # ---- 7-9 饱和→节奏 ----
    S_valid = S[valid]
    S_mean = float(S_valid.mean()) if N_valid > 0 else 0.0
    if S_mean > th["sat_mid_high"]:
        tempo_range = "BPM 100–130"
        dynamics = "f"
    elif S_mean >= th["sat_low"]:
        tempo_range = "BPM 70–100"
        dynamics = "mf"
    else:
        tempo_range = "BPM 50–70"
        dynamics = "p"

    # ---- 10-11 明度 → 音高 ----
    # 【2026-10 修订】改用感知明度 CIELAB L*，不再用 HSV-V。
    #   L* 与视觉明度是线性对应的；HSV-V 在饱和色上会高估亮度(旧版最大偏差 19.2 点)。
    #   分档边界 L*/40/65 是项目设计参数，不是文献给定的公式。
    V_valid = V[valid]
    V_mean = float(V_valid.mean()) if N_valid > 0 else 0.5

    L_valid = Ls[valid]
    L_mean = float(L_valid.mean()) if N_valid > 0 else 50.0
    L_med = float(np.median(L_valid)) if N_valid > 0 else 50.0
    L_p05 = float(np.percentile(L_valid, 5)) if N_valid > 0 else 50.0
    L_p95 = float(np.percentile(L_valid, 95)) if N_valid > 0 else 50.0

    if L_mean > th["L_high"]:
        pitch_range = "C5–C7 (高音区)"
    elif L_mean < th["L_low"]:
        pitch_range = "C2–C4 (低音区)"
    else:
        pitch_range = "C4–C5 (中音区)"

    # legacy: 旧版 HSV-V 分档, 保留用于对照与论文里的"修正前/后"比较
    if V_mean > th["val_high_tone"]:
        pitch_range_hsv = "C5–C7 (高音区)"
    elif V_mean < th["val_low_tone"]:
        pitch_range_hsv = "C2–C4 (低音区)"
    else:
        pitch_range_hsv = "C4–C5 (中音区)"

    # ---- ⭐ 红绿对比指数 RGI（核心）----
    tau = th["tau_lab"]
    a_valid = a_star[valid]

    red_pixels = a_valid > tau
    green_pixels = a_valid < -tau

    redW = float(a_valid[red_pixels].sum()) / N_valid if N_valid > 0 else 0.0
    greenW = float((-a_valid[green_pixels]).sum()) / N_valid if N_valid > 0 else 0.0

    # vivid: 红或绿像素的平均饱和度
    rg_mask = red_pixels | green_pixels
    vivid = float(S_valid[rg_mask].mean()) if rg_mask.sum() > 0 else 0.0

    RGI = 2.0 * min(redW, greenW) * (1.0 + vivid)

    # RGI 判定（暂用相对描述，需校准后给 T_high/T_low）
    if RGI > 10:
        harmony_desc = "不协和音程（小二度/三全音）= 紧张"
        harmony_level = "高紧张"
    elif RGI > 3:
        harmony_desc = "中度不协和"
        harmony_level = "中紧张"
    else:
        harmony_desc = "协和音程（纯五度/大三度）= 平静"
        harmony_level = "平静"

    # ---- 14-15 冷暖→情绪 ----
    if W > 0.6:
        emotion = "兴奋 / 高唤醒"
    elif (1.0 - W) > 0.6:
        emotion = "平静 / 低唤醒"
    else:
        emotion = "中性 / 中等唤醒"

    # ---- RGB 备选方案 R-G ----
    rg_diff = rgb[..., 0] - rgb[..., 1]  # R−G ∈ [-1, 1]
    rg_valid = rg_diff[valid]
    redW_rg = float(rg_valid[rg_valid > th["tau_rg"] / 255.0].sum()) / N_valid if N_valid > 0 else 0.0
    greenW_rg = float((-rg_valid[rg_valid < -th["tau_rg"] / 255.0]).sum()) / N_valid if N_valid > 0 else 0.0
    RGI_rg = 2.0 * min(redW_rg, greenW_rg) * (1.0 + vivid)

    return {
        "image_info": {
            "total_pixels": N_total,
            "valid_color_pixels": N_valid,
            "neutral_excluded_pct": round((1 - N_valid / N_total) * 100, 1) if N_total > 0 else 0,
        },
        "dominant_hue": {
            "label": dominant_label,
            "timbre": dominant_timbre,
            "label_en": EN_HUE_LABEL.get(dominant_label, dominant_label),
            "timbre_en": _en_timbre(dominant_timbre),
            "hue_distribution": hue_distribution,
            "hue_distribution_en": {EN_HUE_LABEL.get(k, k): v
                                    for k, v in hue_distribution.items()},
        },
        "warm_cold": {
            "warm_ratio_W": round(W, 4),
            "N_warm": N_warm,
            "N_cold": N_cold,
            "mode": mode_str,
            "mode_en": EN_MODE.get(mode_str, mode_str),
        },
        "saturation": {
            "metric": "HSV_S",
            "metric_note": "HSV 饱和度 S（非 CIELAB chroma C*），论文中需如此标注",
            "mean_S": round(S_mean, 4),
            "tempo_range": tempo_range,
            "tempo_range_note": "legacy: 由饱和度推 BPM 属项目设计选择，非文献映射",
            "dynamics": dynamics,
        },
        "brightness": {
            "metric": "CIELAB_L*",
            "mean_L": round(L_mean, 2),
            "median_L": round(L_med, 2),
            "L_p05": round(L_p05, 2),
            "L_p95": round(L_p95, 2),
            "mean_V": round(V_mean, 4),
            "mean_V_note": "HSV-V，非感知明度，仅保留作对照",
            "pitch_range": pitch_range,
            "pitch_range_en": EN_PITCH.get(pitch_range, pitch_range),
            "pitch_range_hsv": pitch_range_hsv,
            "pitch_range_hsv_en": EN_PITCH.get(pitch_range_hsv, pitch_range_hsv),
            "thresholds": {"L_low": th["L_low"], "L_high": th["L_high"]},
            "thresholds_note": "分档边界为项目设计参数",
        },
        "red_green_index": {
            "RGI_lab": round(RGI, 4),
            "redW": round(redW, 4),
            "greenW": round(greenW, 4),
            "vivid_sat_of_RG": round(vivid, 4),
            "RGI_rgb_alt": round(RGI_rg, 4),
            "harmony_description": harmony_desc,
            "harmony_level": harmony_level,
            "harmony_description_en": EN_HARMONY_DESC.get(harmony_desc, harmony_desc),
            "harmony_level_en": EN_HARMONY_LEVEL.get(harmony_level, harmony_level),
            "note": "RGI thresholds (T_high/T_low) pending calibration; empirical values in use",
            "status": "not_evidence",
            "status_note": "红绿对比→不协和和声没有直接的颜色-声音实验证据；仅作项目设计选择，"
                           "不进入'有文献支持的映射'清单（需求书 §2 已要求降级）",
        },
        "emotion": {
            "description": emotion,
            "description_en": EN_EMOTION.get(emotion, emotion),
            "warm_ratio_W": round(W, 4),
        },
    }


def print_report(metrics: dict, image_name: str):
    """输出人类可读报告"""
    sep = "=" * 55
    print(f"\n{sep}")
    print(f"  🎨 颜色分析报告：{image_name}")
    print(sep)

    info = metrics["image_info"]
    print(f"\n📐 像素统计")
    print(f"   总像素：{info['total_pixels']:,}")
    print(f"   有效彩色像素：{info['valid_color_pixels']:,} ({100-info['neutral_excluded_pct']:.1f}%)")
    print(f"   中性像素剔除：{info['neutral_excluded_pct']}%")

    dh = metrics["dominant_hue"]
    print(f"\n🎨 主导色相 → 音色")
    print(f"   主导：{dh['label']} → {dh['timbre']}")
    print(f"   色相分布：")
    for label, cnt in dh["hue_distribution"].items():
        bar = "█" * (cnt // 200)
        print(f"     {label:>6}：{cnt:>6,} 像素  {bar}")

    wc = metrics["warm_cold"]
    print(f"\n🌡️ 冷暖 → 调式")
    print(f"   暖色占比 W = {wc['warm_ratio_W']:.1%}  （暖{wc['N_warm']:,} / 冷{wc['N_cold']:,}）")
    print(f"   → {wc['mode']}")

    sat = metrics["saturation"]
    print(f"\n💫 饱和度 → 节奏/力度")
    print(f"   平均饱和 S̄ = {sat['mean_S']:.4f}")
    print(f"   → {sat['tempo_range']} / {sat['dynamics']}")

    br = metrics["brightness"]
    print(f"\n☀️ 明度 → 音高区")
    print(f"   平均明度 V̄ = {br['mean_V']:.4f}")
    print(f"   → {br['pitch_range']}")

    rg = metrics["red_green_index"]
    print(f"\n⭐ 红绿对比指数 RGI（核心创新）")
    print(f"   RGI (Lab a*)  = {rg['RGI_lab']:.4f}")
    print(f"   RGI (RGB备选) = {rg['RGI_rgb_alt']:.4f}")
    print(f"   redW = {rg['redW']:.4f}, greenW = {rg['greenW']:.4f}")
    print(f"   红/绿像素平均饱和 vivid = {rg['vivid_sat_of_RG']:.4f}")
    print(f"   → {rg['harmony_description']} [{rg['harmony_level']}]")
    print(f"   ⚠️ {rg['note']}")

    em = metrics["emotion"]
    print(f"\n😶‍🌫️ 整体情绪")
    print(f"   → {em['description']}")

    print(f"\n{sep}")
    print("  🎵 音乐参数汇总")
    print(sep)
    print(f"   音色：{dh['timbre']}")
    print(f"   调式：{wc['mode']}")
    print(f"   节奏：{sat['tempo_range']} / {sat['dynamics']}")
    print(f"   音高：{br['pitch_range']}")
    print(f"   和声：{rg['harmony_description']}")
    print(f"   情绪：{em['description']}")
    print(sep)


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "artworks" / "Paul Gauguin-Manao tupapau.jpeg"
    if not path.exists():
        print(f"文件不存在：{path}", file=sys.stderr)
        sys.exit(1)

    print(f"正在分析：{path.name}")
    rgb = load_and_preprocess(str(path))
    print(f"图像尺寸：{rgb.shape[1]}×{rgb.shape[0]}")

    metrics = extract_color_metrics(rgb)
    print_report(metrics, path.name)

    # 同时保存 JSON 方便后续代码消费
    out = Path(__file__).parent / "color_output_gauguin.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
    print(f"\n💾 JSON 已保存：{out}")

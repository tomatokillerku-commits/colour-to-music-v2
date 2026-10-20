#!/usr/bin/env python3
"""
saliency.py — OpenCV 显著性检测与局部颜色提取（需求书 P1-1 / P1-2）

做什么
------
1. 用 OpenCV contrib 的 StaticSaliencyFineGrained 生成显著性热图
   （FG 适合绘画这类非自然图像；失败时回退 SpectralResidual）。
2. 取显著性最高的 top 12% 像素做阈值 → 形态学清理 → 连通域 → 最多 4 个区域。
3. 每个区域测：面积占比、外接框、平均 CIELAB L*、平均 HSV S、主导色相。

不做什么（重要）
----------------
「视觉显著」≠「艺术/语义重要」。本模块只输出统计量，不判断哪块区域更重要。
局部颜色进入映射时沿用同样的三条规则（L*→音高、S→响度、L*→音色明亮度），
每个区域作为一条独立的辅助声部，**不做自动加权**（权重机制属于未来展望）。
"""

import os

import cv2
import numpy as np

import color_extractor as CE

# ── 设计参数（非文献给定） ────────────────────────────────────────────────────
TOP_FRAC = 0.12        # 取显著性最高的 12% 像素
MIN_AREA_FRAC = 0.003  # 区域至少占画面 0.3%
MAX_REGIONS = 4
HEAT_ALPHA = 0.55      # 热图与原图的混合比例
# 预平滑: FineGrained 是像素级对比度模型, 在厚涂笔触上会把纹理当成显著。
# 先按 sigma = 边长/60 平滑, 再去算, 得到的是"结构级"显著而不是笔触噪声。
PRESMOOTH_DIV = 60.0
WORK_SIDE = 640        # 工作分辨率（够用且快）


def _imread_unicode(path: str):
    """cv2.imread 在 Windows 上读不了中文/特殊字符路径, 必须 imdecode"""
    data = np.fromfile(path, dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def _imwrite_unicode(path: str, img) -> bool:
    ext = os.path.splitext(path)[1] or ".png"
    ok, buf = cv2.imencode(ext, img)
    if not ok:
        return False
    with open(path, "wb") as f:
        f.write(buf.tobytes())
    return True


def _saliency_map(bgr) -> tuple:
    """结构级显著图: FineGrained(预平滑) 为主, SpectralResidual 作交叉校验

    返回 (0..1 显著图, 算法名, 与 SR 的相关系数)
    """
    algo = "StaticSaliencyFineGrained (pre-smoothed)"
    sigma = max(bgr.shape) / PRESMOOTH_DIV
    smooth = cv2.GaussianBlur(bgr, (0, 0), sigmaX=max(1.0, sigma))

    try:
        s = cv2.saliency.StaticSaliencyFineGrained_create()
        ok, m = s.computeSaliency(smooth)
        if not ok:
            raise RuntimeError("fine-grained returned False")
    except Exception:
        algo = "StaticSaliencySpectralResidual"
        s2 = cv2.saliency.StaticSaliencySpectralResidual_create()
        ok, m = s2.computeSaliency(bgr)
        if not ok:
            raise RuntimeError("saliency failed")
        m = m.astype(np.float32)
        return _norm(_norm(m)), algo, 1.0

    m = _norm(m.astype(np.float32))
    m = _norm(_norm(cv2.GaussianBlur(m, (0, 0), sigmaX=3)))

    # 交叉校验: 与 SR 的一致程度（低 = 两种假设对"哪里显著"分歧大）
    agree = 0.0
    try:
        sr = cv2.saliency.StaticSaliencySpectralResidual_create()
        ok2, m2 = sr.computeSaliency(bgr)
        if ok2:
            m2 = _norm(m2.astype(np.float32))
            a, b = m.ravel(), m2.ravel()
            if a.std() > 0 and b.std() > 0:
                agree = round(float(np.corrcoef(a, b)[0, 1]), 3)
    except Exception:
        pass

    return m, algo, agree


def _norm(m):
    """归一到 0..1"""
    lo, hi = float(m.min()), float(m.max())
    if hi > lo:
        return (m - lo) / (hi - lo)
    return np.zeros_like(m)


def _dominant_hue_label(h_deg: np.ndarray, w: np.ndarray) -> tuple:
    """按 color_extractor 的扇区定义取主导色相标签"""
    acc = {}
    for (lo, hi), _timbre, label in CE.HUE_TO_TIMBRE:
        if lo < hi:
            mask = (h_deg >= lo) & (h_deg < hi)
        else:
            mask = (h_deg >= lo) | (h_deg < hi)
        acc[label] = acc.get(label, 0.0) + float(w[mask].sum())
    if not acc:
        return "", 0.0
    label = max(acc, key=acc.get)
    return label, acc[label]


def analyze(path: str, heat_out: str = None, focus_out: str = None,
            group_l: float = None, group_s: float = None,
            max_side: int = WORK_SIDE) -> dict:
    """主入口: 图片路径 -> 显著性统计 + 区域列表 (+ 热图 / 焦点蒙版)

    group_l / group_s: 全图的 L* 与 HSV S（由调用方的颜色测量传入，
    保证这里的"ΔL*"和 02 Colour 面板显示的是同一个基准）。
    """
    bgr = _imread_unicode(path)
    if bgr is None:
        raise RuntimeError(f"cannot read image: {path}")

    h0, w0 = bgr.shape[:2]
    if max(h0, w0) > max_side:
        scale = max_side / max(h0, w0)
        bgr = cv2.resize(bgr, (int(w0 * scale), int(h0 * scale)), interpolation=cv2.INTER_AREA)

    sal, algo, agree = _saliency_map(bgr)

    # 颜色统计（一次算全图, 再按掩码取子集）
    rgb = np.clip(bgr[:, :, ::-1].astype(np.float64) / 255.0, 0, 1)   # BGR->RGB
    L_all, a_all, b_all = CE.rgb_to_lab(rgb)
    H_all, S_all, V_all = CE.rgb_to_hsv(rgb)

    # 全图基准（优先用调用方传进来的颜色测量值，保证与 02 面板一致）
    gL = float(group_l) if group_l is not None else float(L_all.mean())
    gS = float(group_s) if group_s is not None else float(S_all.mean())
    img_sal_mean = float(sal.mean()) or 1e-6

    # ---- 阈值 + 形态学 + 连通域 ----
    thr = float(np.percentile(sal, 100.0 * (1.0 - TOP_FRAC)))
    mask = (sal >= thr).astype(np.uint8)
    k3 = np.ones((3, 3), np.uint8)
    k7 = np.ones((7, 7), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k3)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k7)

    n, labels, stats, cents = cv2.connectedComponentsWithStats(mask, connectivity=8)
    min_area = MIN_AREA_FRAC * labels.size

    regions = []
    for i in range(1, n):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area < min_area:
            continue
        x, y, bw, bh = (int(stats[i, cv2.CC_STAT_LEFT]), int(stats[i, cv2.CC_STAT_TOP]),
                        int(stats[i, cv2.CC_STAT_WIDTH]), int(stats[i, cv2.CC_STAT_HEIGHT]))
        sel = labels == i
        L = float(L_all[sel].mean())
        S = float(S_all[sel].mean())
        V = float(V_all[sel].mean())
        hue_lbl, hue_w = _dominant_hue_label(H_all[sel], np.ones(int(sel.sum())))
        mean_rgb = (rgb[sel].mean(axis=0) * 255).round().astype(int).tolist()
        sal_mean = float(sal[sel].mean())
        # 局部值 vs 全图：回答"这块和整体有什么不同"，绝对数值没有信息量
        dL = L - gL
        dS = S - gS
        anchor = 36.0 + (max(0.0, min(100.0, L)) / 100.0) * 48.0
        try:
            from mapping_rules import pitch_to_note
            vnote = pitch_to_note(anchor)
        except Exception:
            vnote = ""
        regions.append({
            "id": len(regions) + 1,
            "area_pct": round(100.0 * area / labels.size, 2),
            "bbox": {"x": x, "y": y, "w": bw, "h": bh},
            "centroid": {"x": round(float(cents[i][0]), 1), "y": round(float(cents[i][1]), 1)},
            "mean_saliency": round(sal_mean, 3),
            # 这块的显著度相对全图均值（2.2 = 2.2 倍）
            "saliency_ratio": round(sal_mean / img_sal_mean, 2),
            "rank_score": round(sal_mean * (0.5 + S), 3),
            "mean_L": round(L, 2),
            "mean_S": round(S, 3),
            "mean_V": round(V, 3),
            "delta_L": round(dL, 1),
            "delta_S": round(dS, 2),
            "dominant_hue": hue_lbl,
            "mean_rgb": mean_rgb,
            "hex": "#%02X%02X%02X" % tuple(mean_rgb),
            # 这个区域在 06 基础声音里对应的辅助声部
            "voice_midi": round(anchor, 1),
            "voice_note": vnote,
            # 内部用: 连通域编号, 用于生成焦点蒙版（不对外输出）
            "_labels": [i],
        })

    # 排序: 显著且饱和的区域优先（rank_score 是设计参数, 见 notes）
    regions.sort(key=lambda r: r["rank_score"], reverse=True)
    regions = regions[:MAX_REGIONS]

    # 合并同一处色域的碎片（音高相近 且 质心接近），否则一个蓝色区域会插好几根钉
    merged = []
    diag = float(np.hypot(bgr.shape[1], bgr.shape[0]))
    for r in regions:
        same = None
        for m_ in merged:
            dn = abs(m_["voice_midi"] - r["voice_midi"])
            dc = float(np.hypot(m_["centroid"]["x"] - r["centroid"]["x"],
                                m_["centroid"]["y"] - r["centroid"]["y"]))
            if dn < 0.6 or (dn < 1.5 and dc < 0.18 * diag):
                same = m_
                break
        if same:
            same["area_pct"] = round(same["area_pct"] + r["area_pct"], 2)
            same["merged_count"] = same.get("merged_count", 1) + 1
            same["_labels"].extend(r["_labels"])
        else:
            r["merged_count"] = 1
            merged.append(r)
    regions = merged
    for idx, r in enumerate(regions, 1):
        r["id"] = idx

    heat_url = None
    if heat_out:
        hm = cv2.applyColorMap((sal * 255).astype(np.uint8), cv2.COLORMAP_JET)
        blend = cv2.addWeighted(bgr, 1.0 - HEAT_ALPHA, hm, HEAT_ALPHA, 0)
        for r in regions:   # 框出区域, 便于核对
            bb = r["bbox"]
            cv2.rectangle(blend, (bb["x"], bb["y"]),
                          (bb["x"] + bb["w"], bb["y"] + bb["h"]), (255, 255, 255), 2)
        if _imwrite_unicode(heat_out, blend):
            heat_url = heat_out

    # ── 焦点蒙版: 非显著区压暗 + 编号钉 ──────────────────────────────────
    # 不用彩虹热图: JET 会往画面里再加一层颜色，对"色彩—音乐"这个题目是反效果，
    # 而且对色觉异常者不友好。压暗只改亮度，画面本身不动。
    focus_url = None
    if focus_out:
        # 只保留最终选中的区域亮着, 其余压暗；比"top 12% 散点"干净得多
        keep = np.isin(labels, [li for r in regions for li in r["_labels"]])
        m = keep.astype(np.float32)
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        m = cv2.GaussianBlur(m, (0, 0), sigmaX=14)
        m3 = np.clip(m, 0, 1)[..., None]
        focus = (bgr.astype(np.float32) * (0.34 + 0.66 * m3)).clip(0, 255).astype(np.uint8)
        for r in regions:
            c = (int(r["centroid"]["x"]), int(r["centroid"]["y"]))
            cv2.circle(focus, c, 14, (18, 18, 18), -1, lineType=cv2.LINE_AA)
            cv2.circle(focus, c, 14, (245, 245, 245), 1, lineType=cv2.LINE_AA)
            txt = str(r["id"])
            (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.putText(focus, txt, (c[0] - tw // 2, c[1] + th // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (245, 245, 245), 1, cv2.LINE_AA)
        if _imwrite_unicode(focus_out, focus):
            focus_url = focus_out

    # ── 结论所需的统计（前端据此组一句话，而不是罗列参数） ──────────────
    for r in regions:                      # 内部字段不对外
        r.pop("_labels", None)
    area_total = round(sum(r["area_pct"] for r in regions), 2)
    ratio_mean = round(sum(r["saliency_ratio"] for r in regions) / len(regions), 2) if regions else 0
    brightest = max(regions, key=lambda r: r["delta_L"]) if regions else None
    darkest = min(regions, key=lambda r: r["delta_L"]) if regions else None
    most_sat = max(regions, key=lambda r: r["delta_S"]) if regions else None

    summary = {
        "n_regions": len(regions),
        "area_total_pct": area_total,
        "saliency_ratio_mean": ratio_mean,
        "group_L": round(gL, 2),
        "group_S": round(gS, 3),
        "brightest": {"id": brightest["id"], "delta_L": brightest["delta_L"]} if brightest else None,
        "darkest": {"id": darkest["id"], "delta_L": darkest["delta_L"]} if darkest else None,
        "most_saturated": {"id": most_sat["id"], "delta_S": most_sat["delta_S"]} if most_sat else None,
    }

    return {
        "algorithm": algo,
        "agreement_with_SR": agree,
        "presmooth_sigma_div": PRESMOOTH_DIV,
        "top_frac": TOP_FRAC,
        "threshold": round(thr, 4),
        "mean_saliency": round(float(sal.mean()), 4),
        "size": {"w": int(bgr.shape[1]), "h": int(bgr.shape[0])},
        "regions": regions,
        "summary": summary,
        "heat_file": heat_url,
        "focus_file": focus_url,
        "notes": [
            "视觉显著 ≠ 艺术/语义重要（需求书 P1-1）",
            f"top {int(TOP_FRAC*100)}% 阈值、最小面积 0.3%、最多 {MAX_REGIONS} 个区域、rank_score 权重均为设计参数",
            "预平滑(sigma=边长/60)用于抑制厚涂笔触纹理，属实现细节",
            "OpenCV 的 FG/SR 算法不是 Itti-Koch-Niebur (1998) 的原实现，引用时不得等同 [R5]",
        ],
    }


if __name__ == "__main__":
    import sys
    import json
    from pathlib import Path
    from datetime import datetime

    p = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).parent / "artworks" / "赵无极-20-03-60.jpeg")
    out = Path(__file__).parent / "outputs" / "saliency"
    out.mkdir(parents=True, exist_ok=True)
    r = analyze(p, str(out / "demo_heat.png"), str(out / "demo_focus.png"))
    print(f"{Path(p).name}: {r['algorithm']}  {r['size']['w']}x{r['size']['h']}  "
          f"regions={len(r['regions'])}  heat={r['heat_file']}  focus={r['focus_file']}")
    print("summary:", __import__("json").dumps(r["summary"], ensure_ascii=False))
    print(__import__("json").dumps(r["regions"], ensure_ascii=False, indent=2)[:900])

"""输入范围闸门：系统对哪一类画负责，超出的画明确拒绝，而不是硬给结果。

设计原则
- 用可测量的量，不用风格标签。风格标签要靠语料分类器，而十幅画撑不起分类器；
  但"这幅画有没有可读的明度结构"是能当场算出来的。
- 区间来自十幅参考画的实测边界（见 gallery.json + 本文件注释），并去掉几何图这一端：
  Vega 200 的 edge=63.7 是已知的失败案例（映射没有空间频率轴），把它排除在支持范围外，
  这样"我们能做什么"和"我们证明了做不到什么"是一致的。
- 只读一次 320px 缩略图，纯 numpy/opencv，无模型、无网络。
"""

import numpy as np
import cv2

# 十幅参考画实测（320px 缩图）：aspect 0.62–1.57 / mean_L 29.0–77.3 / sd_L 11.8–28.0
# mean_S 0.26–0.69 / sd_S 0.12–0.39 / edge 5.4–63.7 / sd_col 2.2–11.7
ENVELOPE = {
    "aspect":  (0.55, 1.65, "长宽比超出支持范围（太窄或太宽的条幅）", "换一张接近方形的画"),
    "mean_L":  (20.0, 88.0, "整体太暗或太亮，明度几乎是一条平线", "换一张明暗有分布的画"),
    "sd_L":    (9.0, 40.0, "对比度太低：全画明度几乎相同，音高会是常数", "换一张有明确明暗层次的作品"),
    "mean_S":  (0.10, 0.85, "几乎无彩或饱和度溢出", "换一张有可见色彩的作品"),
    "edge":    (3.0, 55.0, "表面太干净（矢量/渲染）或过于几何——映射没有空间频率轴", "换一张笔触可见的绘画"),
    "sd_col":  (1.5, 20.0, "左右几乎没有变化，扫掠线听不出任何走向", "换一张横向有构图的画"),
}

MIN_SIDE = 400          # 参考画本身是 410–800px 的副本；低于 400px 时取样点半径 < 10px，提示会失真
WORK_W = 320


def _read(path):
    data = np.fromfile(path, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"cannot decode image: {path}")
    return img


def metrics(path):
    bgr = _read(path)
    h, w = bgr.shape[:2]
    sm = cv2.resize(bgr, (WORK_W, max(1, int(h * WORK_W / w))), interpolation=cv2.INTER_AREA)
    rgb01 = np.clip(sm[:, :, ::-1].astype(np.float32) / 255.0, 0, 1)
    L = cv2.cvtColor(rgb01, cv2.COLOR_RGB2LAB)[:, :, 0]
    S = cv2.cvtColor(rgb01, cv2.COLOR_RGB2HSV)[:, :, 1]
    e = (np.abs(cv2.Sobel(L, cv2.CV_32F, 1, 0, ksize=3))
         + np.abs(cv2.Sobel(L, cv2.CV_32F, 0, 1, ksize=3)))
    col = L.mean(axis=0)                    # 每列明度均值 → 横向结构强度
    return {
        "width": int(w), "height": int(h), "min_side": int(min(w, h)),
        "aspect": float(w / h),
        "mean_L": float(L.mean()), "sd_L": float(L.std()),
        "mean_S": float(S.mean()), "sd_S": float(S.std()),
        "edge": float(e.mean()), "sd_col": float(col.std()),
    }


def evaluate(path):
    m = metrics(path)
    checks = []
    for key, (lo, hi, why, fix) in ENVELOPE.items():
        v = m[key]
        ok = lo <= v <= hi
        checks.append({
            "key": key, "value": round(float(v), 2), "min": lo, "max": hi,
            "ok": bool(ok), "why": why, "fix": fix,
        })
    if m["min_side"] < MIN_SIDE:
        checks.append({
            "key": "min_side", "value": m["min_side"], "min": MIN_SIDE, "max": None,
            "ok": False,
            "why": f"分辨率不足（短边 {m['min_side']}px，需要 ≥ {MIN_SIDE}px）",
            "fix": "上传原图，不要上传缩略图",
        })
    failures = [c for c in checks if not c["ok"]]
    return {
        "ok": not failures,
        "verdict": "in range" if not failures else "out of range",
        "metrics": {k: round(v, 2) for k, v in m.items()},
        "checks": checks,
        "failures": failures,
    }


if __name__ == "__main__":
    import json
    import sys
    for p in sys.argv[1:]:
        r = evaluate(p)
        print(p, r["verdict"], [f["key"] for f in r["failures"]])

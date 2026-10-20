#!/usr/bin/env python3
"""
artwork_match.py — 用 OpenCV 感知哈希把上传图对到已有作品（P0 级可靠性修复）

为什么需要
----------
Gemini 的作品识别不稳定：同一幅赵无极《20.03.60》连续四次调用，四次给出
22.07.64 / 自编标题 / 20.03.60 / 24.11.68 —— 只有一次正确。抽象画尤其容易认错，
因为同一艺术家的作品在构图上高度相似。

对策：先用感知哈希做确定性的图像匹配，命中就直接采用 gallery.json 的权威元数据；
没命中才交给 AI 识别（此时 AI 只是给"未知作品"起个描述性标题）。

用 AverageHash（8×8 灰度均值）而不是文件 sha256：上传图会被重编码成 JPEG、
可能被缩放，精确哈希对不上，但平均哈希在轻微重编码/缩放后距离仍然很小。
"""

import cv2
import numpy as np

from saliency import _imread_unicode   # 复用中文路径安全的读取

# 汉明距离阈值：0–6 视为同一幅（64 bit 中最多差 6 bit）
MAX_HAMMING = 6


def _avg_hash(bgr) -> np.ndarray:
    h = cv2.img_hash.AverageHash_create().compute(bgr)
    return h          # shape (1, 8) uint8 → 64 bit


def _hamming(a: np.ndarray, b: np.ndarray) -> int:
    return int(cv2.norm(a, b, cv2.NORM_HAMMING))


def build_index(gallery: list, img_dir) -> list:
    """为 gallery.json 里的每幅画算一次哈希（进程启动时调用一次即可）"""
    idx = []
    for g in gallery:
        p = img_dir / g.get("file", "")
        if not p.exists():
            continue
        bgr = _imread_unicode(str(p))
        if bgr is None:
            continue
        small = cv2.resize(bgr, (256, 256), interpolation=cv2.INTER_AREA)
        idx.append({"meta": g, "hash": _avg_hash(small)})
    return idx


def match(bgr, index: list, max_hamming: int = MAX_HAMMING):
    """返回 (gallery_entry, distance) 或 (None, None)。

    bgr 需是与索引同尺寸(256×256)的 BGR 图。
    """
    if not index or bgr is None:
        return None, None
    h = _avg_hash(bgr)
    best, best_d = None, 999
    for item in index:
        d = _hamming(h, item["hash"])
        if d < best_d:
            best, best_d = item, d
    if best is not None and best_d <= max_hamming:
        return best["meta"], best_d
    return None, best_d


def hash_bgr(bgr):
    """对外暴露：256×256 归一化后求哈希"""
    if bgr is None:
        return None
    return _avg_hash(cv2.resize(bgr, (256, 256), interpolation=cv2.INTER_AREA))


if __name__ == "__main__":
    import sys
    from pathlib import Path

    base = Path(__file__).parent
    gal = __import__("json").loads((base / "gallery.json").read_text(encoding="utf-8"))
    idx = build_index(gal, base / "artworks")
    print(f"index: {len(idx)} artworks")

    # 自测: 原图、缩放图、重压缩图三种情况
    for name in ("赵无极-20-03-60.jpeg", "Georgia O'Keeffe-Music, Pink and Blue No. 2.jpg"):
        p = base / "artworks" / name
        bgr = _imread_unicode(str(p))
        small = cv2.resize(bgr, (256, 256), interpolation=cv2.INTER_AREA)
        m, d = match(small, idx)
        print(f"{name[:28]:30s} → {m['title'] if m else 'NO MATCH'} (d={d})")

        for q, side in ((80, 400), (60, 1000)):
            ok, buf = cv2.imencode(".jpg", cv2.resize(bgr, (side, int(side * bgr.shape[0] / bgr.shape[1]))),
                                   [cv2.IMWRITE_JPEG_QUALITY, q])
            re = cv2.imdecode(buf, cv2.IMREAD_COLOR)
            m2, d2 = match(cv2.resize(re, (256, 256), interpolation=cv2.INTER_AREA), idx)
            print(f"   recompressed q={q} side={side} → {m2['title'] if m2 else 'NO MATCH'} (d={d2})")

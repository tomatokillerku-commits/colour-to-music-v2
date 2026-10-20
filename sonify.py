#!/usr/bin/env python3
"""
sonify.py — 扫描式图像声化：让声音跟着画面走

为什么需要重写
--------------
原来的基础声音只有三个标量（音高锚点、响度、频谱重心）+ 一段固定旋律轮廓
`[0,2,3,5,3,2,0,-2,0,0]`。十幅画里只有 8 个不同的音名，两幅画可能只差 0.1 个半音。
那不是"把画变成声音"，那是"给同一段音乐换三个参数"。

这里的做法不一样：**画面本身决定声音的时间与空间结构**。

  x 轴  → 时间    从左扫到右，画被"读"一遍（这是设计选择 D5，不是实验结论）
  y 轴  → 音区    上面的东西高，下面的东西低（空间→音高的直觉映射）
  色块  → 声部    一次 k-means 分割 = 一批声部，各自在自己的 x 区间进入
  面积  → 时长    大色块持续得久，小块一闪而过
  饱和度→ 力度    这一条沿用 R2
  明度  → 音色    这一条沿用 R3
  边缘度→ 起音    边界硬的地方是短促的击发，柔的地方是慢慢涨起来

它仍然是可审计的：哪一条来自实验（R2/R3）、哪一条是设计（空间→时间、空间→音区），
在这里分开写清楚。但它第一次让"这幅画"在声音里可辨认 —— 因为信息量不再只有三个数。
"""

from pathlib import Path

import cv2
import numpy as np

from synth import (SR, TARGET_PEAK, _centroid_ratio, _solve_p, _tone,
                   _write_wav, midi_to_hz)

WORK_W = 320                # 分析宽度（够用，快）
K_REGIONS = 7               # 色块数量
MIN_NOTE_S = 0.9


# ── 1. 把画面拆成"事件" ─────────────────────────────────────────────────────

def analyze_structure(image_path: str, k: int = K_REGIONS) -> dict:
    data = np.fromfile(image_path, dtype=np.uint8)
    bgr = cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None
    if bgr is None:
        raise RuntimeError(f"cannot read image: {image_path}")

    h, w = bgr.shape[:2]
    scale = WORK_W / float(w)
    small = cv2.resize(bgr, (WORK_W, max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
    rgb01 = np.clip(small[:, :, ::-1].astype(np.float32) / 255.0, 0, 1)
    lab = cv2.cvtColor(rgb01, cv2.COLOR_RGB2LAB)          # L 0..100, a/b ±128
    hsv = cv2.cvtColor(rgb01, cv2.COLOR_RGB2HSV)          # H 0..360, S 0..1
    lum = lab[:, :, 0]

    samples = lab.reshape(-1, 3).astype(np.float32)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.8)
    _, labels, centers = cv2.kmeans(
        samples, k, None, crit, 3, cv2.KMEANS_PP_CENTERS
    )
    labels = labels.reshape(lum.shape)

    edges = cv2.Sobel(lum, cv2.CV_32F, 1, 0, ksize=3)
    edges += cv2.Sobel(lum, cv2.CV_32F, 0, 1, ksize=3)
    edge_mag = np.abs(edges)
    edge_norm = edge_mag / (np.percentile(edge_mag, 99) + 1e-6)

    H, W = labels.shape
    regions = []
    for i in range(k):
        m = labels == i
        area = float(m.mean())
        if area < 0.004:
            continue
        ys, xs = np.nonzero(m)
        cx = float(xs.mean()) / W
        cy = float(ys.mean()) / H
        spread = float(np.sqrt(((xs / W - cx) ** 2).mean()))
        L = float(lum[m].mean())
        S = float(hsv[:, :, 1][m].mean())
        edge = float(edge_norm[m].mean())
        # 色块在 x 上的左右边界 → 它在扫描里的进入/离开时间
        x0 = float(xs.min()) / W
        x1 = float(xs.max()) / W
        regions.append({
            "id": len(regions) + 1,
            "area": round(area, 3),
            "x": round(cx, 3),
            "y": round(cy, 3),
            "x0": round(x0, 3),
            "x1": round(x1, 3),
            "spread": round(spread, 3),
            "L": round(L, 1),
            "S": round(S, 3),
            "edge": round(edge, 3),
        })

    regions.sort(key=lambda r: r["x"])
    return {
        "regions": regions,
        "size": {"w": w, "h": h},
        "mean_L": round(float(lum.mean()), 2),
        "mean_S": round(float(hsv[:, :, 1].mean()), 3),
    }


# ── 2. 把事件渲染成声音 ─────────────────────────────────────────────────────

def _midi_of(r: dict, base: float = 45.0) -> float:
    """音区由纵向位置主导（上=高），明度做偏移（R1 的方向）。"""
    vertical = (1.0 - r["y"]) * 26.0          # 顶部 +26，底部 0
    from_light = (r["L"] - 50.0) * 0.16       # 明度小的偏移
    return base + vertical + from_light


def _write_wav_stereo(path: str, left: np.ndarray, right: np.ndarray) -> None:
    import wave
    pcm = np.stack([np.clip(left, -1, 1), np.clip(right, -1, 1)], axis=1)
    pcm = (pcm * 32767).astype(np.int16)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def _pan_gains(x: float, width: float = 1.55):
    """x∈[0,1] → 等功率左右增益。左边的东西去左声道，右边的去右声道。"""
    pan = (max(0.0, min(1.0, x)) - 0.5) * width      # -0.775 … +0.775
    ang = (pan + 1.0) * np.pi / 4.0
    return float(np.cos(ang)), float(np.sin(ang))


SCALE = [0, 3, 5, 7, 10]          # 小调五声：量化后听上去像"有调性"，而不是随机音高


def _scale_midi(deg: int, anchor: float = 45.0) -> float:
    """把音级（可以是负数）落到小调五声上，跨三个八度。"""
    octave, idx = divmod(deg, len(SCALE))
    return anchor + 12.0 * octave + SCALE[idx]


def _click(n: int, amp: float) -> np.ndarray:
    """极短的噪声瞬态：让"有没有事件"听得出来。"""
    rng = np.random.default_rng(7)
    buf = rng.standard_normal(n).astype(np.float32)
    buf *= np.exp(-np.linspace(0, 8, n)).astype(np.float32)
    return buf * amp


def render_scan(image_path: str, seconds: float = 14.0, out_wav: str = None,
                k: int = K_REGIONS, loudness_db: float = -20.0) -> dict:
    """扫描式声化 v2 —— 三个可听的差别：节奏密度、音域走向、起音性格。

    上一版的问题（实测）：四幅画的起音率都是 6.2–6.4 次/秒、动态范围都是 9 dB，
    唯一差别是"整条线高几个半音"。绝对音高没有参照点，人听不出来。

    这一版：
      · 音高按**这幅画自己的**明度分位量化到三个八度的五声音阶 → 每幅都走满音域
      · 只有边缘能量超过阈值才触发一次音 → **节奏密度随画面变**（网格画快，柔笔触慢）
      · 每个音是短促的拨弦 + 瞬态，不是绵长的持续音 → 有"事件感"
      · 声像跟 x 走（水平位置 → 左右）
    """
    st = analyze_structure(image_path, k)

    data = np.fromfile(image_path, dtype=np.uint8)
    bgr = cv2.imdecode(data, cv2.IMREAD_COLOR)
    h, w = bgr.shape[:2]
    small = cv2.resize(bgr, (WORK_W, max(1, int(h * WORK_W / w))), interpolation=cv2.INTER_AREA)
    rgb01 = np.clip(small[:, :, ::-1].astype(np.float32) / 255.0, 0, 1)
    lab = cv2.cvtColor(rgb01, cv2.COLOR_RGB2LAB)
    hsv = cv2.cvtColor(rgb01, cv2.COLOR_RGB2HSV)
    L = lab[:, :, 0]
    S = hsv[:, :, 1]
    gy = cv2.Sobel(L, cv2.CV_32F, 1, 0, ksize=3)
    gx = cv2.Sobel(L, cv2.CV_32F, 0, 1, ksize=3)
    edge = np.abs(gx) + np.abs(gy)

    COLS = 56
    cols = []
    for i in range(COLS):
        x0 = int(i * WORK_W / COLS)
        x1 = max(x0 + 1, int((i + 1) * WORK_W / COLS))
        cols.append({
            "x": (i + 0.5) / COLS,
            "L": float(L[:, x0:x1].mean()),
            "S": float(S[:, x0:x1].mean()),
            "edge": float(edge[:, x0:x1].mean()),
        })

    # 关键：全部用**绝对**尺度。上过一版的当——按每幅画自己的分位归一化，
    # 会把"这幅画和那幅画的差别"正好抹掉（四幅都变成 27 个事件、同样的音域）。
    edge_mean = float(edge.mean())                       # 5.4（Rothko）… 63.7（Vasarely）
    rate = float(np.clip(0.8 + edge_mean / 12.0, 1.0, 6.5))   # 事件率随画面"吵闹度"变

    n = int(SR * seconds)
    mixL = np.zeros(n + SR)
    mixR = np.zeros(n + SR)

    def add(seg: np.ndarray, i0: int, x: float):
        i1 = min(mixL.size, i0 + seg.size)
        if i1 <= i0:
            return
        pan = (max(0.0, min(1.0, x)) - 0.5) * 1.6
        ang = (pan + 1.0) * np.pi / 4.0
        part = seg[: i1 - i0]
        mixL[i0:i1] += part * float(np.cos(ang))
        mixR[i0:i1] += part * float(np.sin(ang))

    step = seconds / COLS
    n_events = max(3, int(round(rate * seconds)))
    line = []
    events = 0
    for t_idx in range(n_events):
        i = int(round(t_idx * (COLS - 1) / max(1, n_events - 1)))
        c = cols[i]
        # 绝对明度 → 五声音阶（三个八度），每幅画的音区不同
        deg = int(round((c["L"] / 100.0) * (len(SCALE) * 3 - 1)))
        midi = _scale_midi(max(0, min(len(SCALE) * 3 - 1, deg)))
        dur = float(np.clip(0.42 - c["edge"] * 0.004, 0.13, 0.42))
        f0 = midi_to_hz(midi)
        seg = _tone(f0, dur, 0.55, 0.28 + 0.34 * c["S"])       # 快衰减 = 拨弦
        a = max(1, int(SR * 0.006))
        seg[:a] *= np.linspace(0, 1, a)
        i0 = int(t_idx * (seconds / n_events) * SR)
        add(seg, i0, c["x"])
        cl = _click(int(SR * 0.018), float(np.clip(c["edge"] / 60.0, 0.0, 1.0)) * 0.18)
        add(cl, i0, c["x"])
        events += 1
        line.append({"t": round(t_idx * (seconds / n_events), 2), "L": round(c["L"], 1),
                     "S": round(c["S"], 3), "midi": round(midi, 1),
                     "note": _note_name(midi), "fires": True})

    # 低音：整幅平均明度，很轻
    drone = _tone(midi_to_hz(36.0 + (st["mean_L"] / 100.0) * 8.0), seconds * 0.98, 1.6, 0.05)
    d1 = min(mixL.size, drone.size)
    mixL[:d1] += drone[:d1] * 0.707
    mixR[:d1] += drone[:d1] * 0.707

    mixL, mixR = mixL[:n], mixR[:n]
    peak = max(float(np.abs(mixL).max()), float(np.abs(mixR).max())) or 1.0
    mixL /= peak
    mixR /= peak
    cur = 20.0 * np.log10(max(1e-9, float(np.sqrt(((mixL ** 2).mean() + (mixR ** 2).mean()) / 2))))
    g = 10 ** ((loudness_db - cur) / 20.0)
    mixL *= g
    mixR *= g
    m = max(float(np.abs(mixL).max()), float(np.abs(mixR).max()))
    if m > 0.999:
        mixL = mixL / m * 0.999
        mixR = mixR / m * 0.999
    fade = min(int(SR * 0.03), n // 4)
    if fade:
        ramp = np.linspace(0, 1, fade)
        mixL[:fade] *= ramp; mixL[-fade:] *= ramp[::-1]
        mixR[:fade] *= ramp; mixR[-fade:] *= ramp[::-1]

    if out_wav:
        _write_wav_stereo(out_wav, mixL, mixR)
    return {
        "wav_url": f"/preview/{Path(out_wav).name}" if out_wav else None,
        "seconds": seconds,
        "channels": 2,
        "events": events,
        "events_per_s": round(events / seconds, 2),
        "edge_mean": round(edge_mean, 1),
        "rate_hz": round(rate, 2),
        "line": line,
        "voices": [],
        "structure": st,
    }


def _note_name(midi: float) -> str:
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    m = int(round(midi))
    return f"{names[m % 12]}{m // 12 - 1}"


if __name__ == "__main__":
    import json
    import sys

    base = Path(__file__).parent
    img = sys.argv[1] if len(sys.argv) > 1 else str(
        base / "artworks" / "Georgia O'Keeffe-Music, Pink and Blue No. 2.jpg")
    out = base / "outputs" / "preview" / "scan_demo.wav"
    r = render_scan(img, 22.0, str(out))
    print(json.dumps({"wav": str(out), "voices": r["voices"][:4]}, ensure_ascii=False, indent=1))


# ── 网格音序：把画面变成一段 16 步的节奏型 ─────────────────────────────────
# 为什么加这个：连续扫描给出的是"一条线"，人记不住线，但记得住节奏型。
# 4×4 网格每格一个音，边缘强的格出声、弱的格停 ⇒ 每幅画得到一段不同的 groove。
# 实测 4×4 边缘指纹：Rothko 4–10、O'Keeffe 7–26、Matisse 24–51、Vasarely 高且匀。

def analyze_grid(image_path: str, gx: int = 4, gy: int = 4) -> list:
    data = np.fromfile(image_path, dtype=np.uint8)
    bgr = cv2.imdecode(data, cv2.IMREAD_COLOR)
    h, w = bgr.shape[:2]
    sm = cv2.resize(bgr, (WORK_W, max(1, int(h * WORK_W / w))), interpolation=cv2.INTER_AREA)
    rgb01 = np.clip(sm[:, :, ::-1].astype(np.float32) / 255.0, 0, 1)
    L = cv2.cvtColor(rgb01, cv2.COLOR_RGB2LAB)[:, :, 0]
    S = cv2.cvtColor(rgb01, cv2.COLOR_RGB2HSV)[:, :, 1]
    e = (np.abs(cv2.Sobel(L, cv2.CV_32F, 1, 0, ksize=3))
         + np.abs(cv2.Sobel(L, cv2.CV_32F, 0, 1, ksize=3)))
    H, W = L.shape
    cells = []
    for col in range(gx):
        for row in range(gy):                      # 列优先：从左到右，每列从上到下
            y0, y1 = row * H // gy, (row + 1) * H // gy
            x0, x1 = col * W // gx, (col + 1) * W // gx
            cells.append({
                "step": len(cells),
                "col": col, "row": row,
                "x": (col + 0.5) / gx,
                "L": float(L[y0:y1, x0:x1].mean()),
                "S": float(S[y0:y1, x0:x1].mean()),
                "edge": float(e[y0:y1, x0:x1].mean()),
            })
    return cells


def render_grid(image_path: str, loops: int = 3, step_s: float = 0.3,
                out_wav: str = None, loudness_db: float = -20.0,
                gx: int = 4, gy: int = 4) -> dict:
    """16 步音序循环若干次：节奏型 = 画面的方格边缘分布。"""
    cells = analyze_grid(image_path, gx, gy)
    steps = len(cells)
    total = loops * steps * step_s + 0.8
    n = int(SR * total)
    mixL = np.zeros(n + SR)
    mixR = np.zeros(n + SR)

    def add(seg, i0, x):
        i1 = min(mixL.size, i0 + seg.size)
        if i1 <= i0:
            return
        pan = (max(0.0, min(1.0, x)) - 0.5) * 1.5
        ang = (pan + 1.0) * np.pi / 4.0
        mixL[i0:i1] += seg[: i1 - i0] * float(np.cos(ang))
        mixR[i0:i1] += seg[: i1 - i0] * float(np.sin(ang))

    # 每循环出几个音 = 全画边缘能量（稀疏画少、网格画密）；
    # 出在哪几格 = 边缘最强的那些格（所以节奏型跟着构图走，不是随机的）
    edge_mean = float(np.mean([c["edge"] for c in cells]))
    k_on = int(max(1, min(steps, round(steps * float(np.clip(edge_mean / 70.0, 0.12, 1.0))))))
    ranked = sorted(cells, key=lambda c: -c["edge"])[:k_on]
    on_steps = {c["step"] for c in ranked}
    e_max = max(1e-6, max(c["edge"] for c in ranked))

    seq = []
    for lp in range(loops):
        for c in cells:
            idx = lp * steps + c["step"]
            i0 = int(idx * step_s * SR)
            vel = 0.35 + 0.65 * float(np.clip(c["edge"] / e_max, 0.0, 1.0))
            deg = int(round((c["L"] / 100.0) * (len(SCALE) * 3 - 1)))
            midi = _scale_midi(max(0, min(len(SCALE) * 3 - 1, deg)))
            fires = c["step"] in on_steps
            if fires:
                f0 = midi_to_hz(midi)
                seg = _tone(f0, step_s * 1.25, 0.6, (0.22 + 0.30 * c["S"]) * (0.35 + 0.65 * vel))
                a = max(1, int(SR * 0.005))
                seg[:a] *= np.linspace(0, 1, a)
                add(seg, i0, c["x"])
                add(_click(int(SR * 0.015), vel * 0.12), i0, c["x"])
            seq.append({"step": c["step"], "loop": lp, "col": c["col"], "row": c["row"],
                        "L": round(c["L"], 1), "edge": round(c["edge"], 1),
                        "note": _note_name(midi), "fires": fires, "vel": round(vel, 2)})

    peak = max(float(np.abs(mixL).max()), float(np.abs(mixR).max())) or 1.0
    mixL /= peak; mixR /= peak
    cur = 20.0 * np.log10(max(1e-9, float(np.sqrt(((mixL ** 2).mean() + (mixR ** 2).mean()) / 2))))
    g = 10 ** ((loudness_db - cur) / 20.0)
    mixL *= g; mixR *= g
    m = max(float(np.abs(mixL).max()), float(np.abs(mixR).max()))
    if m > 0.999:
        mixL = mixL / m * 0.999; mixR = mixR / m * 0.999
    n2 = int(SR * (loops * steps * step_s))
    mixL, mixR = mixL[:n2], mixR[:n2]
    fade = min(int(SR * 0.02), n2 // 4)
    if fade:
        r = np.linspace(0, 1, fade)
        mixL[:fade] *= r; mixR[:fade] *= r
        mixL[-fade:] *= r[::-1]; mixR[-fade:] *= r[::-1]
    if out_wav:
        _write_wav_stereo(out_wav, mixL, mixR)
    on = sum(1 for s2 in seq if s2["fires"]) // loops
    return {
        "wav_url": f"/preview/{Path(out_wav).name}" if out_wav else None,
        "seconds": round(loops * steps * step_s, 1),
        "steps": steps, "loops": loops,
        "onsets_per_loop": on,
        "edge_mean": round(edge_mean, 1),
        "k_on": k_on,
        "fingerprint": [c["edge"] for c in cells],
        "cells": [{k: c[k] for k in ("step", "col", "row", "L", "S", "edge")} for c in cells],
        "seq": seq,
    }

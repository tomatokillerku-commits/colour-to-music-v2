#!/usr/bin/env python3
"""
cvd.py — 色觉异常模拟（红绿色盲视角）

为什么需要这一层
----------------
整个项目的前提是「有些人的色相通道是失效的」。但页面上从来没有让人看见
这件事——读者只能接受一句断言。这里把同一幅画在正常视觉、红色盲(deuteranopia)、
绿色盲(protanopia) 下的成像并列出来，让前提变成可见的。

方法
----
Machado, Oliveira & Fernandes (2009) 的色觉缺陷模拟矩阵，severity = 1.0。
矩阵作用在**线性 RGB** 上（不是 sRGB 伽马空间），否则结果会偏亮偏灰。

这套矩阵是对「典型」红绿色盲的近似，不是对某个具体人的模拟，
更不能用来判断某个人的观感——UI 里必须这样标注。

用途提醒
--------
模拟图只用于说明「色相维度缺失后，剩下的信息是明度、饱和度、位置」，
它不构成对色觉异常者主观体验的替代，也不构成任何改善效果的证据。
"""

from pathlib import Path

import cv2
import numpy as np

# Machado et al. 2009, severity 1.0（线性 RGB 域）
MATRICES = {
    "deuteranopia": np.array([
        [0.367322, 0.860646, -0.227968],
        [0.280085, 0.672501, 0.047413],
        [-0.011820, 0.042940, 0.968881],
    ], dtype=np.float32),
    "protanopia": np.array([
        [0.152286, 1.052583, -0.204868],
        [0.114503, 0.786281, 0.099216],
        [-0.003882, -0.048116, 1.051998],
    ], dtype=np.float32),
    "tritanopia": np.array([
        [1.255528, -0.076749, -0.178779],
        [-0.078411, 0.930809, 0.147602],
        [0.004733, 0.691367, 0.303900],
    ], dtype=np.float32),
}

LABELS = {
    "normal": "typical colour vision",
    "deuteranopia": "deuteranopia · green-blind",
    "protanopia": "protanopia · red-blind",
}

MAX_SIDE = 560


def _srgb_to_linear(x: np.ndarray) -> np.ndarray:
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def _linear_to_srgb(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * (x ** (1 / 2.4)) - 0.055)


def simulate_array(rgb01: np.ndarray, kind: str = "deuteranopia") -> np.ndarray:
    """rgb01: float [H,W,3] in 0..1 (sRGB) → 模拟后的 sRGB"""
    m = MATRICES.get(kind)
    if m is None:
        return rgb01
    lin = _srgb_to_linear(rgb01)
    out = lin @ m.T
    return _linear_to_srgb(out)


def _read_unicode(path: str):
    data = np.fromfile(path, dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def _write_unicode(path: str, bgr) -> bool:
    ok, buf = cv2.imencode(".png", bgr)
    if not ok:
        return False
    with open(path, "wb") as f:
        f.write(buf.tobytes())
    return True


def generate(image_path: str, key: str, out_dir: Path,
             kinds=("deuteranopia", "protanopia")) -> dict:
    """生成 正常/红盲/绿盲 三张图，返回 URL 与说明"""
    out_dir.mkdir(parents=True, exist_ok=True)
    bgr = _read_unicode(image_path)
    if bgr is None:
        raise RuntimeError(f"cannot read image: {image_path}")

    h, w = bgr.shape[:2]
    if max(h, w) > MAX_SIDE:
        s = MAX_SIDE / max(h, w)
        bgr = cv2.resize(bgr, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)

    rgb01 = np.clip(bgr[:, :, ::-1].astype(np.float64) / 255.0, 0, 1)

    urls = {}
    files = {"normal": f"{key}_cvd_normal.png"}
    _write_unicode(str(out_dir / files["normal"]), bgr)
    urls["normal"] = f"/cvd/{files['normal']}"

    for kind in kinds:
        sim = simulate_array(rgb01, kind)
        out_bgr = (sim[:, :, ::-1] * 255).round().clip(0, 255).astype(np.uint8)
        name = f"{key}_cvd_{kind}.png"
        _write_unicode(str(out_dir / name), out_bgr)
        urls[kind] = f"/cvd/{name}"

    return {
        "urls": urls,
        "labels": {k: LABELS[k] for k in ["normal", *kinds]},
        "method": "Machado, Oliveira & Fernandes (2009), severity = 1.0, applied in linear RGB",
        "notes": [
            "这是对「典型」红绿色盲的近似模拟，不是对某个具体人的观感模拟",
            "用来看“色相失效后还剩什么信息”：明度、饱和度、位置",
            "不构成对色觉异常者体验的替代，也不构成改善效果的证据",
        ],
    }


if __name__ == "__main__":
    import sys
    import json

    base = Path(__file__).parent
    img = sys.argv[1] if len(sys.argv) > 1 else str(base / "artworks" / "Henri Matisse-La Desserte rouge.jpg")
    r = generate(img, "demo", base / "outputs" / "cvd")
    print(json.dumps(r, ensure_ascii=False, indent=2))

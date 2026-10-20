#!/usr/bin/env python3
"""
gen_prompts.py — 为全部画作生成英文 prompt (离线, 不消耗音乐 API 额度)

输出: outputs/prompts.json  供网页前端与手动出歌使用
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from color_extractor import load_and_preprocess, extract_color_metrics
from emotion_model import color_metrics_to_emotion
from suno_prompt import build_suno_prompt

IMG_DIR = HERE / "artworks"
CACHE = HERE / "ai_emotion_cache.json"
GALLERY = HERE / "gallery.json"
OUT_DIR = HERE / "outputs"
OUT = OUT_DIR / "prompts.json"


def main():
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    gallery = json.loads(GALLERY.read_text(encoding="utf-8")) if GALLERY.exists() else []
    meta = {g["file"]: g for g in gallery}

    results = {}
    files = sorted([p for p in IMG_DIR.iterdir()
                    if p.suffix.lower() in (".jpg", ".jpeg", ".png")
                    and not p.name.startswith(".")])

    for p in files:
        m = extract_color_metrics(load_and_preprocess(str(p)))
        emo = color_metrics_to_emotion(m)
        ai = cache.get(p.name)
        out = build_suno_prompt(m, emo, ai)

        g = meta.get(p.name, {})
        results[p.name] = {
            "file": p.name,
            "artist": g.get("artist", ""),
            "title": g.get("title", ""),
            "year": g.get("year", ""),
            "medium": g.get("medium", ""),
            "dimensions": g.get("dimensions", ""),
            "movement": g.get("movement", ""),
            # AI 情感
            "mood": out["mood"],
            "valence": out["valence"],
            "arousal": out["arousal"],
            "tension": out["tension"],
            "narrative": out["narrative"],
            "musical_hint": out["musical_hint"],
            # 颜色数值
            "dominant_hue_en": m["dominant_hue"].get("label_en", ""),
            "timbre_en": m["dominant_hue"].get("timbre_en", ""),
            "mode_en": m["warm_cold"].get("mode_en", ""),
            "pitch_en": m["brightness"].get("pitch_range_en", ""),
            "mean_S": m["saturation"]["mean_S"],
            "mean_V": m["brightness"]["mean_V"],
            "warm_ratio": m["warm_cold"]["warm_ratio_W"],
            "rgi": m["red_green_index"]["RGI_lab"],
            # 音乐参数
            "bpm": out["bpm"],
            # 输出
            "style_en": out["style_en"],
            "full_en": out["full_en"],
            "source": out["source"],
        }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"生成 {len(results)} 条 -> {OUT}\n")
    for name, r in results.items():
        flag = "AI " if r["source"] == "ai" else "RULE"
        print(f"[{flag}] {r['artist']} — {r['title']} ({r['year']})")
        print(f"   mood: {r['mood']}")
        print(f"   style: {r['style_en']}")
        print()


if __name__ == "__main__":
    main()

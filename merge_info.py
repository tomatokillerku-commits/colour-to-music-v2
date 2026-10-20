#!/usr/bin/env python3
"""
merge_info.py — 把 docx 中的作品元信息合并进 gallery.json

字段对齐: 按 artist 姓氏/名 + title 关键词匹配, 优先精确匹配 title
合并字段: year / medium / dimensions / movement
展示语言: 全部英文(界面文案与画作信息均为英文)
"""

import json
import re
from pathlib import Path

HERE = Path(__file__).parent
GALLERY = HERE / "gallery.json"
OUT = HERE / "gallery.json"

# 从 docx 提取的元信息: (artist, title, year, medium, dimensions)
INFO = [
    ("Zao Wou-Ki", "20.03.60", "1960", "Oil on canvas", "130 x 162 cm"),
    ("Wassily Kandinsky", "Impression III (Concert)", "1911", "Oil on canvas", "78.4 x 100.6 cm"),
    ("Paul Gauguin", "Tahitian Landscape", "1891", "Oil on canvas", "67.95 x 92.39 cm"),
    ("Georgia O'Keeffe", "Music, Pink and Blue No. 2", "1918", "Oil on canvas", "88.9 x 76 cm"),
    ("Paul Gauguin", "Manao tupapau (Spirit of the Dead Watching)", "1892",
     "Oil on jute mounted on canvas", "73.02 x 92.39 cm"),
    ("Wassily Kandinsky", "Yellow-Red-Blue (Gelb-Rot-Blau)", "1925", "Oil on canvas", "128 x 201.5 cm"),
    ("Mark Rothko", "Untitled (Black in Deep Orange)", "1957", "Oil on canvas", "176.2 x 136.5 cm"),
    ("Victor Vasarely", "Vega 200", "1968", "Acrylic on canvas", "200 x 200 cm"),
    ("Henri Matisse", "La Desserte rouge (The Dessert: Harmony in Red)", "1908",
     "Oil on canvas", "180.5 x 221 cm"),
    ("Helen Frankenthaler", "Jacob's Ladder", "1957", "Oil on canvas", "287.9 x 177.5 cm"),
]

# 艺术流派(英文, 供展示用)
MOVEMENT = {
    "Zao Wou-Ki": "Lyrical Abstraction",
    "Wassily Kandinsky": "Abstract Expressionism",
    "Paul Gauguin": "Post-Impressionism",
    "Georgia O'Keeffe": "American Modernism",
    "Mark Rothko": "Color Field Painting",
    "Victor Vasarely": "Op Art",
    "Henri Matisse": "Fauvism",
    "Helen Frankenthaler": "Color Field Painting",
}

# 文件名 -> docx 条目的映射(文件名里的画名与 docx 略有差异)
FILE_TO_KEY = {
    "赵无极-20-03-60.jpeg": ("Zao Wou-Ki", "20.03.60"),
    "Wassily Kandinsky-Impression_III_(Concert).jpg": ("Wassily Kandinsky", "Impression III (Concert)"),
    "Paul Gauguin-Tahitian Landscape.jpg": ("Paul Gauguin", "Tahitian Landscape"),
    "Georgia O'Keeffe-Music, Pink and Blue No. 2.jpg": ("Georgia O'Keeffe", "Music, Pink and Blue No. 2"),
    "Paul Gauguin-Manao tupapau.jpeg": ("Paul Gauguin", "Manao tupapau (Spirit of the Dead Watching)"),
    "Wassily Kandinsky-Yellow-Red-Blue.jpg": ("Wassily Kandinsky", "Yellow-Red-Blue (Gelb-Rot-Blau)"),
    "Mark Rothko-Untitled (Black in Deep Orange).jpeg": ("Mark Rothko", "Untitled (Black in Deep Orange)"),
    "Victor Vasarely - Vega 200 .jpeg": ("Victor Vasarely", "Vega 200"),
    "Henri Matisse-La Desserte rouge.jpg": ("Henri Matisse", "La Desserte rouge (The Dessert: Harmony in Red)"),
    "Helen Frankenthaler-Jacob’s Ladder.jpg": ("Helen Frankenthaler", "Jacob's Ladder"),
}

EN_NAME = {"赵无极": "Zao Wou-Ki"}


def main():
    items = json.loads(GALLERY.read_text(encoding="utf-8"))
    idx = {(a, t): (y, m, d) for a, t, y, m, d in INFO}
    miss = []

    for it in items:
        key = FILE_TO_KEY.get(it["file"])
        # 艺术家名统一为英文
        it["artist"] = EN_NAME.get(it["artist"], it["artist"])

        if key and key in idx:
            artist, title = key
            y, m, d = idx[key]
            it["title"] = title
            it["year"] = y
            it["medium"] = m
            it["dimensions"] = d
            it["movement"] = MOVEMENT.get(artist, "")
        else:
            miss.append(it["file"])
            it.setdefault("medium", "")
            it.setdefault("dimensions", "")

    OUT.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已更新 {len(items)} 条 -> {OUT}\n")
    for it in items:
        print(f"  {it['artist']:<24} {it['title']:<46} {it['year']}  {it['movement']}")
    if miss:
        print("\n未匹配到元信息:")
        for m in miss:
            print(f"   {m}")


if __name__ == "__main__":
    main()

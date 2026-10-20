#!/usr/bin/env python3
"""
build_gallery.py — 从「01_确定可用」的文件名生成 gallery.json

文件名格式: 作者-画名.jpg  (也兼容 "作者 - 画名.jpg")
  例: Wassily Kandinsky-Yellow-Red-Blue.jpg
     Victor Vasarely - Vega 200 .jpeg
     Georgia O'Keeffe-Music, Pink and Blue No. 2.jpg

分割策略: 优先按 " - " 切, 否则按第一个 "-" 切
  (画名内部可能含 "-", 如赵无极《20-03-60》, 因此只切第一处)

生成的字段:
  id / file / artist / title / year / movement / intro
  year, movement, intro 留空, 由你后续补充
"""

import json
import re
from pathlib import Path

SRC = Path(__file__).parent / "artworks"
OUT = Path(__file__).parent / "gallery.json"

SKIP = {".DS_Store"}


def split_name(stem: str) -> tuple:
    """文件名主干 -> (artist, title)"""
    if " - " in stem:
        artist, title = stem.split(" - ", 1)
    elif "-" in stem:
        artist, title = stem.split("-", 1)
    else:
        return "", stem
    return artist.strip(), title.strip()


def slug(s: str) -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "_", s).strip("_")
    return s.lower()


def main():
    files = sorted([p for p in SRC.iterdir()
                    if p.is_file() and p.name not in SKIP and not p.name.startswith(".")])
    if not files:
        print(f"目录为空: {SRC}")
        return

    items = []
    for i, p in enumerate(files, 1):
        artist, title = split_name(p.stem)
        items.append({
            "id": f"{i:02d}_{slug(artist)[:20]}_{slug(title)[:24]}".strip("_"),
            "file": p.name,
            "artist": artist,
            "title": title,
            "year": "",
            "movement": "",
            "intro": "",
        })
        print(f"  {i:>2}. {artist:<24} 《{title}》")

    OUT.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n共 {len(items)} 条 -> {OUT}")

    # 检查解析质量
    bad = [x for x in items if not x["artist"] or not x["title"]]
    if bad:
        print("\n⚠️ 以下条目解析异常, 请手动修正:")
        for x in bad:
            print(f"   {x['file']}  ->  artist='{x['artist']}' title='{x['title']}'")


if __name__ == "__main__":
    main()

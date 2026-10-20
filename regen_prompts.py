#!/usr/bin/env python3
"""
regen_prompts.py — 用「规则层约束版」重新生成 10 幅预置画作的 music_prompt

和交付版 music_prompt_ai.py main() 的区别
----------------------------------------
旧流程只给 Gemini 一堆颜色数值，模型会自己发明颜色→音乐对应
（实测给出 "viola-led strings, mid-to-high register, 85 BPM"，与规则层冲突）。

本脚本按映射层重算每幅画的 metrics + mapping，把 evidence 规则作为
BINDING 约束塞进 prompt，产出与界面 Mapping 面板完全一致的 prompt。

可断点续跑：已写入 rules_version=v2 的条目默认跳过（--force 覆盖）。
第一次运行会把原文件备份为 music_prompts.json.bak。
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import server as S                                     # 复用 get_era_style / 路径常量
from color_extractor import load_and_preprocess, extract_color_metrics
from emotion_model import color_metrics_to_emotion
from suno_prompt import build_suno_prompt
import mapping_rules
import music_prompt_ai


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="已生成的也重跑")
    ap.add_argument("--only", nargs="*", default=None, help="只跑文件名含这些子串的画作")
    ap.add_argument("--sleep", type=float, default=4.0, help="每次调用间隔(秒), 避免限流")
    args = ap.parse_args()

    S._load_dotenv()
    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        print("错误: GEMINI_API_KEY 未设置", file=sys.stderr)
        return 1

    if not S.MUSIC_PROMPTS_F.exists():
        print(f"错误: 找不到 {S.MUSIC_PROMPTS_F}", file=sys.stderr)
        return 1

    raw = S.MUSIC_PROMPTS_F.read_text(encoding="utf-8")
    out = json.loads(raw) if raw.strip() else {}
    prompts = json.loads(S.PROMPTS_F.read_text(encoding="utf-8"))
    gallery = json.loads(S.GALLERY_F.read_text(encoding="utf-8"))

    backup = S.MUSIC_PROMPTS_F.with_suffix(".json.bak")
    if not backup.exists():
        backup.write_text(raw, encoding="utf-8")
        print(f"已备份原文件 → {backup.name}")

    ok = skipped = failed = 0
    for i, g in enumerate(gallery, 1):
        f = g.get("file", "")
        title = g.get("title", "")
        if args.only and not any(o.lower() in f.lower() for o in args.only):
            continue
        if not args.force and out.get(f, {}).get("rules_version") == "v2":
            print(f"[{i}/{len(gallery)}] 跳过(已 v2): {title}")
            skipped += 1
            continue

        p = S.IMG_DIR / f
        if not p.exists():
            print(f"[{i}/{len(gallery)}] ✗ 图不存在: {f}")
            failed += 1
            continue

        # 1. 重新测量 + 规则层（和界面显示同一套代码）
        rgb = load_and_preprocess(str(p))
        m = extract_color_metrics(rgb)
        emo = color_metrics_to_emotion(m)
        d = prompts.get(f, {})
        ai = {k: d.get(k) for k in ("mood", "valence", "arousal", "tension",
                                    "narrative", "musical_hint")
              if d.get(k) not in (None, "")}
        mapping = mapping_rules.build(m, ai)
        sp = build_suno_prompt(m, emo, ai or None, mapping=mapping)
        flat = S._prompt_block(m, emo, sp)
        era = S.get_era_style(g)

        # 2. Gemini 转译（规则层作为 BINDING 约束）
        print(f"[{i}/{len(gallery)}] {title} …", flush=True)
        try:
            txt = music_prompt_ai.translate(
                {**flat, "title": title, "artist": g.get("artist", ""),
                 "year": g.get("year", ""), "movement": g.get("movement", "")},
                ai, key, era=era, mapping=mapping,
            )
        except Exception as e:
            print(f"    ✗ 失败: {str(e)[:160]}")
            failed += 1
            time.sleep(args.sleep * 2)
            continue

        # 3. 落盘（每幅都写，断点续跑安全）
        out[f] = {
            "file": f,
            "artist": g.get("artist", ""),
            "title": title,
            "mood": ai.get("mood", ""),
            "music_prompt": txt.strip(),
            "source": "gemini",
            "rules_version": "v2",
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "rule_snapshot": {k: mapping["params"][k] for k in
                              ("mean_L", "mean_S", "pitch_anchor_midi", "pitch_note",
                               "loudness_target_db", "brightness_target_hz",
                               "bpm", "mode", "instrument_candidates")},
        }
        S.MUSIC_PROMPTS_F.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
        print(f"    ✓ {len(txt)} 字符 | {len(txt.split())} words")
        ok += 1
        time.sleep(args.sleep)

    print(f"\n完成: 成功 {ok} / 跳过 {skipped} / 失败 {failed}  → {S.MUSIC_PROMPTS_F}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())

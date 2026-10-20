#!/usr/bin/env python3
"""
measure_audio.py — 测量 outputs/audio 里已生成音乐的响度与频谱重心

为什么需要
----------
需求书 §4 要求把「基础声音」和「Suno 完整音乐」分开呈现，理由之一是
Suno 不保证执行 prompt 里的参数。要证明这件事，就得对成品做和基础声音
同一套测量（synth.measure：RMS dBFS + 频谱重心），而不是凭听感断言。

流程: mp3 --ffmpeg--> 44.1k 单声道 wav --> synth.measure --> outputs/audio_measured.json
需要系统里有 ffmpeg；结果文件随项目一起分发，前端直接读。
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import synth


def measure_one(path: Path) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        wav = tf.name
    try:
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(path),
             "-ac", "1", "-ar", "44100", wav],
            check=True,
        )
        return synth.measure(wav)
    finally:
        Path(wav).unlink(missing_ok=True)


def main() -> int:
    out_f = HERE / "outputs" / "audio_measured.json"
    data = json.loads(out_f.read_text(encoding="utf-8")) if out_f.exists() else {}
    files = sorted((HERE / "outputs" / "audio").glob("*.mp3"))
    if not files:
        print("outputs/audio 里没有 mp3")
        return 1

    ok = skip = fail = 0
    for p in files:
        if p.name in data:
            skip += 1
            continue
        try:
            m = measure_one(p)
        except Exception as e:
            print(f"✗ {p.name}: {str(e)[:120]}")
            fail += 1
            continue
        data[p.name] = m
        ok += 1
        print(f"✓ {p.name:52s} {m['rms_dbfs']:>7} dBFS  {m['spectral_centroid_hz']:>5} Hz  {m['duration_s']}s")

    out_f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n新增 {ok} / 跳过 {skip} / 失败 {fail} → {out_f}  共 {len(data)} 条")
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    sys.exit(main())

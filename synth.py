#!/usr/bin/env python3
"""
synth.py — 可验证的基础声音（需求书 P1-4 / §4 基础声音分工）

为什么单独做这一层
------------------
Suno 不保证执行具体的音高、力度、音色指令。所以「规则到底有没有被遵守」
不能靠听完整音乐判断，必须有一层规则明确、可以测量的声音：

    MIDI        精确规定音高（音符号 = 半音，可读可查）
    numpy 合成  用谐波叠加控制音色明亮度（衰减指数 → 频谱重心）
    音频测量    输出后实测 RMS dBFS 与频谱重心，和规则目标对比

三条证据规则在这里落地：
    R1  L*       → pitch_anchor (MIDI 音高)
    R2  S        → loudness_target (RMS dBFS)
    R3  L*       → brightness_target (频谱重心 Hz)

局部区域（P1-2）: 每个显著区域用自己的 L*/S 生成一条辅助声部，
**不做加权**，只是同时可听——权重机制属于未来展望。
"""

import math
import struct
import wave
from pathlib import Path

import numpy as np

try:
    import mido
except Exception:      # mido 缺失时仍可出音频, 只是不写 .mid
    mido = None

SR = 44100
DEFAULT_SECONDS = 15.0
NOTE_SECONDS = 1.5           # 每个音的时长（10 个音 ≈ 15 秒）
MAX_HARMONICS = 24
TARGET_PEAK = 0.89           # 归一化后的峰值，避免削波


# ── 基础工具 ────────────────────────────────────────────────────────────────
def midi_to_hz(n: float) -> float:
    return 440.0 * (2.0 ** ((n - 69.0) / 12.0))


def _centroid_ratio(p: float, k_max: int = MAX_HARMONICS) -> float:
    """谐波幅度 1/k^p 时，频谱重心 / 基频 的比值"""
    k = np.arange(1, k_max + 1, dtype=np.float64)
    ak = k ** (-p)
    return float((k * ak).sum() / ak.sum())


def _solve_p(target_ratio: float) -> float:
    """二分求衰减指数 p，使频谱重心落在 target_ratio * f0"""
    lo, hi = 0.0, 8.0
    if target_ratio <= _centroid_ratio(hi):
        return hi
    if target_ratio >= _centroid_ratio(lo):
        return lo
    for _ in range(40):
        mid = (lo + hi) / 2.0
        if _centroid_ratio(mid) > target_ratio:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def _adsr(n: int, a=0.02, d=0.15, s=0.65, r=0.35) -> np.ndarray:
    """简单包络，参数按比例，避免起止爆音"""
    a_n, d_n, r_n = int(n * a), int(n * d), int(n * r)
    s_n = max(0, n - a_n - d_n - r_n)
    env = np.concatenate([
        np.linspace(0, 1, max(1, a_n), endpoint=False),
        np.linspace(1, s, max(1, d_n), endpoint=False),
        np.full(s_n, s),
        np.linspace(s, 0, max(1, r_n)),
    ])
    if env.size < n:
        env = np.pad(env, (0, n - env.size))
    return env[:n]


def _tone(f0: float, seconds: float, p: float, amp: float) -> np.ndarray:
    """谐波叠加：p 越大越暗（频谱重心越低）"""
    n = int(SR * seconds)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for k in range(1, MAX_HARMONICS + 1):
        f = f0 * k
        if f > SR / 2 - 100:
            break
        out += (k ** (-p)) * np.sin(2 * math.pi * f * t)
    out *= amp / max(1e-9, np.abs(out).max())
    return out * _adsr(n)


# ── 主渲染 ──────────────────────────────────────────────────────────────────
def render(mapping: dict, regions=None, seconds: float = DEFAULT_SECONDS,
           out_wav: str = None, out_mid: str = None,
           layer: int = 4, samples=None, image_path: str = None,
           spacing: float = None) -> dict:
    """按规则层参数合成一段可试听、可测量的声音

    mapping : mapping_rules.build() 的返回
    regions : saliency.analyze()['regions']（可选，进入 P1-2 局部声部）
    samples : 用户点选取样 [{L,S,...}]（优先于 regions）
    layer   : 1=只有音高线  2=+响度  3=+音色  4=+局部/取样声部
              逐层叠加，用来听出每条规则各自做了什么
    """
    p = mapping["params"]
    anchor = float(p["pitch_anchor_midi"])
    target_db = float(p["loudness_target_db"])
    target_hz = float(p["brightness_target_hz"])

    # 旋律：优先用这幅画自己的五段轮廓（band_motif），重复两遍形成可记的动机。
    # 旧的固定 steps = [0,2,3,5,3,2,0,-2,0,0] 是九幅画共用同一段曲、只换高度，
    # 所以每次试听都像同一段旋律——这是用户第二次指出的同一个问题。
    motif = None
    if image_path:
        try:
            motif = band_motif(image_path)
        except Exception:
            motif = None
    if motif and motif.get("notes"):
        base_midi = float(motif["base_midi"])
        steps = [int(m - base_midi) for m in motif["notes"]] * 2
        anchor = base_midi
        spacing = float(spacing or (seconds / max(1, len(steps))))
    else:
        steps = [0, 2, 3, 5, 3, 2, 0, -2, 0, 0]
        spacing = float(spacing or NOTE_SECONDS)
    n_total = int(SR * seconds)
    mix = np.zeros(n_total + SR * 2)      # 留出尾音空间

    notes = []
    for i, st in enumerate(steps):
        m_note = int(round(max(21, min(108, anchor + st))))
        f0 = midi_to_hz(m_note)
        ratio = max(1.0, target_hz / max(1.0, f0))
        # layer<3: 不施加 R3（谐波不衰减，音色保持最亮）
        p_decay = 0.0 if layer < 3 else _solve_p(min(ratio, _centroid_ratio(0.0)))
        start = int(i * spacing * SR)
        if start >= mix.size:          # 短片段(分层试听)只渲染装得下的音
            break
        seg = _tone(f0, NOTE_SECONDS * 1.35, p_decay, 1.0)
        end = min(mix.size, start + seg.size)
        mix[start:end] += seg[: end - start]
        notes.append({"index": i, "midi": m_note, "hz": round(f0, 2),
                      "start_s": round(i * spacing, 2),
                      "decay_exponent": round(p_decay, 2)})

    # ── 局部声部：优先用户点选取样；每个用自己的 L*/S，无加权 ──
    region_voices = []
    voice_src = samples if samples else (regions or [])
    if layer >= 4 and voice_src:
        for r in voice_src[:4]:
            rL = float(r.get("mean_L", r.get("L", 50)))
            rS = float(r.get("mean_S", r.get("S", 0.5)))
            r_anchor = 36.0 + (max(0.0, min(100.0, rL)) / 100.0) * 48.0
            r_db = -30.0 + rS * 12.0
            r_hz = 700.0 + (max(0.0, min(100.0, rL)) / 100.0) * 2800.0
            f0 = midi_to_hz(r_anchor)
            p_decay = _solve_p(min(max(1.0, r_hz / f0), _centroid_ratio(0.0)))
            seg = _tone(f0, seconds * 0.92, p_decay, 10 ** (r_db / 20.0) * 4.0)
            mix[: seg.size] += seg
            region_voices.append({
                "region_id": r.get("id", len(region_voices) + 1),
                "midi": round(r_anchor, 1),
                "hz": round(f0, 2),
                "target_db": round(r_db, 1),
                "target_hz": int(r_hz),
                "decay_exponent": round(p_decay, 2),
                "source": {"L": round(rL, 1), "S": round(rS, 2)},
            })

    mix = mix[:n_total]

    # ── 响度: layer 1 不施加规则（固定 -20 dBFS），layer>=2 校准到目标 ──
    peak = float(np.abs(mix).max()) or 1.0
    mix = mix / peak * TARGET_PEAK
    cur_db = 20.0 * math.log10(max(1e-9, float(np.sqrt((mix ** 2).mean()))))
    want_db = -20.0 if layer < 2 else target_db
    gain_db = want_db - cur_db
    mix *= 10 ** (gain_db / 20.0)
    if float(np.abs(mix).max()) > 0.999:      # 削波保护
        mix = mix / float(np.abs(mix).max()) * 0.999

    pcm = (np.clip(mix, -1, 1) * 32767).astype("<i2")

    res = {"seconds": seconds, "sample_rate": SR, "notes": notes,
           "region_voices": region_voices, "target": mapping["params"]}

    if out_wav:
        Path(out_wav).parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(out_wav), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(pcm.tobytes())
        res["wav"] = str(out_wav)

    if out_mid and mido is not None:
        Path(out_mid).parent.mkdir(parents=True, exist_ok=True)
        mf = mido.MidiFile(ticks_per_beat=480)
        tr = mido.MidiTrack()
        mf.tracks.append(tr)
        tr.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(int(p.get("bpm", 90))), time=0))
        tr.append(mido.MetaMessage("track_name", name="colour-to-music preview", time=0))
        ticks_per_note = int(mf.ticks_per_beat * NOTE_SECONDS * int(p.get("bpm", 90)) / 60.0)
        for nt in notes:
            tr.append(mido.Message("note_on", note=nt["midi"], velocity=90, time=0))
            tr.append(mido.Message("note_off", note=nt["midi"], velocity=0, time=ticks_per_note))
        mf.save(str(out_mid))
        res["mid"] = str(out_mid)

    return res


# ── 分层渲染（stem player）：同一段旋律，逐层叠加一条规则 ────────────────────

LAYER_LABELS = {
    1: "the motif · R1 only",
    2: "＋ loudness · R2",
    3: "＋ timbre brightness · R3",
}
# L4「＋ 取样声部」已删除：它唯一的独特内容来自用户点选，而点选被判定为无音乐后果的交互。
# 三层正好对应三条 evidence 规则，累计叠加，不再有第四层。


def render_layers(mapping: dict, samples=None, seconds: float = 8.0,
                  out_dir=None, key: str = "x", image_path: str = None) -> list:
    """渲染 4 个逐层叠加的版本，每个都做一次测量。

    同一段旋律、同一个音高；差别只在
      L1 纯正弦（不施加响度/音色规则）
      L2 施加目标响度
      L3 施加目标音色明亮度（频谱重心）
      L4 再加取样声部
    """
    out = []
    for layer in (1, 2, 3):
        wav = Path(out_dir) / f"{key}_L{layer}.wav"
        r = render(mapping, None, seconds, str(wav), None, layer=layer,
                   image_path=image_path)
        meas = measure(str(wav))
        out.append({
            "layer": layer,
            "label": LAYER_LABELS[layer],
            "wav_url": f"/preview/{wav.name}",
            "measured": meas,
            "voices": len(r["region_voices"]),
            "decay_exponent": r["notes"][0]["decay_exponent"] if r["notes"] else None,
            # 给前端的钢琴卷帘用
            "notes": [{"start_s": n["start_s"], "midi": n["midi"]} for n in r["notes"]],
            "region_voices": r["region_voices"],
            "seconds": seconds,
        })
    return out


# ── 画廊用的「声音签名」：一个短和弦，1–2 秒听完一幅画 ──────────────────────

def _write_wav(path: str, mix: np.ndarray) -> None:
    """单声道 float [-1,1] → 16bit PCM WAV"""
    pcm = (np.clip(mix, -1.0, 1.0) * 32767).astype(np.int16)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())

_NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def _name_of(midi: int) -> str:
    m = int(round(midi))
    return f"{_NOTE_NAMES[m % 12]}{m // 12 - 1}"


def band_motif(image_path: str, bands_n: int = 5) -> dict:
    """画面横切若干段：每段平均 L* → 一个音（供签名与 Suno prompt 共用）。"""
    import cv2
    data = np.fromfile(image_path, dtype=np.uint8)
    bgr = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if bgr is None:
        return {"notes": [], "names": [], "base_midi": None}
    h, w = bgr.shape[:2]
    sm = cv2.resize(bgr, (240, max(1, int(h * 240 / w))), interpolation=cv2.INTER_AREA)
    rgb01 = np.clip(sm[:, :, ::-1].astype(np.float32) / 255.0, 0, 1)
    L = cv2.cvtColor(rgb01, cv2.COLOR_RGB2LAB)[:, :, 0]
    S = cv2.cvtColor(rgb01, cv2.COLOR_RGB2HSV)[:, :, 1]
    rows = []
    for i in range(bands_n):
        sl = slice(i * L.shape[0] // bands_n, (i + 1) * L.shape[0] // bands_n)
        rows.append((float(L[sl].mean()), float(S[sl].mean())))
    mean_l = float(np.mean([r[0] for r in rows]))
    base = _snap_penta(45.0 + (mean_l - 30.0) / 50.0 * 12.0)
    notes, names = [], []
    for bl, bs in rows:
        off = float(np.clip((bl - mean_l) * 0.55, -9.0, 9.0))
        m = _snap_penta(base + off)
        notes.append(m)
        names.append(_name_of(m))
    return {"notes": notes, "names": names, "base_midi": base,
            "mean_L": round(mean_l, 2)}


def render_signature(mapping: dict, seconds: float = 2.4, out_wav: str = None) -> dict:
    """根音 = pitch anchor，叠五度与八度；音色由 target_centroid 决定。
    目的不是好听，是让十幅画可以在画廊里被"扫听"比较。
    """
    p = mapping["params"]
    anchor = float(p["pitch_anchor_midi"])
    target_hz = float(p["brightness_target_hz"])
    target_db = float(p["loudness_target_db"])

    n = int(SR * seconds)
    mix = np.zeros(n + SR)
    notes = []
    for i, off in enumerate((0.0, 7.0, 12.0)):
        m_note = int(round(max(21, min(108, anchor + off))))
        f0 = midi_to_hz(m_note)
        ratio = max(1.0, target_hz / max(1.0, f0))
        p_decay = _solve_p(min(ratio, _centroid_ratio(0.0)))
        seg = _tone(f0, seconds * 0.9, p_decay, 0.9 / (1 + i * 0.55))
        mix[: seg.size] += seg
        notes.append({"midi": m_note, "hz": round(f0, 2), "decay_exponent": round(p_decay, 2)})

    mix = mix[:n]
    peak = float(np.abs(mix).max()) or 1.0
    mix = mix / peak * TARGET_PEAK
    cur_db = 20.0 * math.log10(max(1e-9, float(np.sqrt((mix ** 2).mean()))))
    mix *= 10 ** ((target_db - cur_db) / 20.0)
    if float(np.abs(mix).max()) > 0.999:
        mix = mix / float(np.abs(mix).max()) * 0.999
    # 头尾淡入淡出，避免点击声
    fade = min(int(SR * 0.02), n // 4)
    if fade:
        ramp = np.linspace(0, 1, fade)
        mix[:fade] *= ramp
        mix[-fade:] *= ramp[::-1]

    if out_wav:
        _write_wav(out_wav, mix)
    return {"wav_url": f"/preview/{Path(out_wav).name}" if out_wav else None,
            "notes": notes, "seconds": round(seconds, 2)}


def render_chord(samples, seconds: float = 3.0, out_wav: str = None,
                 loudness_db: float = -20.0) -> dict:
    """把用户取样的颜色一起奏成一个和弦（每块颜色一条声线）"""
    if not samples:
        return {"wav_url": None, "voices": []}

    n = int(SR * seconds)
    mix = np.zeros(n + SR)
    voices = []
    for i, s in enumerate(samples[:6]):
        L = max(0.0, min(100.0, float(s.get("L", 50))))
        S = max(0.0, min(1.0, float(s.get("S", 0.5))))
        anchor = 36.0 + (L / 100.0) * 48.0
        f0 = midi_to_hz(anchor)
        r_hz = 700.0 + (L / 100.0) * 2800.0
        p_decay = _solve_p(min(max(1.0, r_hz / f0), _centroid_ratio(0.0)))
        amp = (0.35 + 0.55 * S) / (1 + i * 0.35)
        seg = _tone(f0, seconds * 0.92, p_decay, amp)
        mix[: seg.size] += seg
        voices.append({"id": s.get("id", i + 1), "midi": round(anchor, 1),
                       "note": s.get("voice_note", ""), "hex": s.get("hex", "")})

    mix = mix[:n]
    peak = float(np.abs(mix).max()) or 1.0
    mix = mix / peak * TARGET_PEAK
    cur_db = 20.0 * math.log10(max(1e-9, float(np.sqrt((mix ** 2).mean()))))
    mix *= 10 ** ((loudness_db - cur_db) / 20.0)
    if float(np.abs(mix).max()) > 0.999:
        mix = mix / float(np.abs(mix).max()) * 0.999
    fade = min(int(SR * 0.03), n // 4)
    if fade:
        ramp = np.linspace(0, 1, fade)
        mix[:fade] *= ramp
        mix[-fade:] *= ramp[::-1]

    if out_wav:
        _write_wav(out_wav, mix)
    return {"wav_url": f"/preview/{Path(out_wav).name}" if out_wav else None,
            "voices": voices, "seconds": round(seconds, 2)}


def render_sequence(samples, step_s: float = 0.9, out_wav: str = None,
                    loudness_db: float = -20.0) -> dict:
    """按 x 从左到右把取样点排成一串音：观看的顺序变成旋律。
    不改编曲逻辑——旋律来自用户点在哪里，而不是固定音阶。"""
    if not samples:
        return {"wav_url": None, "voices": []}

    ordered = sorted(samples, key=lambda s: float(s.get("x", 0.5)))
    n = int(SR * (step_s * len(ordered) + 0.8))
    mix = np.zeros(n)
    voices = []
    for i, s in enumerate(ordered[:10]):
        L = max(0.0, min(100.0, float(s.get("L", 50))))
        S = max(0.0, min(1.0, float(s.get("S", 0.5))))
        anchor = 36.0 + (L / 100.0) * 48.0
        f0 = midi_to_hz(anchor)
        r_hz = 700.0 + (L / 100.0) * 2800.0
        p_decay = _solve_p(min(max(1.0, r_hz / f0), _centroid_ratio(0.0)))
        seg = _tone(f0, step_s * 1.15, p_decay, 0.55 + 0.45 * S)
        start = int(i * step_s * SR)
        end = min(n, start + seg.size)
        mix[start:end] += seg[: end - start]
        voices.append({"order": i + 1, "note": s.get("voice_note", ""),
                       "hex": s.get("hex", ""), "x": s.get("x")})

    peak = float(np.abs(mix).max()) or 1.0
    mix = mix / peak * TARGET_PEAK
    cur_db = 20.0 * math.log10(max(1e-9, float(np.sqrt((mix ** 2).mean()))))
    mix *= 10 ** ((loudness_db - cur_db) / 20.0)
    if float(np.abs(mix).max()) > 0.999:
        mix = mix / float(np.abs(mix).max()) * 0.999
    fade = min(int(SR * 0.03), n // 4)
    if fade:
        ramp = np.linspace(0, 1, fade)
        mix[:fade] *= ramp
        mix[-fade:] *= ramp[::-1]
    if out_wav:
        _write_wav(out_wav, mix)
    return {"wav_url": f"/preview/{Path(out_wav).name}" if out_wav else None,
            "voices": voices, "seconds": round(step_s * len(ordered) + 0.8, 2)}


# ── 输出音频测量（验证规则是否真的被执行） ───────────────────────────────────
def measure(wav_path: str) -> dict:
    """读取 WAV → RMS dBFS / 频谱重心 / 峰值"""
    with wave.open(str(wav_path), "rb") as w:
        sr = w.getframerate()
        nch = w.getnchannels()
        sw = w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if sw != 2:
        raise RuntimeError("expect 16-bit wav")
    x = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    if nch > 1:
        x = x.reshape(-1, nch).mean(axis=1)

    rms = float(np.sqrt((x ** 2).mean())) or 1e-12
    rms_db = 20.0 * math.log10(rms)
    peak_db = 20.0 * math.log10(max(1e-12, float(np.abs(x).max())))

    # 频谱重心：只用有能量的帧，避免静音段把重心拉低
    win = 4096
    hop = win // 2
    freqs = np.fft.rfftfreq(win, 1.0 / sr)
    cents, weights = [], []
    for s in range(0, max(1, x.size - win), hop):
        seg = x[s:s + win]
        if seg.size < win:
            break
        e = float((seg ** 2).mean())
        if e < 1e-6:
            continue
        mag = np.abs(np.fft.rfft(seg * np.hanning(win)))
        total = mag.sum()
        if total <= 0:
            continue
        cents.append(float((freqs * mag).sum() / total))
        weights.append(e)
    centroid = float(np.average(cents, weights=weights)) if cents else 0.0

    return {
        "rms_dbfs": round(rms_db, 2),
        "peak_dbfs": round(peak_db, 2),
        "spectral_centroid_hz": int(round(centroid)),
        "duration_s": round(x.size / sr, 2),
    }


def verify(measured: dict, targets: dict) -> dict:
    """规则目标 vs 实测：只判方向与容差，不假装精确"""
    d_loud = measured["rms_dbfs"] - float(targets["loudness_target_db"])
    d_cen = measured["spectral_centroid_hz"] - float(targets["brightness_target_hz"])
    return {
        "loudness_delta_db": round(d_loud, 2),
        "loudness_ok": abs(d_loud) <= 1.0,
        "centroid_delta_hz": int(d_cen),
        "centroid_rel_error": round(d_cen / max(1.0, float(targets["brightness_target_hz"])), 3),
        "centroid_ok": abs(d_cen) / max(1.0, float(targets["brightness_target_hz"])) <= 0.15,
        "note": "响度按目标校准所以误差小；频谱重心受谐波上限与包络影响，15% 内视为通过",
    }


if __name__ == "__main__":
    import sys
    import json

    sys.path.insert(0, str(Path(__file__).parent))
    from color_extractor import load_and_preprocess, extract_color_metrics
    import mapping_rules

    img = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).parent / "artworks" / "赵无极-20-03-60.jpeg")
    m = extract_color_metrics(load_and_preprocess(img))
    mp = mapping_rules.build(m, None)

    out_dir = Path(__file__).parent / "outputs" / "preview"
    r = render(mp, None, out_wav=str(out_dir / "demo.wav"), out_mid=str(out_dir / "demo.mid"))
    meas = measure(r["wav"])
    print(f"notes: {[n['midi'] for n in r['notes']]}")
    print(f"target: {mp['params']['loudness_target_db']} dBFS / {mp['params']['brightness_target_hz']} Hz")
    print(f"measured: {json.dumps(meas, ensure_ascii=False)}")
    print(f"verify: {json.dumps(verify(meas, mp['params']), ensure_ascii=False)}")
    print(f"wav: {r['wav']}")


# ── 签名 v2：五段垂直轮廓 → 五个音 ────────────────────────────────────────
# 为什么改：v1 的签名是「根音 + 五度 + 八度」，九幅画只是同一个和弦换了高度，
# 最小间隔 0.1 半音（Tahitian 64.40 / Yellow-Red-Blue 64.50，同一个 E4），
# 物理上就是同一个声音。一个标量承载不了九件东西。
# v2 让签名有"形状"：把画面横切成五段，每段明度偏离全画均值的多少 → 旋律偏移，
# 每段饱和度 → 力度。于是两幅均值相同的画，只要上下明暗分布不同，听起来就不同。

_PENTA = (0, 3, 5, 7, 10)


def _snap_penta(midi: float) -> int:
    """吸附到以 45(A2) 为根的小调五声音阶。"""
    m = int(round(midi))
    best, best_d = m, 99
    base = m - ((m - 45) % 12)          # 回到根音所在八度
    for octv in (-1, 0, 1):
        for pc in _PENTA:
            c = base + octv * 12 + pc
            d = abs(c - m)
            if d < best_d:
                best, best_d = c, d
    return max(21, min(108, best))


def render_signature(mapping: dict, seconds: float = 2.4, out_wav: str = None,
                     image_path: str = None) -> dict:
    """五段垂直轮廓的短乐句（2.4s）。没有图片时退回旧的和弦。"""
    from pathlib import Path as _P

    if not image_path or not _P(image_path).exists():
        return _render_signature_chord(mapping, seconds, out_wav)

    import cv2

    data = np.fromfile(image_path, dtype=np.uint8)
    bgr = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if bgr is None:
        return _render_signature_chord(mapping, seconds, out_wav)
    h, w = bgr.shape[:2]
    sm = cv2.resize(bgr, (240, max(1, int(h * 240 / w))), interpolation=cv2.INTER_AREA)
    rgb01 = np.clip(sm[:, :, ::-1].astype(np.float32) / 255.0, 0, 1)
    L = cv2.cvtColor(rgb01, cv2.COLOR_RGB2LAB)[:, :, 0]
    S = cv2.cvtColor(rgb01, cv2.COLOR_RGB2HSV)[:, :, 1]

    bands = []
    for i in range(5):
        sl = slice(i * L.shape[0] // 5, (i + 1) * L.shape[0] // 5)
        bands.append((float(L[sl].mean()), float(S[sl].mean())))
    mean_l = float(np.mean([b[0] for b in bands]))
    mean_s = float(np.mean([b[1] for b in bands]))

    p = mapping["params"]
    target_hz = float(p["brightness_target_hz"])
    target_db = float(p["loudness_target_db"])

    # 音区由整幅画的明度决定（暗画更低），旋律由每段偏离均值的多少决定（形状）
    base = _snap_penta(45.0 + (mean_l - 30.0) / 50.0 * 12.0)
    step = min(0.40, (seconds - 0.45) / 5.0)
    n = int(SR * seconds)
    mix = np.zeros(n + SR)
    notes = []
    for i, (bl, bs) in enumerate(bands):
        off = float(np.clip((bl - mean_l) * 0.55, -9.0, 9.0))
        midi = _snap_penta(base + off)
        f0 = midi_to_hz(midi)
        ratio = max(1.0, target_hz / max(1.0, f0))
        p_decay = _solve_p(min(ratio, _centroid_ratio(0.0)))
        amp = 0.34 + 0.40 * float(np.clip((bs - 0.1) / 0.7, 0.0, 1.0))
        seg = _tone(f0, step * 2.1, p_decay, amp)
        a = max(1, int(SR * 0.006))
        seg[:a] *= np.linspace(0, 1, a)
        i0 = int(i * step * SR)
        mix[i0:i0 + seg.size] += seg[: max(0, mix.size - i0)]
        notes.append({"band": i, "midi": midi, "hz": round(f0, 2),
                      "L": round(bl, 1), "note": p.get("pitch_note", ""),
                      "offset_semitones": round(off, 2)})

    # 一条很轻的低音托底（整幅画的主音），只给身体感，不参与辨识
    root = _tone(midi_to_hz(max(28, base - 12)), seconds * 0.95, 1.05, 0.11)
    mix[: root.size] += root[: max(0, mix.size)]

    mix = mix[:n]
    # 电平对齐：整段（含音间衰减）的 RMS 要落在 R2 的目标上，否则页面上
    # "规则命中目标"的说法会和这个签名自相矛盾。软限幅后迭代一次。
    peak = float(np.abs(mix).max()) or 1.0
    mix = mix / peak * TARGET_PEAK
    for _ in range(3):
        cur_db = 20.0 * math.log10(max(1e-9, float(np.sqrt((mix ** 2).mean()))))
        mix *= 10 ** ((target_db - cur_db) / 20.0)
        if float(np.abs(mix).max()) > 0.995:
            mix = np.tanh(mix)
        else:
            break
    fade = min(int(SR * 0.015), n // 4)
    if fade:
        r = np.linspace(0, 1, fade)
        mix[:fade] *= r
        mix[-fade:] *= r[::-1]
    if out_wav:
        _write_wav(out_wav, mix)
    return {"notes": notes, "mode": "bands", "mean_L": round(mean_l, 2),
            "mean_S": round(mean_s, 3), "base_midi": base, "seconds": round(seconds, 2),
            "wav_url": f"/sig/{_P(out_wav).name}" if out_wav else None}


def _render_signature_chord(mapping: dict, seconds: float = 2.4, out_wav: str = None) -> dict:
    """旧版：根音 + 五度 + 八度。保留作无图时的回退。"""
    p = mapping["params"]
    anchor = float(p["pitch_anchor_midi"])
    target_hz = float(p["brightness_target_hz"])
    target_db = float(p["loudness_target_db"])
    n = int(SR * seconds)
    mix = np.zeros(n + SR)
    notes = []
    for i, off in enumerate((0.0, 7.0, 12.0)):
        m_note = int(round(max(21, min(108, anchor + off))))
        f0 = midi_to_hz(m_note)
        ratio = max(1.0, target_hz / max(1.0, f0))
        p_decay = _solve_p(min(ratio, _centroid_ratio(0.0)))
        seg = _tone(f0, seconds * 0.9, p_decay, 0.9 / (1 + i * 0.55))
        mix[: seg.size] += seg
        notes.append({"midi": m_note, "hz": round(f0, 2), "decay_exponent": round(p_decay, 2)})
    mix = mix[:n]
    peak = float(np.abs(mix).max()) or 1.0
    mix = mix / peak * TARGET_PEAK
    cur_db = 20.0 * math.log10(max(1e-9, float(np.sqrt((mix ** 2).mean()))))
    mix *= 10 ** ((target_db - cur_db) / 20.0)
    if float(np.abs(mix).max()) > 0.999:
        mix = mix / float(np.abs(mix).max()) * 0.999
    fade = min(int(SR * 0.02), n // 4)
    if fade:
        r = np.linspace(0, 1, fade)
        mix[:fade] *= r
        mix[-fade:] *= r[::-1]
    if out_wav:
        _write_wav(out_wav, mix)
    return {"notes": notes, "mode": "chord", "seconds": round(seconds, 2),
            "wav_url": f"/sig/{_P(out_wav).name}" if out_wav else None}

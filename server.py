#!/usr/bin/env python3
"""
server.py — 颜色→音乐 作品集 后端 (Flask)

提供 API 并托管 React 构建产物, 单端口运行。

路由:
  GET  /                     前端页面(React dist)
  GET  /api/gallery          画作列表(10 幅预置)
  GET  /api/artwork/<id>     单幅完整数据: 画作信息 + 颜色 + AI 情感 + prompt
  POST /api/analyze          上传新图 -> 颜色分析 + Gemini 情感(会消耗 Gemini 额度)
  GET  /img/<name>           画作原图
  GET  /audio/<name>         生成的音频
  POST /api/generate         生成音乐(默认禁用, 需显式开启且用户确认)

安全:
  · 所有 API key 仅在后端, 前端不可见
  · /api/generate 默认关闭(ENABLE_MUSIC_API=False), 不会消耗 Suno 额度
"""

import os
import io
import re
import sys
import json
import time
import uuid
import base64
import threading
import numpy as np
from pathlib import Path

from flask import Flask, request, jsonify, send_from_directory, send_file, Response
from PIL import Image

import gate

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))


def _load_dotenv():
    """读取 .env (优先用 python-dotenv, 没有则简易解析)"""
    env = BASE / ".env"
    if not env.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env)
        return
    except Exception:
        pass
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()

from color_extractor import (load_and_preprocess, extract_color_metrics,
                             rgb_to_lab, rgb_to_hsv)
from emotion_model import color_metrics_to_emotion
from suno_prompt import build_suno_prompt
import mapping_rules
import cv2
import artwork_match

# ── 目录 ────────────────────────────────────────────────────────────────
# 画作目录: 优先读环境变量, 便于在不同机器上部署
IMG_DIR = Path(os.environ.get(
    "ARTWORK_DIR",
    str(BASE / "artworks")
)).expanduser()
if not IMG_DIR.is_absolute():
    IMG_DIR = BASE / IMG_DIR
DIST = BASE / "frontend" / "dist"
AUDIO_DIR = BASE / "outputs" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

GALLERY_F = BASE / "gallery.json"
READINGS_F = BASE / "content" / "readings.json"
AI_CACHE_F = BASE / "ai_emotion_cache.json"
PROMPTS_F = BASE / "outputs" / "prompts.json"
MUSIC_PROMPTS_F = BASE / "outputs" / "music_prompts.json"
AUDIO_MEAS_F = BASE / "outputs" / "audio_measured.json"

# ── 音乐 API 开关: 默认关闭, 绝不自动消耗额度 ─────────────────────────────
ENABLE_MUSIC_API = os.environ.get("ENABLE_MUSIC_API", "false").lower() == "true"

# ── 音乐风格映射: 按年代 / 流派决定 ─────────────────────────────────────
# 用于提示 Gemini 生成符合画作时代背景的音乐风格
# 每个流派: label(风格名) + hint(要什么) + avoid(明确不要什么)
# avoid 很关键: 仅写"要什么"时模型常滑回通用的电影配乐/古典弦乐写法,
# 必须显式排除, 否则 1957 的罗斯科会生成浪漫派管弦乐。
ERA_STYLE = {
    "Post-Impressionism": {
        "label": "Late Romantic / Impressionist orchestral",
        "hint": "Late-Romantic orchestral palette in the spirit of Debussy and "
                "Ravel: whole-tone and modal colour, rich string sonorities, "
                "harp and woodwind timbres, rubato phrasing.",
        "avoid": "No synthesizers. No drum kit. No cinematic trailer build. "
                 "No pop song form. No electronic textures.",
    },
    "Fauvism": {
        "label": "Early Modern French orchestral",
        "hint": "Early-20th-century French orchestral language: bold primary-colour "
                "instrumentation, brass and woodwind in vivid blocks, modal "
                "harmony with unresolved colour, dance-like rhythmic drive.",
        "avoid": "No synthesizers. No ambient pads. No minimalism. "
                 "No film-score swelling. No electronic drums.",
    },
    "American Modernism": {
        "label": "Early 20th-century American lyrical",
        "hint": "Early American modernism (Ives / Copland strain): lyrical "
                "chamber-orchestral writing, open fifths and quartal harmony, "
                "transparent texture, gentle asymmetric metre, pastoral winds.",
        "avoid": "No synthesizers. No ambient drone. No epic percussion. "
                 "No Hollywood orchestration. No electronic textures.",
    },
    "Abstract Expressionism": {
        "label": "Second Viennese School / atonal expressionist",
        "hint": "Expressionist idiom of the 1910s (Schoenberg / Webern): high "
                "chromatic dissonance, atonality, extreme dynamic contrasts, "
                "Klangfarbenmelodie, violent registral leaps.",
        "avoid": "NO tonal harmony. NO hummable melody. NO romantic string "
                 "themes. No synthesizers. No steady beat. Nothing pretty or "
                 "background-music-like.",
    },
    "Bauhaus Modernism": {
        "label": "Neoclassical / modernist chamber",
        "hint": "1920s modernist neoclassicism: clear contrapuntal lines, chamber "
                "orchestra, mechanistic ostinati, bitonal clashes, dry precise "
                "articulation, jazz-tinged rhythms.",
        "avoid": "No romantic rubato. No lush string washes. No synthesizers. "
                 "No ambient texture. No film-score sentiment.",
    },
    "Color Field Painting": {
        "label": "Post-war avant-garde / minimalist drone",
        "hint": "Post-war avant-garde minimalism in the spirit of Morton Feldman: "
                "very slow harmonic drift, sustained soft dynamics, isolated "
                "sustained tones, sparse events, wide spatial reverberance. "
                "Think sustained frequencies breathing, not melody developing.",
        "avoid": "CRITICAL — this is NOT romantic orchestral music. "
                 "NO melody. NO tonal chord progression. NO crescendo. "
                 "NO full orchestra. NO brass swells. NO film-score climax. "
                 "NO rhythmic drive. NO percussion. "
                 "Use sustained tones / drone / sparse isolated attacks only. "
                 "Do not describe a narrative arc or emotional journey.",
    },
    "Op Art": {
        "label": "Minimalist process music / analog electronic",
        "hint": "1960s minimalist process music (Reich / Riley) and analog "
                "electronic textures: phasic repetition, gradual phase shifting, "
                "modular synthesizer timbres, mallet percussion, mechanical "
                "pulsation, no rubato.",
        "avoid": "NO orchestral strings. NO romantic harmony. NO rubato. "
                 "NO film score. NO melody-led development. "
                 "Repetition and process must remain the structural principle.",
    },
    "Lyrical Abstraction": {
        "label": "Post-war European avant-garde",
        "hint": "Post-war European avant-garde: free orchestral gesture, "
                "calligraphic melodic lines, controlled aleatoric passages, "
                "wide dynamic extremes, resonance-driven form.",
        "avoid": "No tonal-pop harmony. No synthesizers. No ambient chillout. "
                 "No steady groove. No Hollywood build.",
    },
}

# 康定斯基两幅年代不同: 1911 属表现主义, 1925 属包豪斯现代主义
KANDINSKY_YEAR_STYLE = {
    "1911": "Abstract Expressionism",
    "1925": "Bauhaus Modernism",
}


# AI 可能返回字典外的流派名, 做模糊匹配
MOVEMENT_ALIASES = {
    "abstract expressionism": "Abstract Expressionism",
    "expressionism": "Abstract Expressionism",
    "color field": "Color Field Painting",
    "colour field": "Color Field Painting",
    "color field painting": "Color Field Painting",
    "post-painterly abstraction": "Color Field Painting",
    "minimalism": "Color Field Painting",
    "op art": "Op Art",
    "optical art": "Op Art",
    "post-impressionism": "Post-Impressionism",
    "post impressionism": "Post-Impressionism",
    "impressionism": "Post-Impressionism",
    "fauvism": "Fauvism",
    "fauve": "Fauvism",
    "american modernism": "American Modernism",
    "precisionism": "American Modernism",
    "lyrical abstraction": "Lyrical Abstraction",
    "art informel": "Lyrical Abstraction",
    "tachisme": "Lyrical Abstraction",
    "bauhaus": "Bauhaus Modernism",
    "bauhaus modernism": "Bauhaus Modernism",
    "constructivism": "Bauhaus Modernism",
    "suprematism": "Bauhaus Modernism",
    "cubism": "Bauhaus Modernism",
    "de stijl": "Bauhaus Modernism",
    "surrealism": "Lyrical Abstraction",
}


def get_era_style(artwork: dict) -> dict:
    """按年代/流派返回音乐风格指导(含模糊匹配)"""
    movement = (artwork.get("movement") or "").strip()
    year = (artwork.get("year") or "").strip()

    # 康定斯基特例: 按年代细分
    if "Kandinsky" in (artwork.get("artist") or "") and year in KANDINSKY_YEAR_STYLE:
        movement = KANDINSKY_YEAR_STYLE[year]
    else:
        # 精确匹配
        if movement in ERA_STYLE:
            pass
        else:
            # 模糊匹配: 小写包含
            # 注意: 空字符串会被 "ml in alias" 命中任意流派, 必须先判空
            ml = movement.lower()
            matched = None
            if ml:
                for alias, canon in MOVEMENT_ALIASES.items():
                    if alias in ml or (len(ml) >= 6 and ml in alias):
                        matched = canon
                        break
            movement = matched or ""

    return ERA_STYLE.get(movement, {
        "label": "Contemporary instrumental",
        "hint": "Contemporary instrumental writing matching the painting's emotional reading.",
        "avoid": "No vocals. No pop song structure.",
    })


# ── 数据加载 ────────────────────────────────────────────────────────────
def load_json(p: Path, default=None):
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def dominant_color_hex(rgb: np.ndarray) -> str:
    """主色 hex: 归一化 + 提亮, 避免纯黑"""
    mean = np.mean(rgb.reshape(-1, 3), axis=0)
    r, g, b = mean
    mx = max(r, g, b)
    if mx < 1e-3:
        return "#222222"
    r, g, b = r / mx, g / mx, b / mx
    r, g, b = r * 0.6 + 0.25, g * 0.6 + 0.25, b * 0.6 + 0.25
    return "#%02X%02X%02X" % tuple((np.clip([r, g, b], 0, 1) * 255).astype(int))


def extract_palette(rgb: np.ndarray, k: int = 5) -> list:
    """提取主色板: 3D 直方图取 Top-K"""
    q = (rgb * 24).astype(int)
    keys = q.reshape(-1, 3)
    uniq, counts = np.unique(keys, axis=0, return_counts=True)
    order = np.argsort(-counts)[:k]
    total = counts.sum()
    out = []
    for i in order:
        c = uniq[i] / 24.0
        r, g, b = (np.clip(c, 0, 1) * 255).astype(int)
        out.append({
            "rgb": f"rgb({r},{g},{b})",
            "hex": "#%02X%02X%02X" % (r, g, b),
            "ratio": round(float(counts[i]) / total, 4),
        })
    return out


app = Flask(__name__, static_folder=None)


# ── API ────────────────────────────────────────────────────────────────
@app.route("/api/gallery")
def api_gallery():
    """画作列表"""
    gallery = load_json(GALLERY_F, [])
    items = []
    for g in gallery:
        f = g.get("file", "")
        if not (IMG_DIR / f).exists():
            continue
        items.append({
            "id": g.get("id", ""),
            "file": f,
            "artist": g.get("artist", ""),
            "title": g.get("title", ""),
            "year": g.get("year", ""),
            "movement": g.get("movement", ""),
            "thumb": f"/img/{f}",
            "thumb_small": f"/thumb/{f}",
        })
    return jsonify(items)


@app.route("/api/artwork/<aid>")
def api_artwork(aid):
    """单幅完整数据: 画作信息 + 颜色分析 + AI 情感 + prompt"""
    gallery = load_json(GALLERY_F, [])
    g = next((x for x in gallery if x.get("id") == aid or x.get("file") == aid), None)
    if not g:
        return jsonify({"error": "artwork not found"}), 404

    f = g.get("file", "")
    p = IMG_DIR / f
    if not p.exists():
        return jsonify({"error": "image not found"}), 404

    prompts = load_json(PROMPTS_F, {})
    ai_cache = load_json(AI_CACHE_F, {})
    music_prompts = load_json(MUSIC_PROMPTS_F, {})
    readings = load_json(READINGS_F, {})

    d = prompts.get(f, {})
    ai = ai_cache.get(f, {})
    if "error" in ai:
        ai = {}
    mp = music_prompts.get(f, {})

    # 颜色(实时计算, 按 mtime 缓存)
    rgb = load_and_preprocess(str(p))
    m, emo = _metrics_cached(p, rgb)

    # 规则层: 预置画作没有 ai_emotion_cache 时, 用 prompts.json 里存下的 AI 快照
    ai_for_rules = ai or {k: d.get(k) for k in
                          ("mood", "valence", "arousal", "tension", "narrative", "musical_hint")
                          if d.get(k) not in (None, "")}
    mapping_obj = mapping_rules.build(m, ai_for_rules)
    sp_now = build_suno_prompt(m, emo, ai_for_rules or None, mapping=mapping_obj, image_path=str(p))

    era = get_era_style(g)

    resp = {
        "id": g.get("id", ""),
        "file": f,
        "image": f"/img/{f}",
        "artist": g.get("artist", ""),
        "title": g.get("title", ""),
        "year": g.get("year", ""),
        "medium": g.get("medium", ""),
        "dimensions": g.get("dimensions", ""),
        "movement": g.get("movement", ""),
        # 音乐风格(按年代/流派)
        "era_style": era,
        # AI 情感
        "mood": ai.get("mood", d.get("mood", "")),
        "valence": ai.get("valence", d.get("valence", 0)),
        "arousal": ai.get("arousal", d.get("arousal", 0)),
        "tension": ai.get("tension", d.get("tension", 0)),
        "narrative": ai.get("narrative", d.get("narrative", "")),
        # 作者视角的作品解读（为什么是这幅 / 3 条看这里 / 翻译失败在哪）
        "reading": readings.get(g.get("id", "")) or None,
        "musical_hint": ai.get("musical_hint", d.get("musical_hint", "")),
        "ai_available": bool(ai) or bool(d.get("source")),
        # 颜色
        "dominant_color": dominant_color_hex(rgb),
        "palette": extract_palette(rgb),
        "dominant_hue": m["dominant_hue"].get("label_en", ""),
        "timbre": m["dominant_hue"].get("timbre_en", ""),
        "mode": m["warm_cold"].get("mode_en", ""),
        "pitch": m["brightness"].get("pitch_range_en", ""),
        "mean_S": m["saturation"]["mean_S"],
        "mean_V": m["brightness"]["mean_V"],
        "warm_ratio": m["warm_cold"]["warm_ratio_W"],
        "rgi": m["red_green_index"]["RGI_lab"],
        "bpm": sp_now["bpm"],
        # prompt
        "music_prompt": mp.get("music_prompt", ""),
        # v2 = 按新规则层重新生成的 prompt（与 Mapping 面板一致）
        "music_prompt_source": ("gemini" if mp.get("rules_version") == "v2"
                                else ("gemini-cached" if mp.get("music_prompt") else "")),
        "style_en": sp_now["style_en"],
        # 文献规则层
        "mapping": mapping_obj,
        # 音频(下面自动发现后填充)
        "audio": None,
    }

    # 自动发现已生成的音频(可能不止一首)
    # 命名形如 "<title-slug>.mp3" / "_1" / "_2"
    # 兼容历史文件带艺术家前缀的情况: 用"包含 slug"匹配
    found = _find_audio(g)
    if found:
        resp["audio"] = found[0]
        resp["audio_urls"] = found
        # 已生成音乐的实测值（响度/频谱重心），用于和规则目标并列展示
        meas_all = load_json(AUDIO_MEAS_F, {})
        resp["suno_measured"] = [
            {"file": f, **meas_all[f]} for f in
            (u.rsplit("/", 1)[-1] for u in found) if f in meas_all
        ]
    return jsonify(resp)


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", s or "").strip("_").lower()


def _find_audio(g: dict) -> list:
    """按画作标题查找已生成的音频文件"""
    title = g.get("title", "")
    artist = g.get("artist", "")
    t_slug = _slug(title)
    if not t_slug:
        return []
    a_slug = _slug(artist)

    cands = [t_slug]
    if a_slug:
        cands.append(f"{a_slug}_{t_slug}")

    found = []
    for p in sorted(AUDIO_DIR.glob("*.mp3")):
        stem = p.stem.lower()
        # 精确: stem 等于 slug 或 slug_序号
        for c in cands:
            if stem == c or re.fullmatch(re.escape(c) + r"_?\d*", stem):
                found.append(p)
                break
        else:
            # 兜底: 文件名包含标题 slug
            base_stem = re.sub(r"_\d+$", "", stem)
            if t_slug in stem or (len(base_stem) >= 24 and any(c.startswith(base_stem) for c in cands)):
                found.append(p)

    # 按 _1/_2 序号排序, 保证播放顺序稳定
    found.sort(key=lambda p: p.name)
    return [f"/audio/{p.name}" for p in found]


@app.route("/img/<path:name>")
def img(name):
    return send_from_directory(str(IMG_DIR), name)


@app.route("/thumb/<path:name>")
def thumb(name):
    """缩略图(加速列表加载)"""
    try:
        p = IMG_DIR / name
        im = Image.open(p).convert("RGB")
        im.thumbnail((300, 300), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=82)
        buf.seek(0)
        return Response(buf.getvalue(), mimetype="image/jpeg")
    except Exception as e:
        return jsonify({"error": str(e)}), 404


@app.route("/audio/<path:name>")
def audio(name):
    return send_from_directory(str(AUDIO_DIR), name)


def _color_block(rgb, m, sp):
    """颜色分析结果(两阶段中的第一阶段)"""
    return {
        "dominant_color": dominant_color_hex(rgb),
        "palette": extract_palette(rgb),
        "dominant_hue": m["dominant_hue"].get("label_en", ""),
        "timbre": m["dominant_hue"].get("timbre_en", ""),
        "mode": m["warm_cold"].get("mode_en", ""),
        "pitch": m["brightness"].get("pitch_range_en", ""),
        "mean_S": m["saturation"]["mean_S"],
        "mean_V": m["brightness"]["mean_V"],
        "warm_ratio": m["warm_cold"]["warm_ratio_W"],
        "rgi": m["red_green_index"]["RGI_lab"],
        "bpm": sp["bpm"],
        "style_en": sp["style_en"],
    }


# ── 上传会话: token -> 颜色分析结果 (进程内, 供第二阶段复用) ────────────────
ANALYSIS: dict = {}
SESSION_TTL = 60 * 60  # 1 小时

# ── 感知哈希索引: 上传图先对到已有作品, 命中就用权威元数据 ────────────────
_MATCH_IDX = None


def _match_artwork(bgr):
    """返回 (gallery_entry|None, hamming_distance|None)"""
    global _MATCH_IDX
    try:
        if _MATCH_IDX is None:
            _MATCH_IDX = artwork_match.build_index(load_json(GALLERY_F, []), IMG_DIR)
            print(f"[match] 建立哈希索引: {len(_MATCH_IDX)} 幅", flush=True)
        small = cv2.resize(bgr, (256, 256), interpolation=cv2.INTER_AREA)
        return artwork_match.match(small, _MATCH_IDX)
    except Exception as e:
        print(f"[match] 跳过: {e}", flush=True)
        return None, None


def _prune():
    """清理: 过期上传会话 + 6 小时前的临时图（原版两者都只增不减）"""
    now = time.time()
    for k, v in list(ANALYSIS.items()):
        if now - float(v.get("t", now)) > SESSION_TTL:
            ANALYSIS.pop(k, None)
    try:
        for p in (BASE / "outputs" / "tmp").glob("*.jpg"):
            if now - p.stat().st_mtime > 6 * 3600:
                p.unlink()
    except Exception:
        pass


# 颜色指标按 (路径, mtime) 缓存：/api/artwork 每次重算要 0.4s
_METRICS_CACHE: dict = {}


def _metrics_cached(path, rgb):
    """按 (路径, mtime) 缓存颜色指标 + 规则情感（/api/artwork 每次重算要 0.4s）"""
    try:
        key = (str(path), round(path.stat().st_mtime, 3))
    except Exception:
        key = (str(path), 0)
    if key not in _METRICS_CACHE:
        if len(_METRICS_CACHE) > 64:
            _METRICS_CACHE.clear()
        m = extract_color_metrics(rgb)
        _METRICS_CACHE[key] = (m, color_metrics_to_emotion(m))
    return _METRICS_CACHE[key]


def _prompt_block(m: dict, emo: dict, sp: dict) -> dict:
    """给 music_prompt_ai.build_color_block 用的扁平字段块"""
    return {
        "dominant_hue_en": m["dominant_hue"].get("label_en", ""),
        "timbre_en": m["dominant_hue"].get("timbre_en", ""),
        "mode_en": m["warm_cold"].get("mode_en", ""),
        "pitch_en": m["brightness"].get("pitch_range_en", ""),
        "mean_S": m["saturation"]["mean_S"],
        "mean_V": m["brightness"]["mean_V"],
        "warm_ratio": m["warm_cold"]["warm_ratio_W"],
        "rgi": m["red_green_index"]["RGI_lab"],
        "bpm": sp.get("bpm", 90),
    }


def _build_music_prompt(flat: dict, m: dict, emo: dict, ai: dict, era: dict,
                        api_key: str, mapping: dict = None, image_path: str = None) -> tuple:
    """统一出口: 优先 Gemini 转译, 失败/无 key 时用规则模板兜底。
    返回 (prompt, source)。source ∈ {gemini, rule-template}
    """
    if ai and api_key:
        try:
            import music_prompt_ai
            txt = music_prompt_ai.translate(flat, ai, api_key, era=era, mapping=mapping)
            if txt and len(txt) > 40:
                return txt.strip(), "gemini"
        except Exception as e:
            print(f"[prompt] Gemini 转译失败, 回退规则模板: {e}", flush=True)

    sp = build_suno_prompt(m, emo, ai or None, mapping=mapping, image_path=image_path)
    # 规则模板: style 行 + 情绪/叙事, 足够驱动 Suno, 且可解释
    txt = sp["full_en"]
    if era.get("label") and era["label"] not in txt:
        txt = f"[{era['label']}] " + txt
    return txt, "rule-template"


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """第一阶段: 上传 -> 颜色分析 (本地计算, 快, 不消耗任何 API 额度)
    返回 token, 供第二阶段 /api/emotion 使用
    """
    if "file" not in request.files:
        return jsonify({"error": "no file"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "empty filename"}), 400

    _prune()          # 顺手清理过期会话与临时图

    try:
        raw = f.read()
        img = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as e:
        return jsonify({"error": f"invalid image: {e}"}), 400

    # 先用感知哈希对到已有作品（确定性，比 AI 识别可靠）
    matched, match_d = None, None
    try:
        bgr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        matched, match_d = _match_artwork(bgr)
    except Exception as e:
        print(f"[analyze] match failed: {e}", flush=True)

    tmp_dir = BASE / "outputs" / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    tmp = tmp_dir / f"{token}.jpg"
    img.save(tmp, format="JPEG", quality=92)

    rgb = load_and_preprocess(str(tmp))
    m = extract_color_metrics(rgb)
    emo = color_metrics_to_emotion(m)
    mp = mapping_rules.build(m, None)          # 文献规则层 (无 AI 时语义类规则取中性)
    sp = build_suno_prompt(m, emo, None, mapping=mp, image_path=str(tmp))

    # 存会话: 第二阶段复用, 避免重复算颜色 / 也用于生成记录
    ANALYSIS[token] = {
        "t": time.time(),
        "filename": f.filename,
        "metrics": m,
        "emotion": emo,
        "style": sp,
        "mapping": mp,
        "matched": matched,
        "match_distance": match_d,
        "flat": _prompt_block(m, emo, sp),
    }

    stem = Path(f.filename).stem
    # 中文/空文件名不适合作为展示标题, 标记待 AI 生成
    has_cjk = bool(re.search(r"[\u4e00-\u9fff]", stem))

    out = _color_block(rgb, m, sp)
    out["mapping"] = mp
    out.update({
        "token": token,
        # 命中已有作品 → 用 gallery.json 的权威元数据（AI 识别可能认错）
        "title": matched["title"] if matched else ("" if has_cjk else stem),
        "title_from_filename": (not has_cjk) and not matched,
        "needs_title": has_cjk and not matched,
        "artist": matched.get("artist", "Unknown") if matched else "Unknown",
        "year": matched.get("year", "") if matched else "",
        "medium": matched.get("medium", "") if matched else "",
        "dimensions": matched.get("dimensions", "") if matched else "",
        "movement": matched.get("movement", "") if matched else "",
        "matched_id": matched.get("id", "") if matched else "",
        "match_distance": match_d,
        "era_style": get_era_style(matched) if matched else {
            "label": "Contemporary instrumental",
            "hint": "Contemporary instrumental writing matching the artwork."},
        "music_prompt": "",
        "audio": None,
        "image": None,          # 前端用本地 objectURL
        # 规则模型兜底, 供 AI 不可用时使用
        "fallback": {
            "narrative": emo.get("narrative", ""),
            "valence": emo.get("valence", 0),
            "arousal": emo.get("arousal", 0),
            "tension": 0.0,
        },
    })

    # 输入范围闸门：超出支持范围就明确说，不让下游给出一份看起来成立的结果
    try:
        out["gate"] = gate.evaluate(str(tmp))
    except Exception as e:
        out["gate"] = {"ok": True, "verdict": "unchecked", "failures": [], "checks": [], "metrics": {}}
        print(f"[gate] failed: {e}", flush=True)

    return jsonify(out)


@app.route("/api/emotion", methods=["POST"])
def api_emotion():
    """第二阶段: Gemini 情感分析 + 音乐 prompt 生成 (P0-1 修复点)

    无 GEMINI_API_KEY 或 AI 失败时不再中断流程:
    仍然用规则模板产出一份 music_prompt, 保证"上传任意图 → 能出歌"。
    响应里 music_prompt_source 标明是 gemini 还是 rule-template。
    """
    data = request.get_json(silent=True) or {}
    token = (data.get("token") or "").strip()

    if not token or not re.fullmatch(r"[0-9a-f]{32}", token):
        return jsonify({"error": "invalid token"}), 400

    tmp = BASE / "outputs" / "tmp" / f"{token}.jpg"
    sess = ANALYSIS.get(token)

    if sess is None:
        # 进程重启后内存会话丢失 -> 从磁盘重建, 不要求用户重传
        if not tmp.exists():
            return jsonify({"error": "session expired, please re-upload"}), 404
        try:
            rgb = load_and_preprocess(str(tmp))
            m = extract_color_metrics(rgb)
            emo = color_metrics_to_emotion(m)
            mp0 = mapping_rules.build(m, None)
            sp = build_suno_prompt(m, emo, None, mapping=mp0, image_path=str(tmp))
            sess = {"t": time.time(), "filename": tmp.name, "metrics": m,
                    "emotion": emo, "style": sp, "mapping": mp0,
                    "flat": _prompt_block(m, emo, sp)}
            ANALYSIS[token] = sess
        except Exception as e:
            return jsonify({"error": f"analysis unavailable: {e}"}), 500

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    ai, ai_error = {}, ""

    if not api_key:
        ai_error = "GEMINI_API_KEY not set"
    else:
        try:
            import ai_vision
            # 一次调用: 作品识别 + 情感判断
            ai = ai_vision.analyze_full(str(tmp), api_key=api_key) or {}
        except Exception as e:
            ai_error = str(e)

    # 缓存, 避免重复分析
    if ai:
        try:
            cache = load_json(AI_CACHE_F, {})
            cache[f"upload_{token}"] = ai
            AI_CACHE_F.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    # 流派 -> 音乐风格 (哈希命中的权威元数据优先, 否则 AI 识别)
    matched = sess.get("matched") or {}
    era = get_era_style(matched or {
        "artist": ai.get("artist", ""),
        "movement": ai.get("movement", ""),
        "year": ai.get("year", ""),
    })

    # 规则层: 有 AI 就用 AI 的 valence/arousal/tension 驱动 design 规则
    mp = mapping_rules.build(sess["metrics"], ai)
    sess["mapping"] = mp

    _tmp_img = BASE / "outputs" / "tmp" / f"{token}.jpg"
    music_prompt, prompt_source = _build_music_prompt(
        sess["flat"], sess["metrics"], sess["emotion"], ai, era, api_key, mapping=mp,
        image_path=str(_tmp_img) if _tmp_img.exists() else None,
    )
    sess["music_prompt"] = music_prompt
    sess["prompt_source"] = prompt_source
    sess["ai"] = ai
    _save_record(token)          # P1-6: 分析完成即留档（不必等 saliency/preview）

    resp = {
        "ai_available": bool(ai),
        "ai_error": ai_error,
        # 作品识别: 哈希命中优先（gallery.json 权威），否则用 AI 判断
        "title": matched.get("title") or ai.get("title", ""),
        "artist": matched.get("artist") or ai.get("artist", "Unknown"),
        "year": matched.get("year") or ai.get("year", ""),
        "movement": matched.get("movement") or ai.get("movement", ""),
        "medium": matched.get("medium") or ai.get("medium", ""),
        "identified": bool(matched) or ai.get("identified", False),
        "identity_source": ("opencv-hash" if matched
                            else ("gemini" if ai.get("identified") else
                                  ("gemini-guess" if ai else "none"))),
        "matched_id": matched.get("id", ""),
        "match_distance": sess.get("match_distance"),
        "ai_title_guess": ai.get("title", ""),
        "ai_model": ai.get("model", ""),
        # 情感
        "mood": ai.get("mood", ""),
        "valence": ai.get("valence", 0),
        "arousal": ai.get("arousal", 0),
        "tension": ai.get("tension", 0),
        "narrative": ai.get("narrative", ""),
        "musical_hint": ai.get("musical_hint", ""),
        # 按 AI 识别的流派匹配音乐风格
        "era_style": era,
        # ⭐ 音乐 prompt: 这条链路以前断裂, 上传图永远拿不到
        "music_prompt": music_prompt,
        "music_prompt_source": prompt_source,
        # 文献规则层: 每条规则的输入/输出/参考编号
        "mapping": mp,
    }
    return jsonify(resp)


# ── 批次 C: 显著性 / 基础声音 / 生成记录 ─────────────────────────────────────
SAL_DIR = BASE / "outputs" / "saliency"
PRE_DIR = BASE / "outputs" / "preview"
REC_DIR = BASE / "outputs" / "records"
CVD_DIR = BASE / "outputs" / "cvd"
SIG_DIR = BASE / "outputs" / "sig"
for _d in (SAL_DIR, PRE_DIR, REC_DIR, CVD_DIR, SIG_DIR):
    _d.mkdir(parents=True, exist_ok=True)

_RULER_CACHE = {"key": None, "data": None}


def _resolve(payload: dict) -> tuple:
    """token 或 gallery id → (image_path, key, metrics, emo, mapping, ai)"""
    token = (payload.get("token") or "").strip()
    aid = (payload.get("id") or "").strip()

    if token:
        if not re.fullmatch(r"[0-9a-f]{32}", token):
            raise ValueError("invalid token")
        img = BASE / "outputs" / "tmp" / f"{token}.jpg"
        if not img.exists():
            raise FileNotFoundError("session expired, please re-upload")
        sess = ANALYSIS.get(token) or {}
        if sess.get("mapping"):
            return (img, token, sess["metrics"], sess["emotion"],
                    sess["mapping"], sess.get("ai") or {})
        rgb = load_and_preprocess(str(img))
        m = extract_color_metrics(rgb)
        emo = color_metrics_to_emotion(m)
        mp = mapping_rules.build(m, None)
        ANALYSIS[token] = {"t": time.time(), "filename": img.name, "metrics": m,
                           "emotion": emo, "mapping": mp,
                           "flat": _prompt_block(m, emo, build_suno_prompt(m, emo, None, mapping=mp, image_path=str(img)))}
        return img, token, m, emo, mp, {}

    if aid:
        gallery = load_json(GALLERY_F, [])
        g = next((x for x in gallery if x.get("id") == aid or x.get("file") == aid), None)
        if not g:
            raise LookupError("artwork not found")
        img = IMG_DIR / g.get("file", "")
        if not img.exists():
            raise FileNotFoundError("image not found")
        d = load_json(PROMPTS_F, {}).get(g.get("file", ""), {})
        ai = {k: d.get(k) for k in ("mood", "valence", "arousal", "tension",
                                    "narrative", "musical_hint") if d.get(k) not in (None, "")}
        rgb = load_and_preprocess(str(img))
        m = extract_color_metrics(rgb)
        emo = color_metrics_to_emotion(m)
        mp = mapping_rules.build(m, ai)
        return img, aid, m, emo, mp, ai

    raise ValueError("token or id required")


def _save_record(key: str):
    """P1-6: 原图 + 视觉数据 + 映射 + prompt + 音频 + 规则编号, 一处留档"""
    sess = ANALYSIS.get(key) or {}
    rec = {
        "key": key,
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "image": sess.get("filename", ""),
        # 作品身份来自哪里: 感知哈希(权威) / Gemini / 无
        "identity": {
            "source": "opencv-hash" if sess.get("matched") else ("gemini" if sess.get("ai") else "none"),
            "matched_id": (sess.get("matched") or {}).get("id", ""),
            "match_distance": sess.get("match_distance"),
            "ai_title_guess": (sess.get("ai") or {}).get("title", ""),
            "ai_model": (sess.get("ai") or {}).get("model", ""),
        },
        "metrics": sess.get("metrics"),
        "mapping": sess.get("mapping"),
        "saliency": sess.get("saliency"),
        "preview": sess.get("preview"),
        "music_prompt": sess.get("music_prompt"),
        "music_prompt_source": sess.get("prompt_source"),
        "generated_audio": sess.get("generated_audio"),
        "generated_prompt": sess.get("generated_prompt"),
        "ai": sess.get("ai"),
        "refs": mapping_rules.REFS,
    }
    try:
        (REC_DIR / f"{key}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[record] save failed: {e}", flush=True)


@app.route("/api/saliency", methods=["POST"])
def api_saliency():
    """P1-1/P1-2: OpenCV 显著图 + 高显著区域局部颜色（本地计算, 不耗额度）"""
    payload = request.get_json(silent=True) or {}
    try:
        img, key, m, emo, mp, ai = _resolve(payload)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except (FileNotFoundError, LookupError) as e:
        return jsonify({"error": str(e)}), 404

    try:
        import saliency
        side = SAL_DIR / f"{key}.json"
        s = None
        # 缓存: 图没变就直接复用（显著图计算 ~0.8s，重复打开没必要重算）
        try:
            if side.exists() and side.stat().st_mtime >= img.stat().st_mtime:
                cached = json.loads(side.read_text(encoding="utf-8"))
                if cached.get("summary") and cached.get("focus_url"):
                    s = cached
        except Exception:
            s = None

        if s is None:
            s = saliency.analyze(
                str(img),
                str(SAL_DIR / f"{key}_heat.png"),
                str(SAL_DIR / f"{key}_focus.png"),
                group_l=m["brightness"].get("mean_L"),
                group_s=m["saturation"].get("mean_S"),
            )
            s["heat_url"] = f"/heat/{key}_heat.png" if s.pop("heat_file", None) else None
            s["focus_url"] = f"/focus/{key}_focus.png" if s.pop("focus_file", None) else None
            try:
                side.write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass
    except Exception as e:
        return jsonify({"error": f"saliency failed: {e}"}), 500
    ANALYSIS.setdefault(key, {}).update({"saliency": s, "metrics": m,
                                         "mapping": mp, "ai": ai})
    _save_record(key)
    return jsonify(s)


@app.route("/api/preview", methods=["POST"])
def api_preview():
    """P1-4: 规则明确的 15 秒基础声音 (MIDI + 合成器), 并对输出音频做测量"""
    payload = request.get_json(silent=True) or {}
    try:
        img, key, m, emo, mp, ai = _resolve(payload)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except (FileNotFoundError, LookupError) as e:
        return jsonify({"error": str(e)}), 404

    sess = ANALYSIS.setdefault(key, {})
    if not sess.get("mapping"):
        sess.update({"metrics": m, "emotion": emo, "mapping": mp, "ai": ai})

    regions = (sess.get("saliency") or {}).get("regions")
    if regions is None:
        try:
            import saliency
            s = saliency.analyze(
                str(img), str(SAL_DIR / f"{key}_heat.png"), str(SAL_DIR / f"{key}_focus.png"),
                group_l=m["brightness"].get("mean_L"), group_s=m["saturation"].get("mean_S"),
            )
            s["heat_url"] = f"/heat/{key}_heat.png" if s.pop("heat_file", None) else None
            s["focus_url"] = f"/focus/{key}_focus.png" if s.pop("focus_file", None) else None
            sess["saliency"] = s
            regions = s.get("regions") or []
        except Exception as e:
            print(f"[preview] saliency skipped: {e}", flush=True)
            regions = []

    seconds = float(payload.get("seconds") or 15.0)
    seconds = max(5.0, min(30.0, seconds))
    samples = sess.get("samples") or []

    # 分层试听: 4 个版本，同一段旋律逐层加规则
    if payload.get("layers"):
        try:
            import synth
            out = synth.render_layers(mp, None, max(5.0, min(15.0, float(payload.get("seconds") or 8.0))),
                                      PRE_DIR, key, image_path=str(img))
        except Exception as e:
            return jsonify({"error": f"layers failed: {e}"}), 500
        sess["layers"] = out
        _save_record(key)
        return jsonify({
            "layers": out,
            "samples": samples,
            "targets": {
                "loudness_target_db": mp["params"]["loudness_target_db"],
                "brightness_target_hz": mp["params"]["brightness_target_hz"],
                "pitch_anchor_midi": mp["params"]["pitch_anchor_midi"],
            },
            "notes": [
                "同一段动机（这幅画自己的五段轮廓，重复两遍）；差别只在响度 / 音色",
                "L1 固定 −20 dBFS，不施加 R2；L2 起才按饱和度校准",
            ],
        })

    try:
        import synth
        wav = PRE_DIR / f"{key}.wav"
        mid = PRE_DIR / f"{key}.mid"
        r = synth.render(mp, regions, seconds, str(wav), str(mid), layer=4, samples=samples)
        meas = synth.measure(str(wav))
        ver = synth.verify(meas, mp["params"])
    except Exception as e:
        return jsonify({"error": f"preview failed: {e}"}), 500

    out = {
        "wav_url": f"/preview/{key}.wav",
        "mid_url": f"/preview/{key}.mid" if r.get("mid") else None,
        "seconds": r["seconds"],
        "notes_midi": [n["midi"] for n in r["notes"]],
        "notes_detail": r["notes"],
        "region_voices": r["region_voices"],
        "measured": meas,
        "verify": ver,
        "targets": {
            "loudness_target_db": mp["params"]["loudness_target_db"],
            "brightness_target_hz": mp["params"]["brightness_target_hz"],
            "pitch_anchor_midi": mp["params"]["pitch_anchor_midi"],
        },
        "notes": [
            "MIDI 精确规定音高；响度与音色明亮度必须对音频测量，velocity 不等于响度",
            "局部区域各一条辅助声部，未做加权（P1-2）",
            "这层与 Suno 完整音乐分开呈现，Suno 不保证执行这些参数",
        ],
    }
    sess["preview"] = out
    _save_record(key)
    return jsonify(out)


@app.route("/api/record/<key>")
def api_record(key):
    """P1-6: 取留档记录"""
    if not re.fullmatch(r"[0-9a-zA-Z_\-]{1,64}", key or ""):
        return jsonify({"error": "invalid key"}), 400
    f = REC_DIR / f"{key}.json"
    if not f.exists():
        return jsonify({"error": "record not found", "hint": "先跑 /api/saliency 或 /api/preview"}), 404
    return jsonify(load_json(f, {}))


@app.route("/api/records")
def api_records():
    """全部留档索引: 时间 / 名字 / 身份来源 / anchor / prompt 来源 / 音频数"""
    gallery = {g.get("id"): g for g in load_json(GALLERY_F, [])}
    items = []
    for f in REC_DIR.glob("*.json"):
        d = load_json(f, {})
        if not d:
            continue
        p = ((d.get("mapping") or {}).get("params") or {})
        ai = d.get("ai") or {}
        ident = d.get("identity") or {}
        # 预置画作按 key 命中；上传图按哈希命中的 matched_id 反查
        g = gallery.get(str(d.get("key", ""))) or gallery.get(str(ident.get("matched_id", "")))
        # 标题优先级: 哈希命中的权威元数据 > AI 识别 > 文件名
        title = (g or {}).get("title") or ai.get("title") or d.get("image", "") or f.stem
        artist = (g or {}).get("artist") or ai.get("artist", "")
        # 老记录没有 pitch_note（字段是后加的），用 MIDI 号补算
        anchor = p.get("pitch_note", "")
        if not anchor and p.get("pitch_anchor_midi") is not None:
            try:
                anchor = mapping_rules.pitch_to_note(float(p["pitch_anchor_midi"]))
            except Exception:
                anchor = ""
        items.append({
            "key": d.get("key", f.stem),
            "saved_at": d.get("saved_at", ""),
            "image": d.get("image", ""),
            "title": title,
            "artist": artist,
            "identity": ident.get("source", ""),
            "anchor": anchor,
            "bpm": p.get("bpm", ""),
            "prompt_source": d.get("music_prompt_source", ""),
            "n_audio": len(d.get("generated_audio") or []),
            "has_saliency": bool(d.get("saliency")),
            "is_gallery": bool(g),
        })
    items.sort(key=lambda x: x["saved_at"], reverse=True)
    return jsonify({"count": len(items), "items": items})


@app.route("/api/cvd", methods=["POST"])
def api_cvd():
    """色觉模拟: 正常 / 绿盲 / 红盲 三联（本地计算）"""
    payload = request.get_json(silent=True) or {}
    try:
        img, key, m, emo, mp, ai = _resolve(payload)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except (FileNotFoundError, LookupError) as e:
        return jsonify({"error": str(e)}), 404

    try:
        import cvd
        out = cvd.generate(str(img), key, CVD_DIR)
    except Exception as e:
        return jsonify({"error": f"cvd failed: {e}"}), 500

    ANALYSIS.setdefault(key, {})["cvd"] = out
    return jsonify(out)


@app.route("/api/sample", methods=["POST"])
def api_sample():
    """点选取样: 用户指定"这块"，系统只测这一块的颜色（判断权归用户）"""
    payload = request.get_json(silent=True) or {}
    try:
        img, key, m, emo, mp, ai = _resolve(payload)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except (FileNotFoundError, LookupError) as e:
        return jsonify({"error": str(e)}), 404

    sess = ANALYSIS.setdefault(key, {})
    if payload.get("clear"):
        sess["samples"] = []
        _save_record(key)
        return jsonify({"samples": []})

    try:
        x = max(0.0, min(1.0, float(payload.get("x", 0.5))))
        y = max(0.0, min(1.0, float(payload.get("y", 0.5))))
    except Exception:
        return jsonify({"error": "x/y must be numbers in 0..1"}), 400

    data = np.fromfile(str(img), dtype=np.uint8)
    bgr = cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None
    if bgr is None:
        return jsonify({"error": "cannot read image"}), 500

    h, w = bgr.shape[:2]
    px, py = int(x * w), int(y * h)
    rad = max(5, int(0.025 * min(h, w)))
    y0, y1 = max(0, py - rad), min(h, py + rad)
    x0, x1 = max(0, px - rad), min(w, px + rad)
    patch = bgr[y0:y1, x0:x1]
    if patch.size == 0:
        return jsonify({"error": "sample outside image"}), 400

    rgb = np.clip(patch[:, :, ::-1].astype(np.float64) / 255.0, 0, 1)
    L = float(rgb_to_lab(rgb)[0].mean())
    S = float(rgb_to_hsv(rgb)[1].mean())
    mean_rgb = (rgb.reshape(-1, 3).mean(axis=0) * 255).round().astype(int).tolist()
    anchor = 36.0 + (max(0.0, min(100.0, L)) / 100.0) * 48.0

    samples = sess.setdefault("samples", [])
    s = {
        "id": len(samples) + 1,
        "x": round(x, 3), "y": round(y, 3),
        "radius_px": rad,
        "L": round(L, 1),
        "S": round(S, 3),
        "hex": "#%02X%02X%02X" % tuple(mean_rgb),
        "voice_midi": round(anchor, 1),
        "voice_note": mapping_rules.pitch_to_note(anchor),
    }
    samples.append(s)
    _save_record(key)
    return jsonify({"sample": s, "samples": samples})


@app.route("/api/ruler", methods=["GET", "POST"])
def api_ruler():
    """十幅画在同一条映射标尺上的位置（画廊/详情页共用）"""
    gallery_all = load_json(GALLERY_F, [])
    stamps = []
    for g in gallery_all:
        p = IMG_DIR / str(g.get("file", ""))
        if p.exists():
            stamps.append(f"{g.get('id')}:{int(p.stat().st_mtime)}")
    key = "|".join(stamps)
    payload = request.get_json(silent=True) or {}
    want_you = bool(payload.get("token") or payload.get("id"))
    cached = _RULER_CACHE.get("data") if _RULER_CACHE.get("key") == key else None
    if cached and not want_you:
        return jsonify(cached)

    # 有 token 时要加上「你的图」，所以缓存只用来跳过重算语料部分
    gallery = [] if cached else load_json(GALLERY_F, [])
    ai_cache = load_json(AI_CACHE_F, {})
    prompts = load_json(PROMPTS_F, {})
    items = list(cached["items"]) if cached else []
    for g in gallery:
        f = str(g.get("file", ""))
        p = IMG_DIR / f
        if not p.exists():
            continue
        try:
            rgb = load_and_preprocess(str(p))
            m, emo = _metrics_cached(p, rgb)
            d = prompts.get(f, {})
            ai = ai_cache.get(f, {})
            if "error" in ai:
                ai = {}
            ai_for_rules = ai or {k: d.get(k) for k in
                                  ("mood", "valence", "arousal", "tension", "narrative", "musical_hint")
                                  if d.get(k) not in (None, "")}
            pr = mapping_rules.build(m, ai_for_rules)["params"]
        except Exception:
            continue
        items.append({
            "id": g.get("id", ""),
            "title": g.get("title", ""),
            "artist": g.get("artist", ""),
            "thumb": g.get("thumb_small") or f"/thumb/{f}",
            "file": f,
            "mean_L": pr.get("mean_L"),
            "mean_S": pr.get("mean_S"),
            "anchor_midi": pr.get("pitch_anchor_midi"),
            "note": pr.get("pitch_note", ""),
            "loudness_db": pr.get("loudness_target_db"),
            "centroid_hz": pr.get("brightness_target_hz"),
            "bpm": pr.get("bpm"),
        })

    payload = request.get_json(silent=True) or {}
    you = None
    if payload.get("token") or payload.get("id"):
        try:
            _img, ykey, _m, _emo, ymp, _ai = _resolve(payload)
            yp = ymp["params"]
            gallery_ids = {i["id"] for i in items}
            if ykey not in gallery_ids:
                you = {
                    "id": ykey,
                    "title": payload.get("title") or "your image",
                    "artist": "",
                    "thumb": "",
                    "mean_L": yp.get("mean_L"),
                    "mean_S": yp.get("mean_S"),
                    "anchor_midi": yp.get("pitch_anchor_midi"),
                    "note": yp.get("pitch_note", ""),
                    "loudness_db": yp.get("loudness_target_db"),
                    "centroid_hz": yp.get("brightness_target_hz"),
                    "bpm": yp.get("bpm"),
                    "is_you": True,
                }
                items = items + [you]
        except Exception:
            you = None

    data = {"count": len(items), "items": items, "you": you}
    if not you:                      # 只缓存语料部分
        _RULER_CACHE.update(key=key, data={"count": len(items), "items": items, "you": None})
    return jsonify(data)


@app.route("/api/signature", methods=["POST"])
def api_signature():
    """画廊「扫听」用的 2.4 秒声音签名（一个和弦），按 id 缓存"""
    payload = request.get_json(silent=True) or {}
    try:
        img, key, m, emo, mp, ai = _resolve(payload)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except (FileNotFoundError, LookupError) as e:
        return jsonify({"error": str(e)}), 404

    out = SIG_DIR / f"{key}.wav"
    meta = SIG_DIR / f"{key}.json"
    if out.exists():
        notes, mode = [], None
        if meta.exists():
            try:
                mj = json.loads(meta.read_text(encoding="utf-8"))
                notes, mode = mj.get("notes", []), mj.get("mode")
            except Exception:
                pass
        return jsonify({"wav_url": f"/sig/{out.name}", "notes": notes, "mode": mode, "cached": True})
    try:
        import synth
        # 传图片路径：签名改用五段垂直轮廓（旧的"和弦换高度"九幅画听起来是同一个声音）
        r = synth.render_signature(mp, 2.4, str(out), image_path=str(img))
        try:
            meta.write_text(json.dumps({"notes": r.get("notes", []), "mode": r.get("mode"),
                                        "base_midi": r.get("base_midi")}, ensure_ascii=False),
                            encoding="utf-8")
        except Exception:
            pass
    except Exception as e:
        return jsonify({"error": f"signature failed: {e}"}), 500
    return jsonify({"wav_url": f"/sig/{out.name}", "notes": r["notes"], "mode": r.get("mode"), "cached": False})


@app.route("/api/scan", methods=["POST"])
def api_scan():
    """扫描式声化：画面结构决定时间与音区，不再用固定旋律"""
    payload = request.get_json(silent=True) or {}
    try:
        img, key, m, emo, mp, ai = _resolve(payload)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except (FileNotFoundError, LookupError) as e:
        return jsonify({"error": str(e)}), 404

    seconds = max(12.0, min(30.0, float(payload.get("seconds") or 22.0)))
    out = PRE_DIR / f"{key}_scan.wav"
    try:
        import sonify
        r = sonify.render_scan(str(img), seconds, str(out))
    except Exception as e:
        return jsonify({"error": f"scan failed: {e}"}), 500

    sess = ANALYSIS.setdefault(key, {})
    sess["scan"] = {"wav_url": r["wav_url"], "voices": r["voices"], "seconds": seconds}
    _save_record(key)
    return jsonify({
        "wav_url": r["wav_url"],
        "seconds": r.get("seconds", seconds),
        "line": r["line"],
        "voices": r["voices"],
        "events": r.get("events"),
        "events_per_s": r.get("events_per_s"),
        "edge_mean": r.get("edge_mean"),
        "rate_hz": r.get("rate_hz"),
        "structure": {
            "regions": r["structure"]["regions"],
            "mean_L": r["structure"]["mean_L"],
            "mean_S": r["structure"]["mean_S"],
        },
        "notes": [
            "x 轴 → 时间：从左到右把画读一遍（设计选择 D5）",
            "y 轴 → 音区：上面的东西高，下面的低（设计选择 D6）",
            "明度 → 音高/音色（R1/R3）、饱和度 → 力度（R2）",
            "色块在自己的 x 位置各响一下，时长按面积",
        ],
    })


@app.route("/api/palette", methods=["POST"])
def api_palette():
    """把当前取样点一起奏成一个和弦（色卡即和弦）"""
    payload = request.get_json(silent=True) or {}
    try:
        img, key, m, emo, mp, ai = _resolve(payload)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except (FileNotFoundError, LookupError) as e:
        return jsonify({"error": str(e)}), 404

    samples = (ANALYSIS.get(key) or {}).get("samples") or []
    if not samples:
        return jsonify({"error": "no samples", "voices": []}), 400
    ordered = bool(payload.get("ordered"))
    try:
        import synth
        if ordered:
            out = PRE_DIR / f"{key}_seq.wav"
            r = synth.render_sequence(samples, 0.9, str(out))
        else:
            out = PRE_DIR / f"{key}_chord.wav"
            r = synth.render_chord(samples, 3.0, str(out))
    except Exception as e:
        return jsonify({"error": f"palette failed: {e}"}), 500
    return jsonify({"wav_url": r["wav_url"], "voices": r["voices"],
                    "n": len(samples), "ordered": ordered})


@app.route("/heat/<path:name>")
def heat(name):
    return send_from_directory(str(SAL_DIR), name)


@app.route("/cvd/<path:name>")
def cvd_img(name):
    return send_from_directory(str(CVD_DIR), name)


@app.route("/sig/<path:name>")
def sig_wav(name):
    return send_from_directory(str(SIG_DIR), name)


@app.route("/focus/<path:name>")
def focus_img(name):
    return send_from_directory(str(SAL_DIR), name)


@app.route("/preview/<path:name>")
def preview_audio(name):
    return send_from_directory(str(PRE_DIR), name)


# ── 音乐生成: 任务队列 + 配额保护 ────────────────────────────────────────────
TASKS: dict = {}
USAGE_F = BASE / "outputs" / "api_usage.json"
DAILY_LIMIT = int(os.environ.get("MUSIC_DAILY_LIMIT", "20"))


def _load_usage() -> dict:
    return load_json(USAGE_F, {})


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def _usage_today() -> int:
    u = _load_usage()
    return u.get(_today(), {}).get("count", 0)


def _bump_usage(filename: str, ok: bool):
    u = _load_usage()
    d = u.setdefault(_today(), {"count": 0, "items": []})
    d["count"] += 1
    d["items"].append({"t": time.strftime("%H:%M:%S"), "file": filename, "ok": ok})
    try:
        USAGE_F.write_text(json.dumps(u, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _run_generation(task_id: str, prompt: str, title: str, out_name: str, token: str = ""):
    """后台线程: 真正调用音乐 API"""
    api_key = os.environ.get("MUSIC_API_KEY", "").strip()

    def log(msg):
        TASKS[task_id]["log"] = msg
        print(f"[{task_id[:8]}] {msg}", flush=True)

    try:
        import music_api_client
        res = music_api_client.generate(prompt, title, out_name, api_key, log=log)
        if res.get("ok"):
            files = res.get("filenames", [])
            TASKS[task_id].update({
                "status": "done",
                "filenames": files,
                # 默认播第一首, 前端可切换
                "audio_url": f"/audio/{files[0]}" if files else None,
                "audio_urls": [f"/audio/{f}" for f in files],
            })
            _bump_usage(files[0] if files else out_name, True)
            # P1-6: 把成品写回该图的留档记录
            if token and token in ANALYSIS:
                ANALYSIS[token]["generated_audio"] = files
                ANALYSIS[token]["generated_prompt"] = prompt
                _save_record(token)
        else:
            TASKS[task_id].update({"status": "error", "error": res.get("error", "unknown")})
            _bump_usage(out_name, False)
    except Exception as e:
        TASKS[task_id].update({"status": "error", "error": str(e)})
        _bump_usage(out_name, False)


@app.route("/api/generate", methods=["POST"])
def api_generate():
    """生成音乐 — 只有用户点击并确认后才真正调用, 会消耗 Suno 额度。

    三重保险:
      1. ENABLE_MUSIC_API 必须为 true
      2. 前端必须传 confirm=true (用户点了确认弹窗)
      3. 每日调用上限 MUSIC_DAILY_LIMIT
    """
    if not ENABLE_MUSIC_API:
        return jsonify({"error": "Music API is disabled"}), 403

    data = request.get_json(silent=True) or {}
    if not data.get("confirm"):
        return jsonify({"error": "confirmation required"}), 400

    api_key = os.environ.get("MUSIC_API_KEY", "").strip()
    if not api_key:
        return jsonify({"error": "MUSIC_API_KEY not set"}), 400

    # 配额检查
    used = _usage_today()
    if used >= DAILY_LIMIT:
        return jsonify({
            "error": f"Daily limit reached ({DAILY_LIMIT}). Try again tomorrow.",
            "used": used, "limit": DAILY_LIMIT,
        }), 429

    # 取 prompt
    art_id = (data.get("id") or "").strip()
    prompt = (data.get("prompt") or "").strip()
    title = (data.get("title") or "Untitled").strip()

    if not prompt:
        # 未显式传 prompt 时, 从已生成的 prompt 文件取
        if art_id:
            gallery = load_json(GALLERY_F, [])
            g = next((x for x in gallery if x.get("id") == art_id), None)
            if g:
                mp = load_json(MUSIC_PROMPTS_F, {}).get(g.get("file", ""), {})
                prompt = mp.get("music_prompt", "")
                title = g.get("title", title)
                # 把签名层的五音动机写进 prompt —— 否则两幅画的 prompt 七项相同，
                # Suno 没有任何理由把它们做成不同的东西。
                try:
                    import synth
                    from suno_prompt import motif_clause
                    _mt = motif_clause(synth.band_motif(str(ARTWORK_DIR / g.get("file", ""))).get("names") or [])
                    if _mt and "Opening motif" not in prompt:
                        prompt = (prompt + "\n\n" + _mt).strip()
                except Exception as e:
                    print(f"[generate] motif skipped: {e}", flush=True)
        if not prompt:
            return jsonify({"error": "no music prompt available"}), 400

    task_id = uuid.uuid4().hex
    stem = re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_").lower()[:40] or "untitled"
    # 上传图: 文件名带 token 前缀；预置画作: 带 task 短码。
    # 否则同一幅画生成两次会写到同一个文件名，第二次静默覆盖第一次（2026-10 实测踩到）。
    tok = (data.get("token") or "").strip()
    stem = f"{stem}_{tok[:6]}" if tok else f"{stem}_{task_id[:6]}"

    TASKS[task_id] = {
        "status": "running",
        "prompt": prompt,
        "log": "queued",
        "filename": None,
        "audio_url": None,
        "error": None,
        "title": title,
    }

    threading.Thread(
        target=_run_generation,
        args=(task_id, prompt, title, stem, (data.get("token") or "").strip()),
        daemon=True,
    ).start()

    return jsonify({
        "task_id": task_id,
        "status": "running",
        "used": used + 1,
        "limit": DAILY_LIMIT,
    })


@app.route("/api/task/<task_id>")
def api_task(task_id):
    """查询生成任务状态"""
    if not re.fullmatch(r"[0-9a-f]{32}", task_id or ""):
        return jsonify({"error": "invalid task id"}), 400
    t = TASKS.get(task_id)
    if not t:
        return jsonify({"error": "task not found"}), 404
    return jsonify(t)


@app.route("/api/usage")
def api_usage():
    """今日调用量(让用户清楚还剩多少额度)"""
    return jsonify({
        "used": _usage_today(),
        "limit": DAILY_LIMIT,
        "date": _today(),
        "enabled": ENABLE_MUSIC_API,
    })


@app.route("/api/era-styles")
def api_era_styles():
    return jsonify(ERA_STYLE)


# ── 托管前端 ────────────────────────────────────────────────────────────
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve(path):
    if path and (DIST / path).exists() and (DIST / path).is_file():
        return send_from_directory(str(DIST), path)
    idx = DIST / "index.html"
    if idx.exists():
        return send_file(str(idx))
    return jsonify({
        "error": "frontend not built",
        "message": "Run: cd frontend && npm run build",
    }), 503


if __name__ == "__main__":
    print("=" * 62)
    print("  颜色 → 音乐 作品集")
    print("=" * 62)
    print(f"  画作目录: {IMG_DIR}")
    print(f"  前端目录: {DIST}")
    print(f"  音乐 API: {'启用' if ENABLE_MUSIC_API else '关闭 (不会消耗额度)'}")
    print(f"  Gemini  : {'已配置' if os.environ.get('GEMINI_API_KEY') else '未配置'}")
    print("=" * 62)
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)

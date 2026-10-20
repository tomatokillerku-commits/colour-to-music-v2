#!/usr/bin/env python3
"""
ai_vision.py — AI 视觉情感分析层 (Google Gemini)

架构定位:
    ┌─ ① AI 视觉情感层 (本文件)   → 语义: 画面整体给人什么感受
    ├─ ② 代码精确测量层 (color_extractor) → 数值: 主色/色相/饱和/明度
    └─ ③ 融合层                    → AI 情感决定如何解释数值 → 音乐参数

为什么需要 AI:
    像素统计能告诉代码"有什么颜色", 但理解不了"这些颜色并置产生什么感受"。
    例如大面积红绿并置会产生戏剧性张力, 即使红绿像素量相近也应判为"激烈"
    而非"平静"——这是语义判断, 规则公式做不到, 必须靠多模态模型。

用法:
    export GEMINI_API_KEY=...
    python ai_vision.py <图片路径>          # 分析单张
    python ai_vision.py --batch <目录>      # 批量(输出到 ai_emotion_cache.json)

输出字段:
    mood         : 氛围概括(中文)
    valence      : [-1,1] 负向沉重 ↔ 正向愉悦
    arousal      : [0,1]  极度宁静 ↔ 极度激昂
    tension      : [0,1]  完全和谐 ↔ 强烈冲突
    narrative    : 80-150字, 描述色彩如何营造该情感
    musical_hint : 40-80字, 音乐建议(速度/力度/和声/乐器)
"""

import os
import io
import re
import sys
import json
import time
import base64
import requests
from pathlib import Path
from PIL import Image

API_BASE = "https://generativelanguage.googleapis.com/v1beta"
# 注: gemini-2.5-flash 已于近期停止对新用户开放, API 推荐 gemini-3.6-flash
DEFAULT_MODEL = "gemini-3.6-flash"

# ── 模型回退链 ────────────────────────────────────────────────────────────────
# 单个模型会遇到 503 (high demand) / 429 (rate limit)，直接抛出会让整个 AI 阶段
# 失败、上传的图拿不到 prompt。按此顺序回退，4xx 中除限流外不重试（请求本身错）。
MODEL_CHAIN = [
    DEFAULT_MODEL,          # gemini-3.6-flash
    "gemini-3.5-flash",
    "gemini-2.5-flash",
    "gemini-flash-latest",
]
RETRY_STATUS = (429, 500, 502, 503, 504)


def _call_gemini(payload: dict, api_key: str, model: str = DEFAULT_MODEL,
                 timeout: int = 120, tries_per_model: int = 2) -> tuple:
    """带模型回退的 generateContent 调用。

    返回 (response, model_used)。全部失败时抛 RuntimeError，信息里带最后一条错误。
    """
    chain = [model] if model and model != DEFAULT_MODEL else MODEL_CHAIN
    last = ""
    for m in chain:
        for attempt in range(tries_per_model):
            url = f"{API_BASE}/models/{m}:generateContent?key={api_key}"
            try:
                r = requests.post(url, json=payload, timeout=timeout)
            except Exception as e:
                last = f"{m}: {type(e).__name__} {e}"
                break
            if r.status_code == 200:
                return r, m
            last = f"{m} HTTP {r.status_code}: {r.text[:160]}"
            if r.status_code not in RETRY_STATUS:
                break                       # 请求本身的问题，换模型无意义
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Gemini 调用失败（尝试过 {len(chain)} 个模型）：{last}")

# 分析提示词: 强调"整体氛围"而非"颜色罗列"
# 注: 项目展示语言为英文, 故所有输出字段均要求英文
ANALYSIS_PROMPT = """You are an expert at the intersection of art therapy and musicology.
Observe this painting and judge its OVERALL EMOTIONAL ATMOSPHERE.

Crucially: judge the feeling the work conveys as a whole, not a mechanical list of colors.
The relationships between colors generate emotion:
  - Strong complementary juxtaposition (red/green, orange/blue, yellow/purple) creates
    dramatic tension, usually reading as intense, restless, or excited
  - Analogous or monochrome schemes read as harmonious, calm, or melancholic
  - Large areas of high-saturation warm color tend to expand outward and feel energetic
  - Large areas of low-value cool color tend to contract inward and feel still or oppressive
  - The agitation or calm of the brushwork, and the instability or balance of the composition,
    contribute to the emotional reading as well
Judge from composition, brushwork, and color relationships together - do not rely on
color proportion alone.

Output STRICTLY a JSON object matching this schema (no other text):
{
  "mood": "one phrase summarizing the overall atmosphere, in English, 3-6 words, e.g. 'fierce and mysterious' / 'serene yet melancholic'",
  "valence": number, -1 (heavy, anguished) to 1 (bright, joyful),
  "arousal": number, 0 (extremely still) to 1 (extremely agitated),
  "tension": number, 0 (fully harmonious) to 1 (strongly conflicting),
  "narrative": "80-150 words in English, describing specifically how the colors together create this emotion. You MUST name concrete color relationships (which color against which, and how they interact).",
  "musical_hint": "40-80 words in English, musical suggestions based on this emotion: tempo / dynamics / harmonic tension / instrumental character"
}
"""


def get_api_key() -> str:
    """按优先级查找 API Key"""
    for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "AI_VISION_API_KEY"):
        v = os.environ.get(k, "").strip()
        if v:
            return v
    return ""


def list_vision_models(api_key: str) -> list:
    """列出支持 generateContent(含视觉)的模型"""
    r = requests.get(f"{API_BASE}/models?key={api_key}", timeout=30)
    r.raise_for_status()
    return [m["name"].replace("models/", "")
            for m in r.json().get("models", [])
            if "generateContent" in m.get("supportedGenerationMethods", [])]


def _encode_image(path: str, max_side: int = 640) -> tuple:
    """缩放并 base64 编码(省 token, 且足够判断整体氛围)"""
    im = Image.open(path).convert("RGB")
    im.thumbnail((max_side, max_side), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode(), "image/jpeg"


def _extract_json(text: str) -> dict:
    """从模型输出中提取 JSON, 容忍 ```json 代码块包裹与前后废话"""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.I)
    t = re.sub(r"\s*```\s*$", "", t)
    s, e = t.find("{"), t.rfind("}")
    if s >= 0 and e > s:
        t = t[s:e + 1]
    return json.loads(t)


TITLE_PROMPT = """Look at this artwork and give it a short descriptive English title.

Rules:
  - 2 to 5 words, Title Case
  - Describe the visible subject / color / mood, not an interpretation
  - English only. No quotation marks, no period, no explanation.
  - If it is a famous recognizable work, use its established English title.
  - Otherwise describe it concretely, e.g.:
      "Crimson Field with Dark Horizon"
      "Study in Blue and Violet Curves"
      "Golden Landscape with Red Path"

Output the title only."""


def generate_title(path: str, api_key: str = None,
                   model: str = DEFAULT_MODEL) -> str:
    """为没有元信息的图片生成简短英文描述性标题。
    用于用户上传、文件名是中文或无意义字符串的情况。"""
    key = api_key or get_api_key()
    if not key:
        return ""

    b64, mime = _encode_image(path, max_side=512)
    url = f"{API_BASE}/models/{model}:generateContent?key={key}"
    payload = {
        "contents": [{"parts": [
            {"text": TITLE_PROMPT},
            {"inline_data": {"mime_type": mime, "data": b64}},
        ]}],
        "generationConfig": {"temperature": 0.4},
    }
    try:
        r = requests.post(url, json=payload, timeout=90)
        if r.status_code != 200:
            return ""
        t = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        t = t.strip().strip('"\'`').strip().rstrip(".").strip()
        return t if 0 < len(t) <= 60 else ""
    except Exception:
        return ""


IDENTIFY_PROMPT = """You are an art historian with an AI music researcher.
Look at this artwork and return BOTH its identification AND its emotional reading.

PART 1 — IDENTIFICATION
  If you recognize this as a known artwork:
    · title   : its established English title
    · artist  : the artist's name
    · year    : year of creation (just the number, or "" if unknown)
    · movement: the art movement (use a standard English term such as
                Post-Impressionism, Fauvism, Cubism, Surrealism,
                Abstract Expressionism, Color Field Painting, Op Art,
                Lyrical Abstraction, Bauhaus Modernism, American Modernism,
                Contemporary, Digital Art, Photography, etc.)
    · medium  : e.g. "Oil on canvas", "Acrylic on canvas", "Watercolor",
                "Digital", "Photograph" (or "" if unknowable)
    · identified: true

  If you DO NOT recognize it:
    · title   : invent a short descriptive English title (2-5 words,
                Title Case) naming the visible colors / forms, e.g.
                "Crimson Field with Dark Horizon"
    · artist  : "Unknown"
    · year    : ""
    · movement: your best guess at the style (use terms from the list above)
    · medium  : your best guess, or "" if unknowable
    · identified: false

PART 2 — EMOTIONAL READING
  Judge the OVERALL emotional atmosphere. The relationships between colors
  generate emotion: complementary juxtaposition (red/green, orange/blue,
  yellow/purple) creates dramatic tension; analogous schemes read as calm
  or melancholic; large areas of high-saturation warm color expand outward
  energetically; low-value cool areas contract inward. Brushwork agitation
  and compositional balance also contribute. Judge from composition,
  brushwork, and color relationships together — not color proportion alone.

Output STRICTLY a JSON object (no other text):
{
  "title": "English title",
  "artist": "Artist name or Unknown",
  "year": "1892",
  "movement": "standard English movement term",
  "medium": "Oil on canvas",
  "identified": true/false,
  "mood": "3-6 word English phrase, e.g. 'fierce and mysterious'",
  "valence": number, -1 (anguished) to 1 (joyful),
  "arousal": number, 0 (still) to 1 (agitated),
  "tension": number, 0 (harmonious) to 1 (conflicting),
  "narrative": "80-150 words in English describing specifically how the colors
                together create this emotion. Name concrete color relationships.",
  "musical_hint": "40-80 words in English: tempo / dynamics / harmonic tension /
                   instrumental character"
}
"""


def analyze_full(path: str, api_key: str = None,
                 model: str = DEFAULT_MODEL) -> dict:
    """一次调用同时拿到「作品识别」与「情感判断」。

    返回字段:
      title / artist / year / movement / medium / identified
      mood / valence / arousal / tension / narrative / musical_hint

    相比分别调用, 合并成一次请求可省额度、也更快。
    """
    key = api_key or get_api_key()
    if not key:
        raise RuntimeError("未设置 GEMINI_API_KEY")

    b64, mime = _encode_image(path)
    payload = {
        "contents": [{"parts": [
            {"text": IDENTIFY_PROMPT},
            {"inline_data": {"mime_type": mime, "data": b64}},
        ]}],
        "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json"},
    }

    r, model_used = _call_gemini(payload, key, model, timeout=120)

    data = r.json()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        raise RuntimeError(f"响应解析失败: {json.dumps(data, ensure_ascii=False)[:300]}")

    out = _extract_json(text)

    # 数值安全化
    for f in ("valence", "arousal", "tension"):
        try:
            out[f] = float(out.get(f, 0))
        except Exception:
            out[f] = 0.0
    out["valence"] = max(-1.0, min(1.0, out["valence"]))
    out["arousal"] = max(0.0, min(1.0, out["arousal"]))
    out["tension"] = max(0.0, min(1.0, out["tension"]))

    # 文本字段清洗
    for f in ("title", "artist", "year", "movement", "medium", "mood",
              "narrative", "musical_hint"):
        out[f] = str(out.get(f, "") or "").strip()

    out["identified"] = bool(out.get("identified", False))
    if not out["artist"]:
        out["artist"] = "Unknown"
    if not out["title"]:
        out["title"] = "Untitled"

    out["model"] = model_used      # 记录实际成功的模型（回退链可能换过）
    return out


def analyze_painting(path: str, model: str = DEFAULT_MODEL,
                     api_key: str = None) -> dict:
    """
    用 Gemini 判断画作整体情感氛围。
    返回 dict: mood / valence / arousal / tension / narrative / musical_hint
    """
    key = api_key or get_api_key()
    if not key:
        raise RuntimeError("未设置 GEMINI_API_KEY 环境变量")

    b64, mime = _encode_image(path)
    url = f"{API_BASE}/models/{model}:generateContent?key={key}"
    payload = {
        "contents": [{
            "parts": [
                {"text": ANALYSIS_PROMPT},
                {"inline_data": {"mime_type": mime, "data": b64}},
            ]
        }],
        "generationConfig": {
            "temperature": 0.4,
            "responseMimeType": "application/json",
        },
    }

    r = requests.post(url, json=payload, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f"Gemini API {r.status_code}: {r.text[:300]}")

    data = r.json()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        raise RuntimeError(f"响应解析失败: {json.dumps(data, ensure_ascii=False)[:300]}")

    out = _extract_json(text)

    # 数值安全化
    for f in ("valence", "arousal", "tension"):
        try:
            out[f] = float(out[f])
        except Exception:
            out[f] = 0.0
    out["valence"] = max(-1.0, min(1.0, out["valence"]))
    out["arousal"] = max(0.0, min(1.0, out["arousal"]))
    out["tension"] = max(0.0, min(1.0, out["tension"]))
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    api_key = get_api_key()
    if not api_key:
        print("错误: 请设置 GEMINI_API_KEY 环境变量", file=sys.stderr)
        sys.exit(1)

    if "--batch" in sys.argv:
        img_dir = Path(args[0]) if args else Path(__file__).parent / "artworks"
        files = sorted([p for p in img_dir.iterdir()
                        if not p.name.startswith(".") and p.name != ".DS_Store"])
        cache = {}
        for p in files:
            print(f"\n分析: {p.name}")
            try:
                emo = analyze_painting(str(p), api_key=api_key)
                cache[p.name] = emo
                print(f"  氛围: {emo['mood']}")
                print(f"  valence={emo['valence']:+.2f}  arousal={emo['arousal']:.2f}  tension={emo['tension']:.2f}")
                print(f"  叙事: {emo['narrative'][:100]}...")
                print(f"  音乐: {emo['musical_hint'][:80]}")
            except Exception as e:
                print(f"  ❌ 失败: {e}", file=sys.stderr)
                cache[p.name] = {"error": str(e)}
        out = Path(__file__).parent / "ai_emotion_cache.json"
        out.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n💾 已保存: {out}")
        return

    if not args:
        print("用法: python ai_vision.py <图片路径>  或  --batch <目录>")
        sys.exit(1)

    emo = analyze_painting(args[0], api_key=api_key)
    print(json.dumps(emo, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

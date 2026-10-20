#!/usr/bin/env python3
"""
music_api_client.py — Suno (api.sunoapi.org) 音乐生成客户端

安全设计:
  · 本模块只在用户显式点击 + 二次确认后被调用
  · 任何自动/批量/循环调用路径都不存在
  · 调用前由 server.py 检查配额上限

接口要点(实测):
  · POST /api/v1/generate  必填 customMode (不是 custom)
  ·                        必填 callBackUrl (平台要求, 本实现靠轮询取结果,
                                            回调地址填占位即可)
  · 返回 taskId
  · GET  /api/v1/tasks/{taskId} 轮询, data[].audioUrl / streamUrl
"""

import os
import sys
import time
import json
import shutil
import requests
from pathlib import Path

BASE_URL = "https://api.sunoapi.org"
ENDPOINT = "/api/v1/generate"

# 查询端点(实测): /api/v1/tasks/{id} 会 404, 正确的是下面这个
RECORD_ENDPOINT = "/api/v1/generate/record-info?taskId={taskId}"

# 回调地址: 平台强制要求该字段, 但本实现通过轮询取结果,
# 因此填占位地址即可(实测填占位后任务能正常创建)
CALLBACK_URL = os.environ.get("SUNO_CALLBACK_URL", "https://example.com/suno-callback")

REQUEST_TEMPLATE = {
    "prompt": "{prompt}",
    "model": "V4",
    "customMode": True,        # 注意: 是 customMode, 不是 custom
    "instrumental": True,
    "title": "{title}",
    "callBackUrl": CALLBACK_URL,
}

# 实测响应结构:
#   提交: {"code":200,"msg":"success","data":{"taskId":"..."}}
#   查询: {"code":200,"msg":"success","data":{"taskId":...,"status":"TEXT_SUCCESS",
#          "response":{"sunoData":[{..."streamAudioUrl":...}]}}}
#   → taskId 嵌套在 data 下; 音频链接在 response.sunoData[].streamAudioUrl
TASK_ID_PATH = "data.taskId"
STATUS_PATH = "data.status"
SUNO_DATA_PATH = "data.response.sunoData"

# 音频链接字段(按优先级): 流媒体链接优先, audioUrl 往往为空
AUDIO_FIELDS = ("streamAudioUrl", "audioUrl", "sourceAudioUrl")

# 任务级状态: 未完成时可能没有 'SUCCESS' 字样
STATUS_PENDING = ("pending", "queued", "running", "text", "processing", "submitted")
STATUS_FAILED = ("failed", "error", "timeout")

POLL_INTERVAL = 8      # 秒
MAX_POLL = 40          # 最多轮询 40 次 ≈ 5 分钟

OUT_DIR = Path(__file__).parent / "outputs" / "audio"


def get_api_key() -> str:
    return (os.environ.get("MUSIC_API_KEY") or "").strip()


def _get_nested(obj, path: str):
    for key in path.split("."):
        if isinstance(obj, dict) and key in obj:
            obj = obj[key]
        else:
            return None
    return obj


def submit(prompt: str, title: str, api_key: str) -> str:
    """提交生成任务, 返回 taskId"""
    body = json.loads(json.dumps(REQUEST_TEMPLATE))
    for k, v in body.items():
        if isinstance(v, str):
            body[k] = v.format(prompt=prompt, title=title[:40])

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    url = BASE_URL + ENDPOINT

    r = requests.post(url, headers=headers, json=body, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Suno API {r.status_code}: {r.text[:300]}")

    data = r.json()

    # 业务错误码(code 非 200)优先处理
    code = data.get("code")
    if code is not None and str(code) != "200":
        raise RuntimeError(f"Suno API error {code}: {data.get('msg', data)}")

    # taskId 在 data 下; 兼容少数直接放在顶层的情况
    task_id = _get_nested(data, TASK_ID_PATH) or _get_nested(data, "taskId")
    if not task_id:
        raise RuntimeError(f"未取到 taskId: {json.dumps(data, ensure_ascii=False)[:300]}")
    return task_id


def _parse_response_block(resp) -> list:
    """response 可能是 dict 或 JSON 字符串"""
    if isinstance(resp, str):
        try:
            resp = json.loads(resp)
        except Exception:
            return []
    if not isinstance(resp, dict):
        return []
    items = resp.get("sunoData") or []
    return [x for x in items if isinstance(x, dict)]


def _pick_audio(item: dict):
    """音频链接字段不固定, 按优先级取第一个非空值"""
    for f in AUDIO_FIELDS:
        v = item.get(f)
        if v and str(v).startswith("http"):
            return v
    return None


def poll(task_id: str, api_key: str) -> dict:
    """轮询任务状态。

    返回 {status, audio_urls: [...], error}
    注意: 一次生成会产出 2 首, 因此返回列表而非单个链接
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    url = BASE_URL + RECORD_ENDPOINT.format(taskId=task_id)

    last_status = None
    for i in range(MAX_POLL):
        r = requests.get(url, headers=headers, timeout=30)
        if r.status_code != 200:
            # 任务刚创建时查询可能短暂 404, 继续重试
            if r.status_code == 404 and i < 3:
                time.sleep(POLL_INTERVAL)
                continue
            raise RuntimeError(f"轮询失败 {r.status_code}: {r.text[:200]}")

        data = r.json()
        code = data.get("code")
        if code is not None and str(code) != "200":
            raise RuntimeError(f"查询失败 {code}: {data.get('msg', data)}")

        status = str(_get_nested(data, STATUS_PATH) or "").strip()
        last_status = status
        s_low = status.lower()

        # 明确的失败状态
        if any(x in s_low for x in STATUS_FAILED):
            err = _get_nested(data, "data.errorMessage") or status
            return {"status": "failed", "audio_urls": [], "error": str(err)}

        # 取音频: response 可能在 data.response
        items = _parse_response_block(_get_nested(data, "data.response"))
        urls = [u for u in (_pick_audio(it) for it in items) if u]

        # 有链接即认为完成(平台用 TEXT_SUCCESS 表示歌词/音频就绪)
        if urls:
            return {"status": "done", "audio_urls": urls}

        time.sleep(POLL_INTERVAL)

    return {"status": "timeout", "audio_urls": [],
            "error": f"轮询超时(约 {MAX_POLL * POLL_INTERVAL}s), 最后状态: {last_status}"}


def download(url: str, out_name: str) -> str:
    """下载音频到本地"""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ext = ".mp3"
    low = url.split("?")[0].lower()
    for e in (".mp3", ".wav", ".m4a", ".ogg"):
        if low.endswith(e):
            ext = e
            break
    out_path = OUT_DIR / f"{out_name}{ext}"

    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            shutil.copyfileobj(r.raw, f)
    return out_path.name


def generate(prompt: str, title: str, out_name: str,
             api_key: str, log=print) -> dict:
    """完整流程: 提交 → 轮询 → 下载。

    一次生成会产出 2 首, 因此返回 filenames 列表
    返回 {ok, filenames: [...], error}
    """
    try:
        log("提交生成任务...")
        task_id = submit(prompt, title, api_key)
        log(f"taskId = {task_id}")

        log("等待生成(通常 1-3 分钟)...")
        res = poll(task_id, api_key)

        if res["status"] != "done" or not res["audio_urls"]:
            return {"ok": False, "filenames": [],
                    "error": res.get("error", "未取得音频链接")}

        n = len(res["audio_urls"])
        log(f"生成完成, 共 {n} 首, 下载中...")
        filenames = []
        for i, url in enumerate(res["audio_urls"], 1):
            name = out_name if n == 1 else f"{out_name}_{i}"
            filenames.append(download(url, name))

        log(f"完成: {', '.join(filenames)}")
        return {"ok": True, "filenames": filenames}
    except Exception as e:
        return {"ok": False, "filenames": [], "error": str(e)}


if __name__ == "__main__":
    key = get_api_key()
    if not key:
        print("错误: 请设置 MUSIC_API_KEY", file=sys.stderr)
        sys.exit(1)
    print("这是一个手动测试入口。正式调用请在网页中点击生成按钮。")
    print("直接运行不会消耗额度。")

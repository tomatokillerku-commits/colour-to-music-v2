# Colour-to-Music V2

将绘画的颜色与空间变化转换为可试听的声音，并展示映射规则、依据和测量结果。此仓库对应 2026-10-19 的九幅参考画版本。

## 功能与范围

- 测量画面的明度、饱和度、主色和空间分布，检查输入是否落在预设范围内。
- 规则层实现明度→音高、饱和度→响度、明度→音色明亮度，并提供五音动机、三层试听与扫描式声音。
- Gemini（用于理解图片和生成文字的 AI 服务）提供可选的画面描述与音乐描述；第三方 Suno 接口可据此生成音乐。
- 页面分为首页、作品详情和制作记录，区分实验支持的映射方向与项目自行设定的设计规则。

具体转换公式、五段取样方式和输入阈值属于项目设计。声音可区分、参数可测量，不等于已经证明听众能凭声音识别画作；AI 音乐也不保证准确遵守目标参数。开发者原有实验描述见 `变更说明.md`，不代表此次上传已重新验证。

## 本地运行

需要 Python 3.10+ 和 Node.js 22.12+。Python 用于后端和声音计算；Node.js 用于构建网页。

在项目根目录运行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
cd frontend
npm ci
npm run build
cd ..
python server.py
```

Windows 中用 `.venv\Scripts\activate` 激活 Python 环境。启动后打开 <http://127.0.0.1:5000>。前端构建文件不提交到仓库，首次运行必须先完成 `npm run build`；修改前端后重新构建并重启后端。

无需密钥即可浏览参考画、计算颜色、生成规则层声音。仓库保留三份经过检查的小型演示数据；不包含私人上传缓存、生成音频、依赖目录或前端构建文件。若页面中的已有 AI 音乐为空，需要自行生成或放入本地 `outputs/audio/`。

## 可选 AI 配置

在本地 `.env` 填写自己的密钥：

| 变量 | 用途与默认值 |
|---|---|
| `GEMINI_API_KEY` | 可选；画面语义分析与音乐描述。调用会向 Google 发送图片或分析数据，并可能消耗额度。 |
| `ENABLE_MUSIC_API` | 默认 `false`；改为 `true` 才允许调用音乐生成服务。 |
| `MUSIC_API_KEY` | 可选；第三方音乐服务的密钥，当前接口为 `api.sunoapi.org`。 |
| `MUSIC_DAILY_LIMIT` | 默认 `20`；本地每日生成次数上限。 |
| `ARTWORK_DIR` | 默认 `artworks`；画作目录。 |
| `SUNO_CALLBACK_URL` | 可选；音乐服务回调地址，按自己的部署配置。 |

缺少 Gemini 密钥时，新图的音乐描述使用规则模板回退。音乐生成需开启开关、填写密钥并在页面确认，会消耗服务额度。不要把密钥放入前端代码或以 `VITE_` 开头的变量。

## 项目结构

| 文件或目录 | 内容 |
|---|---|
| `server.py` | Flask（Python 网页服务工具）后端、接口与网页托管 |
| `frontend/` | React（网页界面工具）与 TypeScript 前端源代码 |
| `mapping_rules.py`、`synth.py`、`sonify.py` | 映射、声音合成、扫描式声音 |
| `color_extractor.py`、`saliency.py`、`gate.py` | 颜色测量、显著区域与输入范围检查 |
| `ai_vision.py`、`music_prompt_ai.py`、`music_api_client.py` | 可选 AI 与音乐服务调用 |
| `gallery.json`、`content/`、`artworks/` | 九幅参考画的元数据、解读和图片，另有一幅排除样本 |
| `outputs/` | 三份小型演示数据；其他运行结果由程序在本地生成 |
| `portfolio/` | 架构图与原有展示页面 |

## 安全与素材

仓库不包含个人 API 密钥。`.env`、私人配置、运行缓存、音频和依赖目录由 `.gitignore` 排除；提交前仍需检查文件内容。若曾分享含密钥的压缩包、日志或提交，应到服务商后台撤销旧密钥并重新生成。

后端默认仅监听本机。公开部署前需另行配置身份验证、上传限制和服务额度保护。参考画的图片与文字沿用原项目素材，其权利归各自权利人；仓库未声明这些素材可以自由再分发。

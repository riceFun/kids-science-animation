# 考考&小熹 · 儿童科普动画

把一份中文台本变成 4–5 分钟的 1080p 儿童科普短片。**画面、配音、音效、配乐全部由代码生成**，不用素材站、不用付费 API、不用 AI 生图。

系列角色：考考（6 岁男孩）与小熹（火狐）。

## 它做什么

输入一个 `script.json`（25 段左右的分镜脚本），输出一支带配音、字幕、配乐和音效的横屏视频：

- **画面**：SVG 图元逐帧计算。每集自带 `scenery.js`，按这一集的话题现场画场景——没有背景库，也没有「话题→背景」映射表。
- **配音**：EdgeTTS 逐句合成，句间留 0.12s，再按角色做变调。逐句合成是为了拿到每句真实时长，字幕因此能锚在真实句首，不会越说越晚。
- **声音**：`numpy` 程序化生成配乐与音效，`vox.py` 合成小熹的特色音。零音频素材。
- **校验**：知识点占比、景别单调、图标滥用、未注册的场景名/figure、字幕与语音对齐，全部在构建时检查。

## 快速开始

```bash
# 依赖：python3(+numpy, edge_tts) / node(+puppeteer-core) / Chrome / ffmpeg
mkdir -p ep01 && cp assets/example/script.json assets/example/scenery.js ep01/

python3 scripts/build.py ep01/script.json --preview 8,40,120   # 抽帧看排版
python3 scripts/build.py ep01/script.json --draft              # 960×540 草稿
python3 scripts/build.py ep01/script.json --grain              # 1080p 正片
python3 scripts/build.py ep01/script.json --check-align        # 只查字幕/语音是否对齐
```

## 目录

```
SKILL.md              完整的制作规范（叙事结构、场景画法、硬规则）
assets/engine/        渲染引擎（场景类型、角色、Schema 图）
assets/example/       可直接跑通的模板集 + 场景代码
scripts/              build / tts / render / music / sfx / vox / fetch_photo
references/           台本字段、视觉规范、角色规范、声音设计、踩坑记录
```

写作规范见 [SKILL.md](SKILL.md)，台本字段见 [references/script-format.md](references/script-format.md)。

## 一套规矩（摘）

- 知识是主角：对话不超过 40%，每个知识点必须有画面承载
- 具体的东西必须画准：讲玻璃鳗就画半透明的小鳗苗，不许拿树叶图标顶替
- 不用 AI 生图：素材只有真图（有商用许可）和手绘两种
- 片头即封面：左标题 + 右主体，16:9 横屏，缩略图也认得出
- 每个字都要同时被读出来，否则对 6 岁观众等于空白

## 许可

代码与文档可自由取用；示例中的角色形象（考考、小熹）版权归作者所有。

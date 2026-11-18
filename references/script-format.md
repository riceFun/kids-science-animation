# 台本格式 script.json

一份台本就是一个 `segments` 数组。`build.py` 会按顺序给每段配音、算时长、累加 `start`，写出 `timeline.json` 交给渲染引擎。

```json
{
  "meta": { "series": "考考&小熹", "title": "为什么天是蓝的", "ep": 1 },
  "segments": [ { "type": "title", "bg": "午后草地", ... } ]
}
```

`meta.title` 决定成片文件名（`out/<title>.mp4`）。

## 通用字段（所有场景）

| 字段 | 类型 | 说明 |
|---|---|---|
| `type` | string | `title` / `talk` / `show` / `card` / `quiz` / `outro` |
| `bg` | string | 场景名。**必须是本集 `scenery.js` 里 `SCENE_KIT.scene("名字", ...)` 注册过的名字**（写错 `build.py` 会报警）。没有背景库，场景按话题现场画 |
| `shot` | string | 景别。`"close"` 大脸特写（仅 `talk`）、`"macro"` 微距推近（仅 `show`）。不写＝中景。一集里至少各来 2–3 次，否则画面像 PPT |
| `hook` | bool | 开场钩子段标记。钩子放在 `title` 之前，合计 10–20 秒，`build.py` 会检查 |
| `cover` | string | 仅 `title` 场景：封面主体（本集 scenery 注册的 figure 名，画在右半边）。片头同时当封面用，强烈建议填 |
| `titleLines` | array | 仅 `title` 场景：显式指定标题的两行文字，避免自动断行甩出孤字 |
| `coverScale` `coverX` `coverY` | number | 仅 `title` 场景：封面主体的缩放与位移，用来调构图 |
| `figure` | string | 仅 `figure` 场景：对象名，必须在本集 `scenery.js` 里 `SCENE_KIT.figure("名字", ...)` 注册过。讲具体东西用它，不要塞圆盘 |
| `photo` | string | 仅 `photo` 场景：图片路径（相对台本目录），如 `photos/mosquito.jpg`。build 时自动转 base64 内联 |
| `credit` | string | 仅 `photo` 场景：署名短句，如 `图：James Gathany · CC BY 2.5（Wikimedia Commons）`。有它就会自动生成片尾署名卡 |
| `kenBurns` | string | 仅 `photo` 场景：`"out"` 缓慢拉远，不写则缓慢推近 |
| `creditPos` | string | 仅 `photo` 场景：角标位置。默认右上角，`"br"` 放右下角（自动避开字幕） |
| `text` | string | 旁白（旁白音色朗读，自动上字幕） |
| `say` | string | 对话气泡内容（≤20 字）。写了就出气泡 |
| `voice` | string | `narrator` / `kao` / `xi`，决定音色与谁动嘴 |
| `speaker` | string | `kao` / `xi`，气泡尾巴指向谁、另一个角色压暗 |
| `min` | number | 这段的最短秒数（默认 4）。**短反应镜头填 3–3.5，正常对话 4.5–5，别一律 5–6**（否则短句说完空出三四秒静音） |
| `hold` | number | 说完之后额外留白秒数。`show`/`card` 建议 0.9 |
| `tex` | string | 覆盖配乐织体：`spark` / `soft` / `piano` / `full` / `outro` |

时长公式（`build.py` 自动算，不用手写 dur）：

```
dur = max(min, 0.40 + 语音时长 + 0.60 + hold)
```

## 各场景专有字段

### title
```json
{ "type":"title", "bg":"午后草地", "min":5.5,
  "brand":"考考&小熹", "kicker":"天空", "title":"为什么天是蓝的？",
  "text":"为什么天是蓝的？" }
```
- `brand` 系列名，渲染在**左上角**当台标。
- `kicker` 只写话题（"天空"、"蝴蝶"）。**不要写「第 N 集」**——每集独立成篇，不和任何一集挂钩。
- `title` 本集问题，居中大字。
- `text` 必填：把标题念出来。小朋友不识字，画面有标题没声音就等于没说。

### talk
```json
{ "type":"talk", "bg":"午后草地", "speaker":"kao",
  "kaoExpr":"talk", "xiView":"q34", "xiExpr":"think", "xiTail":"still",
  "voice":"kao", "say":"小熹，你说天为什么是蓝的？" }
```
- `kaoExpr`：`idle` 常态 / `silly` 大笑 / `wow` 惊讶 / `talk` 说话（会动嘴）
- `xiView`：`front` 正面 / `q34` 三分之二（默认）/ `side` 侧面 / `back` 背面
- `xiExpr`：`idle` / `happy` / `wow` / `think` / `giggle` / `scope` / `talk`
- `xiTail`：`still` 静止 / `wag` 摇摆 / `glow` 尾尖亮起（会带一声知识音）
- 可选 `kaoX` `xiX` `feet` `kaoScale` `xiScale` 调站位，默认 520 / 1340 / 950 / 0.92 / 1.34

### show
```json
{ "type":"show", "bg":"光的实验室", "figure":"白光七色", "big":"白光里藏着七种颜色",
  "text":"先来看太阳光。……", "hold":0.9 }
```
`figure` 必须在本集 `scenery.js` 里注册过。`emblem` / `labels` 已废弃（圆盘那套不再渲染），
标注请直接画在 `figure` 里，位置由你控制。

### card
```json
{ "type":"card", "bg":"午后草地", "title":"这一集弄明白三件事",
  "text":"先别急着猜。……", "hold":0.9,
  "points":[{"text":"太阳光到底是什么颜色","at":0.10}] }
```
最多 4 条；每条文字建议 ≤16 字（超过会折行挤在一起）。
`icon` 已废弃：卡片刻度只有序号，图标和要点内容没关系，不再渲染。

### quiz
```json
{ "type":"quiz", "bg":"午后草地", "q":"考考考你：天空为什么是蓝的？",
  "text":"最后一关，考考你。……", "revealAt":0.66,
  "options":["……","……","……"], "answer":1 }
```
`options` 最多 3 个（A/B/C），每条 ≤12 字。

`revealAt` 是揭晓进度（0–1，默认 **0.82**）。**一定要等选项读完再揭晓**——题目和选项在屏幕上，但语音还在念，答案就变绿，观众等于先看到了结论。选项越多、句子越长，这个值越要往后放。

**题目必须读出来**。观众是小孩子，不识字就等于没出题：

- 写了 `text` → 念 `text`。
- 没写 `text` → 自动把 `q` + `options` 拼成一句念出来（"……？第一，A。第二，B。第三，C。"）。
- 无论哪种，**quiz 的文本都不进字幕**——题目已经在横幅上了，再出字幕是同一句话出现两次，而且拼起来远超两行会被截断。

### outro
```json
{ "type":"outro", "bg":"meadow_night", "min":8,
  "line1":"下次见！", "text":"今天就到这里，下次见！" }
```
- `line2` **不写"第 N 集"**，也不写系列名。每一集都是独立的一期，观众不需要知道这是第几集。
- `next`（下集预告蓝条）**是可选的**，当前默认不做——不给就不画。不要靠它做连续性，每集必须自己收得住。

## 写文案的三条经验

1. **一段只讲一件事**。超过 70 字就拆成两段，画面能多一个镜头，节奏也更好。
2. **旁白用"我们/你"，不用"小朋友们"**。前者是一起看，后者是说教。
3. **每个知识点后面跟一句考考或小熹的反应**，哪怕只有 5 秒。纯旁白连播三段孩子会走神。

## 时长速查

| 段落数 | 大致成片 |
|---|---|
| 18 | 3:00 |
| 25 | 4:00 |
| 31 | 4:30 |
| 36 | 5:10（超了，建议拆成两集） |

`build.py` 会在总时长不在 240–330 秒时提示，但不会拦你。

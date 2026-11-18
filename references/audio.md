# 声音设计

三层声音，全部代码生成，不用任何采样包或付费 TTS：

| 层 | 谁做 | 实现 |
|---|---|---|
| 台词 | 旁白 / 考考 / 小熹 | EdgeTTS（现成音色）+ ffmpeg 变调 |
| 角色特色音 | 小熹 | 共振峰合成（`scripts/vox.py`） |
| 音效 / 配乐 | 全部 | numpy 波形合成（`scripts/sfx.py` / `music.py`） |

## 一、音色定位

### 现成音色够不够用：够

EdgeTTS 的 zh-CN 一共 8 个（2026.11 实测）：

| 音色 | 性别 | 场景标签 | 性格词 | 结论 |
|---|---|---|---|---|
| `zh-CN-YunxiaNeural` | 男 | Cartoon, Novel | **Cute** | ✅ 考考（唯一中文童声） |
| `zh-CN-XiaoyiNeural` | 女 | Cartoon, Novel | **Lively** | ✅ 小熹（灵动、气息浅） |
| `zh-CN-YunxiNeural` | 男 | Novel | Lively, Sunshine | ✅ 旁白 |
| `zh-CN-YunyangNeural` | 男 | News | Professional | 备选旁白 |
| `zh-CN-XiaoxiaoNeural` | 女 | News, Novel | Warm | 只作小熹降级项 |
| `zh-CN-YunjianNeural` | 男 | Sports | Passion | 不用（太硬） |
| `zh-CN-liaoning-XiaobeiNeural` | 女 | Dialect | Humorous | 不用 |
| `zh-CN-shaanxi-XiaoniNeural` | 女 | Dialect | Bright | 不用 |

**结论：两个角色都有现成的合适音色，不需要任何付费服务。**

### 三条配音配方

| 角色 | 音色 | rate | pitch | 变调倍数 | 实测中位基频 |
|---|---|---|---|---|---|
| 旁白 | Yunxi | -5% | +0Hz | 1.00 | 184 Hz |
| 考考 | Yunxia | -6% | +2Hz | **1.05** | 312 Hz |
| 小熹 | Xiaoxiao | +6% | +10Hz | **1.14** | 约 313 Hz |

考考和小熹差 **5.3 个半音**（424 / 312），是「成年男声 vs 小男孩」之外最明显的一档距离，
足够让观众不看画面也能分出谁在说话。

### 为什么是这三个数字

- **考考只抬 5%**：Yunxia 本身就是童声录制，抬高 15% 实测到 337 Hz 已经有点像花栗鼠。
  童声的真值在 300 Hz 附近，微调即可。
- **小熹用晓晓、抬 14%**：晓晓原声约 275 Hz，抬到约 313 Hz。
  这比早期方案的 424 Hz 低一档，**不是更「幼兽」，而是更耐听**——
  4 分钟的片子里，齿音刺耳比「不够卡通」伤害大得多。
  想更卡通就把 `shift` 往上加 0.02 试，超过 1.20 齿音会重新冒出来。
- **小熹不能直接用 Yunxia**：会和考考撞音色。角色音色的第一原则是「先分得开，再好听」。
- **关于「Xiaoyi 还是 Xiaoxiao」**：早期结论是小熹不能用晓晓（基频低，抬上去像阿姨假声）。
  实际试听后反转了：晓晓 1.14 虽然音高只有 313 Hz，但音色干净、没有 Xiaoyi 的气声毛刺，最终选它。
  **音色是听出来的，不是算出来的**——参数表只是起点，定稿前跑 `voice_demo.py`。

### 觉得不好听怎么办

改 `tts.py` 的 `VOICES` 之前先试听，别直接出全片：

```bash
python scripts/voice_demo.py /tmp/vd
```

同一句台词用 7 套配方各念一遍（含考考、小熹、旁白），挑中意的再改默认值。配方里的 `shift` 是变调倍数：1.00 原声，1.14 约两个半音，**超过 1.20 明显发尖**。

### 变调的正确姿势

EdgeTTS 出的是 24 kHz mp3。直接 `asetrate` 会把采样率一起改，时间轴整体错位。

```
aresample=44100 → asetrate=44100*倍数 → atempo=1/倍数
```

降级链也要连 shift 一起改（`tts.py` 的 `VOICES[*].fallback` 支持 `(音色, {覆盖项})` 这种写法）。

### 试听

```bash
python3 scripts/voice_demo.py /tmp/voice_demo
```

同一句台词渲染 7 套配方（含考考两个 shift、小熹三个 shift、Xiaoxiao 对照、旁白），
一次听完全部候选。

## 二、小熹的特色音

### 为什么不做「皮卡皮卡」

那是把角色名字当叫声，本质是拟人化台词，属于宝可梦的专属做法。
小熹是狐狸，要的是「动物发声 + 像在说话」之间的那个位置。

### 设计依据：赤狐真实的三类叫声

| 真实叫声 | 特征 | 对应设计 |
|---|---|---|
| yip / yap | 短促、上滑的一声 | 啾 `vox_chirp` |
| gekkering | 快速连发、15–25 Hz 颤音（亲昵） | 噜 `vox_trill` |
| huff | 鼻音、气流声 | 嗯 `vox_huff` |

### 六个音节

实现方式：**锯齿波激励 + 三个并联共振峰带通 + 音高包络**（`scripts/vox.py`）。
共振峰决定「像不像动物」，音高曲线决定「在说什么情绪」。

| 文件 | 听感 | 音高曲线 | 共振峰 (F1/F2/F3) | 时长 | 用在哪 |
|---|---|---|---|---|---|
| `vox_chirp` | 啾 | 420 → 700 Hz 上滑 | 340 / 2350 / 3050 | 0.11s | 开口前的一声（应答、发现） |
| `vox_trill` | 噜噜噜 | 三连发 + 18 Hz 颤音 | 同上 | 0.34s | 开心、咯咯笑 |
| `vox_coo` | 哩～ | 520 → 400 → 620 Hz 折线 | 400 / 1900 / 2650 | 0.24s | 疑问、歪头想 |
| `vox_yip` | 呀！ | 双跳 420→525→610 | 同上 | 0.15s | 惊讶 |
| `vox_huff` | 嗯 | 180 Hz 平直 + 低通噪声 | 260 低通 / 900 | 0.16s | 思考、否定 |
| `vox_insight` | 叮— | G5-B5-D6-G6 上行四音 | — | 0.55s | **尾巴亮起**（不是动物叫，是"灵光"） |

`vox_insight` 特意和通用的 `sfx_sparkle` 拉开：sparkle 是特效音（铺满高频、无音高），
insight 是有明确音高的钟琴，一听就知道"是小熹想通了"。

### 落点规则（`build.py` 的 `vox_cues`）

全部从台本字段推导，不手写时间码：

```python
voice == "xi"        → chirp  在开口前 0.30s
xiExpr == "think"    → coo    段首 +0.42s
xiExpr == "giggle"   → trill  段首 +0.80s
xiTail == "glow"     → insight 段首 +0.34s
type == "outro"      → trill  段首 +0.60s
```

考考是真人小孩，**不加任何动物音**，他的"表演"由 TTS 的 rate/pitch 和嘴型动画承担。

## 三、音效（与上一版一致）

六个程序化音效，`scripts/sfx.py`，全部 numpy 波形：

| 文件 | 听感 | 合成方式 | 落点 |
|---|---|---|---|
| `sfx_whoosh` | 转场风声 | 带通噪声 + 分段扫频 500→2700 Hz | 每个场景切换前 0.3s |
| `sfx_pop` | 弹出 | 下滑正弦 + 起始咔哒 | `card` 每条要点出现时 |
| `sfx_sparkle` | 闪光 | 6 颗钟琴错落，五声音阶 | `show` 圆盘弹出、quiz 揭晓 |
| `sfx_boing` | 弹簧 | 220 Hz + 14 Hz 颤动 | 片头 logo 落位 |
| `sfx_riser` | 上升 | 锯齿扫频 + 噪声 | quiz 揭晓前 1.3s 铺垫 |
| `sfx_thud` | 落地 | 低频正弦 + 短噪声 | 备用（当前台本未用） |

落点规则同样从时间线推导（`build.py` 的 `sfx_cues`）。

## 四、混音

```
bgm  × 0.16
台词 × 1.15
音效 × 0.55（含 vox，各自还有单独增益）
→ amix → loudnorm(I=-16, TP=-1.5, LRA=11)
```

几条经验：

- **配乐压到 -16 LUFS 以下**：BGM 自己做出来峰值接近 0 dB，直接混会盖住台词。0.16 倍是实测"听得见但不抢"的位置。
- **小熹的 vox 比台词低 3–6 dB**（0.26–0.44），它是语气助词，不是台词。
- **`loudnorm` 放最后**：先按比例混好，再统一响度，不要在每一轨上单独压限。

## 五、想调的时候

| 想改什么 | 改哪 |
|---|---|
| 换音色 / 语速 | `scripts/tts.py` 的 `VOICES` |
| 加一个特色音 | `scripts/vox.py` 的 `VOX` 字典 + `build.py` 的 `vox_cues` |
| 改音效落点 | `scripts/build.py` 的 `sfx_cues` |
| 改配乐织体 | `scripts/music.py` 的 `TEXTURE`（按场景类型） |
| 改混音比例 | `scripts/build.py` 里 ffmpeg 的 `volume=` 参数 |

改完先 `--audio-only` 跑一次（不渲染帧、不编码），几秒就能听。


## 西语（es-MX）

es-MX 只有两个音色，靠 `rate` / `pitch` 拉开三个角色：

| 角色 | 音色 | 参数 | 实测 |
|---|---|---|---|
| 旁白 | `es-MX-JorgeNeural` | `-5%`, `+0Hz` | 11.9 字符/秒 |
| 考考 | `es-MX-JorgeNeural` | `+8%`, `+45Hz`，`shift 1.00` | 13.5 字符/秒 |
| 小熹 | `es-MX-DaliaNeural` | `+6%`, `+25Hz`，`shift 1.00` | 13.2 字符/秒 |

**不要把 `shift` 用在中日韩那套比例上**：Jorge/Dalia 本身是成年声，
抬 1.1 倍会明显失真；靠 `pitch` 抬音高就够了。

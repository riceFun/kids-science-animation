"""配音：EdgeTTS 合成 + 变调（角色音色差异）
   输出统一为 44.1k 单声道 wav，方便直接进 ffmpeg 混音。

   变调为什么要绕这么多步：
     EdgeTTS 出的是 24kHz mp3，直接 asetrate 会把采样率也一起改，
     时间轴会整体错位。正确顺序是 aresample=44100 → asetrate → atempo 拉回时长。
"""
import hashlib
import json
import os
import re
import subprocess
import sys

CACHE = {}

# ------------------------------------------------------------------
# 音色配方
#
# EdgeTTS 的中文音色一共 8 个（2026.11 实测）：
#   zh-CN-XiaoxiaoNeural       女  News/Novel      Warm
#   zh-CN-XiaoyiNeural         女  Cartoon/Novel   Lively     ← 灵动，卡通向
#   zh-CN-YunjianNeural        男  Sports/Novel    Passion
#   zh-CN-YunxiNeural          男  Novel           Lively, Sunshine  ← 旁白
#   zh-CN-YunxiaNeural         男  Cartoon/Novel   Cute       ← 唯一的童声
#   zh-CN-YunyangNeural        男  News            Professional
#   zh-CN-liaoning-XiaobeiNeural / zh-CN-shaanxi-XiaoniNeural   方言
#
# 选型结论：
#   考考 = Yunxia（童声本体，只做 +5% 微调，不动共振峰）
#   小熹 = Xiaoyi（少女、气息浅）+ 抬高 26%，变异成幼兽
#   旁白 = Yunxi（年轻男声，-5% 放慢）
#
# 为什么不给小熹用 Yunxia：会和考考撞音色，观众分不清谁在说话。
# 为什么不给小熹用 Xiaoxiao：成年女声抬高会变成"阿姨假声"，共振峰不跟着走。
# 为什么考考不做大比例 shift：童声本来就对，抬多了像花栗鼠。
# ------------------------------------------------------------------
VOICES = {
    "narrator": {
        "voice": "zh-CN-YunxiNeural", "rate": "-5%", "pitch": "+0Hz", "shift": 1.00,
        "fallback": ["zh-CN-YunyangNeural"],
    },
    "kao": {
        "voice": "zh-CN-YunxiaNeural", "rate": "-6%", "pitch": "+2Hz", "shift": 1.05,
        "fallback": ["zh-CN-YunxiNeural"],
    },
    "xi": {
        # 用晓晓 + 只抬 1.14：音高比 Xiaoyi 方案低一档（约 313 Hz），
        # 但齿音干净。试听对比后选它——4 分钟的片子，耐听比「够卡通」重要
        "voice": "zh-CN-XiaoxiaoNeural", "rate": "+6%", "pitch": "+10Hz", "shift": 1.14,
        # 降级链要保持接近的音高：Xiaoyi 基频比晓晓高 60Hz，所以用原声不再抬
        "fallback": [("zh-CN-XiaoyiNeural", {"shift": 1.00, "pitch": "+0Hz"}),
                     ("zh-CN-YunxiaNeural", {"shift": 1.20})],
    },
}


def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"命令失败: {' '.join(cmd)}\n{r.stderr[-800:]}")
    return r.stdout


def probe(path):
    """返回时长（秒）"""
    out = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "csv=p=0", path])
    return float(out.strip())


def _speak_text(seg):
    """TTS 念什么。

    优先 text / say。quiz 段通常两者都没有——题目只画在横幅上，
    小孩不识字就等于没出题，所以这里自动把题目和选项拼成一句话念出来。
    拼出来的串不进字幕（字幕只认 text），避免和题头文字重复。
    """
    t = (seg.get("text") or seg.get("say") or "").strip()
    if t:
        return t
    if seg.get("type") == "song" and seg.get("song"):
        # 每句单独断句：句号给 TTS 一个短停顿，念出来才有童谣的节奏，
        # 连成一句会变成背书
        lines = [str(x).strip() for x in seg["song"] if str(x).strip()]
        return "".join(l + "。" for l in lines)
    if seg.get("type") == "quiz":
        q = (seg.get("q") or "").strip()
        if not q:
            return ""
        opts = [str(o).strip() for o in (seg.get("options") or []) if str(o).strip()]
        if not opts:
            return q
        marks = ["第一", "第二", "第三"]
        return q + "".join(f" {marks[i]}，{o}。" for i, o in enumerate(opts[:3]))
    return ""


def _key(text, cfg):
    return hashlib.md5(
        f"{text}|{cfg['voice']}|{cfg['rate']}|{cfg['pitch']}|{cfg['shift']}".encode()
    ).hexdigest()[:12]


def synthesize(text, role, out_wav, cache_dir, force=False, mp3_hint=None, cfg=None):
    """合成一句台词，返回 (wav 路径, 时长秒)。同样的文本+音色会复用缓存。

    mp3_hint：已经批量下好的 mp3（synth_all 的并发预取），跳过联网直接变调。
    cfg：段级覆盖过的配置（比如儿歌降速）。不传就按 role 取默认。
    """
    cfg = cfg or VOICES.get(role, VOICES["narrator"])
    key = _key(text, cfg)
    cached = os.path.join(cache_dir, f"vo_{key}.wav")
    if os.path.exists(cached) and not force:
        return cached, probe(cached)

    import asyncio
    import edge_tts

    os.makedirs(cache_dir, exist_ok=True)
    mp3 = os.path.join(cache_dir, f"vo_{key}.mp3")

    async def go(name, path):
        comm = edge_tts.Communicate(text, name, rate=cfg["rate"], pitch=cfg["pitch"])
        await comm.save(path)

    if mp3_hint and os.path.exists(mp3_hint):
        # 批量预取成功，直接用
        mp3 = mp3_hint
    else:
        # 主音色失败就顺着降级链往下试（换机器 / 换区域时音色表可能不同）
        last = None
        for item in [cfg["voice"]] + list(cfg.get("fallback", [])):
            name, over = (item, {}) if isinstance(item, str) else item
            c = {**cfg, **over}
            try:
                asyncio.run(go(name, mp3))
                cfg = c
                last = None
                break
            except Exception as e:  # noqa: BLE001
                last = e
                print(f"  ! 音色 {name} 不可用，降级：{e}")
        if last:
            raise last

    af = ["aresample=44100"]
    if abs(cfg["shift"] - 1.0) > 0.005:
        af.append(f"asetrate={int(44100 * cfg['shift'])}")
        af.append(f"atempo={1 / cfg['shift']:.5f}")
    # 尾巴上 edge-tts 常留 80ms 静音，统一裁掉，节奏更紧
    af.append("areverse,atrim=start=0.06,areverse")

    if not os.path.exists(mp3) or os.path.getsize(mp3) < 1024:
        raise RuntimeError(f"音频为空（{os.path.basename(mp3)}）：{text[:24]}")
    _run(["ffmpeg", "-y", "-v", "error", "-i", mp3, "-af", ",".join(af),
          "-ac", "1", "-ar", "44100", cached])
    os.remove(mp3)
    return cached, probe(cached)


async def _prefetch(tasks, concurrency):
    """并发把还没缓存的 mp3 拉下来。单条失败不抛，留给 synthesize 走降级链。"""
    import asyncio

    import edge_tts

    sem = asyncio.Semaphore(max(1, concurrency))
    stat = {"ok": 0, "fail": 0}

    async def one(t):
        async with sem:
            try:
                # 必须用 plan 里已经合并过段级覆盖的 cfg，
                # 否则儿歌的 rate=-20% 会在这一步被丢掉，预取回一个快版
                cfg = t["cfg"]
                comm = edge_tts.Communicate(t["text"], cfg["voice"],
                                            rate=cfg["rate"], pitch=cfg["pitch"])
                await comm.save(t["mp3"])
                # EdgeTTS 偶尔会"成功"写出 0 字节文件（服务端没吐音频）。
                # 这种必须删掉当失败处理，否则会被缓存住，后面每次都拿它去转码。
                if os.path.getsize(t["mp3"]) < 1024:
                    os.remove(t["mp3"])
                    raise RuntimeError("空音频")
                stat["ok"] += 1
            except Exception as e:  # noqa: BLE001
                stat["fail"] += 1
                if stat["fail"] == 1:
                    print(f"   ! 预取失败示例：{type(e).__name__}: {e}")

    await asyncio.gather(*[one(t) for t in tasks])
    return stat["ok"], stat["fail"]


_SENT_RE = re.compile(r"(?<=[。！？!?])")


def split_sentences(text):
    """按句号/问号/感叹号切句，保留标点。配音和字幕共用这一套切分。"""
    text = (text or "").strip()
    if not text:
        return []
    parts = [p.strip() for p in _SENT_RE.split(text) if p.strip()]
    # 「？！」这种连写标点会被切成只剩标点的碎片，而 EdgeTTS 对纯标点返回空音频
    # （进而写进缓存变成 0 字节）。把没有文字的碎片并回上一句。
    merged = []
    for p in parts:
        if merged and not re.search(r"[0-9A-Za-z\u4e00-\u9fff]", p):
            merged[-1] += p
        else:
            merged.append(p)
    return merged or [text]


def _concat_wavs(paths, out_path, gap=0.12, sr=44100):
    """把逐句 wav 拼成整段，句间插一小段静音；返回每句起点偏移与总时长。"""
    import wave

    import numpy as np

    pieces, offs, t = [], [], 0.0
    gap_n = int(round(sr * gap))
    for i, p in enumerate(paths):
        with wave.open(p, "rb") as w:
            a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        offs.append(round(t, 3))
        pieces.append(a)
        t += len(a) / sr
        if i < len(paths) - 1:
            pieces.append(np.zeros(gap_n, dtype=np.int16))
            t += gap_n / sr
    with wave.open(out_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(np.concatenate(pieces).tobytes())
    return offs, round(t, 3)


def synth_all(segments, cache_dir, force=False, jobs=6):
    """逐句合成再拼段，把结果写回 segment['__vo'] / __voDur / __chunks。

    为什么逐句：
      整段合成后只能按字数猜每句在哪儿，而 TTS 的语速和停顿并不均匀——
      实测一段 11 秒的旁白，字幕会漂到 1.2 秒以上；再加上 wav 首尾自带静音，
      按整段时长分摊会让越靠后的句子越晚。
      逐句合成能拿到每句精确时长，字幕直接锚在真实句首，不用猜。
    """
    import asyncio

    os.makedirs(cache_dir, exist_ok=True)

    plan = []
    for i, seg in enumerate(segments):
        text = _speak_text(seg)
        if not text:
            continue
        role = seg.get("voice") or ("kao" if seg.get("speaker") == "kao" else
                                    "xi" if seg.get("speaker") == "xi" else "narrator")
        cfg = dict(VOICES.get(role, VOICES["narrator"]))
        # 段级语速覆盖：儿歌要念得比对话慢，否则八句十几秒就冲完了
        if seg.get("rate"):
            cfg["rate"] = str(seg["rate"])
        units = []
        for st in split_sentences(text):
            key = _key(st, cfg)
            units.append({
                "text": st, "cfg": cfg,
                "mp3": os.path.join(cache_dir, f"vo_{key}.mp3"),
                "wav": os.path.join(cache_dir, f"vo_{key}.wav"),
            })
            units[-1]["need"] = force or not os.path.exists(units[-1]["wav"])
        plan.append({"i": i, "seg": seg, "role": role, "cfg": cfg, "units": units})

    todo = [u for p in plan for u in p["units"] if u["need"]]
    if todo and jobs > 1:
        print(f"   并发预取 {len(todo)} 句配音（{jobs} 路）")
        ok, fail = asyncio.run(_prefetch(todo, jobs))
        if fail:
            print(f"   {ok} 句就绪，{fail} 句待重试")

    for p in plan:
        seg = p["seg"]
        paths, durs = [], []
        for u in p["units"]:
            path, dur = synthesize(u["text"], p["role"], None, cache_dir,
                                   force=force, cfg=p["cfg"],
                                   mp3_hint=u["mp3"] if u["need"] else None)
            # 降级链可能换音色，缓存文件名以 synthesize 返回值为准
            paths.append(path)
            durs.append(round(dur, 3))

        if len(paths) == 1:
            seg["__vo"] = paths[0]
            seg["__voDur"] = durs[0]
            seg["__chunks"] = [{"t": 0.0, "dur": durs[0], "text": p["units"][0]["text"]}]
        else:
            joined = "|".join(u["text"] for u in p["units"])
            out = os.path.join(cache_dir, f"seg_{p['i']:02d}_{_key(joined, p['cfg'])}.wav")
            offs, total = _concat_wavs(paths, out)
            seg["__vo"] = out
            seg["__voDur"] = total
            seg["__chunks"] = [
                {"t": offs[k], "dur": durs[k], "text": p["units"][k]["text"]}
                for k in range(len(paths))
            ]
        print(f"  [{p['i']:02d}] {p['role']:8s} {seg['__voDur']:5.2f}s "
              f"({len(paths)} 句)  {_speak_text(seg)[:30]}")
    return segments


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python tts.py <script.json>")
        sys.exit(1)
    with open(sys.argv[1], encoding="utf-8") as f:
        sc = json.load(f)
    d = os.path.join(os.path.dirname(os.path.abspath(sys.argv[1])), "audio")
    synth_all(sc["segments"], d, force="--force" in sys.argv)

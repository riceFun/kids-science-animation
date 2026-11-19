#!/usr/bin/env python3
"""考考&小熹 · 一键出片

    python build.py <script.json> [选项]

   --draft         草稿档：960×540 / 15fps，只看节奏，几十秒出一版
   --fps 30        帧率（默认 30）
   --rough         切 Rough.js 手绘档
   --jobs 4        并行渲染进程数（默认按核数自动，6 进程约快 5–6 倍）
   --png           中间帧存 PNG（默认 JPEG q95，视觉无损但快一倍）
   --no-render     跳过帧渲染，用已有帧重跑音频并重新编码
   --audio-only    只重混音，不编码
   --preview 12,40 只出这几个时间点的静帧，检查排版
   --force-tts     忽略配音缓存重新合成
   --grain         编码时叠胶片颗粒（慢，但更像成片）

产物（都在 script.json 同目录）：
   timeline.json   引擎时间线
   audio/          配音缓存、bgm.wav、混音 track.wav
   frames/         帧序列
   out/<标题>.mp4  成片

时长：导演台本里的 dur 由配音自动推算（LEAD + 语音 + TAIL + hold），
      所以「4–5 分钟」是靠片段数量控制的，不是靠调语速。
"""
import argparse
import base64
import glob
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
ENGINE = os.path.join(SKILL, "assets", "engine", "engine.html")

LEAD = 0.40   # 画面出现 → 开口
TAIL = 0.60   # 说完 → 切镜
SR = 44100


# ---------------------------------------------------------------- 工具
def find_puppeteer():
    """找 puppeteer-core 的 node_modules，返回要设进 NODE_PATH 的目录"""
    cands = [
        os.environ.get("PUPPETEER_NODE_PATH", ""),
        os.path.join(SKILL, "node_modules"),
        os.path.expanduser("~/.workbuddy/node_modules"),
        "/tmp/render/node_modules",
    ]
    for c in cands:
        if c and os.path.isdir(os.path.join(c, "puppeteer-core")):
            return c
    # 全局 npm root
    try:
        r = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True)
        c = r.stdout.strip()
        if c and os.path.isdir(os.path.join(c, "puppeteer-core")):
            return c
    except Exception:  # noqa: BLE001
        pass
    return None


def read_wav(path):
    with wave.open(path, "rb") as w:
        n = w.getnframes()
        ch = w.getnchannels()
        raw = np.frombuffer(w.readframes(n), dtype="<i2").astype(np.float32) / 32768.0
    return raw.reshape(-1, ch)


def write_wav(path, data):
    # float32 + 就地裁剪：一张 4 分半的立体声轨用 float64 会吃掉 190MB，容易撞到内存上限
    pcm = (np.clip(data, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(data.shape[1])
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def mix_bed(items, total):
    """items: [(wav路径, 起始秒, 增益)] → 立体声 float 数组"""
    n = int(total * SR) + SR
    out = np.zeros((n, 2), dtype=np.float32)
    for path, at, gain in items:
        if not os.path.exists(path):
            continue
        d = read_wav(path)
        if d.shape[1] == 1:
            d = np.repeat(d, 2, axis=1)
        i0 = int(at * SR)
        if i0 >= n:
            continue
        m = min(len(d), n - i0)
        if m > 0:
            out[i0:i0 + m] += d[:m] * gain
    return out


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        print(r.stdout[-2000:])
        print(r.stderr[-2000:])
        raise SystemExit(f"失败: {' '.join(cmd[:4])} …")
    return r


def auto_jobs(scale):
    """并行度。Chrome 截图是单线程 CPU 活，多开进程近乎线性加速：
    实测 1080p 串行 5.3 帧/秒 → 6 进程 27 帧/秒（5.2×）→ 再叠 JPEG 到 55 帧/秒。
    核多也别无限开，每个 Chrome 吃 300–500MB。"""
    n = os.cpu_count() or 4
    # 默认 3 路。实测 6 路在这台机器上互相抢内存，吞吐只有单路的 1/3（7.2 vs 24 帧/秒）；
    # 每个 Chrome 峰值约 700MB，3 路 ≈ 2GB，留够余量给别的程序。
    return 3 if n >= 6 else max(1, n // 2 or 1)


_ACTIVE = []


def _kill_active():
    """中断时把还活着的分片（含其 Chrome 子进程）一起收掉。
    只 kill build 自己，分片的 node/Chrome 会成为孤儿一直占内存 —— 实测残留 21 个进程，
    下一次渲染直接掉到 1 帧/秒。"""
    for p in list(_ACTIVE):
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGKILL)
        except Exception:  # noqa: BLE001
            try:
                p.kill()
            except Exception:  # noqa: BLE001
                pass
    _ACTIVE.clear()


def _on_signal(signum, frame):
    _kill_active()
    raise SystemExit(130)


signal.signal(signal.SIGTERM, _on_signal)
signal.signal(signal.SIGINT, _on_signal)


def render_frames(node_path, tl_path, frames_dir, fps, scale, total, ext, jobs, rough, force=False,
                  scenery=None):
    """按时间切片起多个 render.js 并行渲。帧号是全局的，分片不会撞。"""
    env = dict(os.environ, NODE_PATH=node_path)
    base = ["node", os.path.join(HERE, "render.js"), ENGINE, tl_path, frames_dir,
            "--fps", str(fps), "--scale", str(scale)]
    if scenery:
        base += ["--scenery", scenery]
    if rough:
        base += ["--style", "rough"]
    if ext == "jpg":
        base += ["--jpeg", "95"]
    if force:
        base += ["--force"]

    jobs = jobs or auto_jobs(scale)
    jobs = max(1, min(jobs, int(total * fps) or 1))
    if jobs == 1:
        return run(base, env=env)

    print(f"   并行 {jobs} 进程（每个各渲一段）")
    # 日志必须落文件，不能用 stderr=PIPE：6 个 Chrome 的警告很快填满 64KB 管道，
    # 子进程卡在写 stderr 上永不退出，父进程又在一个个 communicate() 等它 —— 死锁。
    procs, logs = [], []
    for i in range(jobs):
        a0, b0 = total * i / jobs, total * (i + 1) / jobs
        lp = os.path.join(frames_dir, f".render_{i + 1}.log")
        fh = open(lp, "w", encoding="utf-8")
        logs.append((lp, fh))
        pr = subprocess.Popen(
            base + ["--from", f"{a0:.3f}", "--to", f"{b0:.3f}"], env=env,
            stdout=fh, stderr=subprocess.STDOUT,
            start_new_session=True)    # 独立进程组：超时可以连同 Chrome 一起杀
        procs.append(pr)
        _ACTIVE.append(pr)
    # 兜底超时：正常 1080p 也就 18ms/帧，给到 1s/帧还没完必然是挂住了
    # 正常 1080p 约 24 帧/秒，给到 4 帧/秒的余量就够；卡死的分片早点掐掉，
    # 否则一个卡住的分片会把整片拖到超时（实测多等 15 分钟）
    timeout = max(240, (total * fps) / jobs / 4)
    bad = 0
    for i, p in enumerate(procs):
        try:
            rc = p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            except Exception:  # noqa: BLE001
                p.kill()
            p.wait()
            rc = -9
            print(f"   分片 {i + 1}/{jobs} 超时（>{timeout:.0f}s），已结束")
        logs[i][1].close()
        if rc != 0:
            bad += 1
            tail = ""
            try:
                with open(logs[i][0], encoding="utf-8") as f:
                    tail = f.read()[-400:]
            except OSError:
                pass
            print(f"   分片 {i + 1}/{jobs} 失败 rc={rc}：{tail}")
    if bad:
        raise SystemExit(f"{bad} 个渲染分片失败，日志在 {frames_dir}/.render_*.log")



import re

_SENT = re.compile(r"(?<=[。！？!?])")
LANG = "es"          # main() 里按 --lang 覆盖；西语字幕按词切、每行更宽

def _split_es(text, maxc=38, maxlines=2):
    """西语字幕：按词切，每行 ≤ maxc 字符，最多两行一屏。
    返回结构和中文版一致：[{"lines": [...]}]——上层是按这个结构算时长的。"""
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if p.strip()]
    pages = []
    for part in parts:
        buf = ""
        lines = []
        for w in part.split():
            if len(buf) + len(w) + 1 <= maxc:
                buf = (buf + " " + w).strip()
            else:
                if buf:
                    lines.append(buf)
                buf = w
        if buf:
            lines.append(buf)
        # 每屏最多 maxlines 行
        for i in range(0, len(lines), maxlines):
            pages.append({"lines": lines[i:i + maxlines]})
    return pages


def split_subs(text, maxc=None, maxlines=2):
    """把一段旁白切成「一屏能看完」的字幕条：先按句，再按逗号，最后硬折行"""
    if LANG == "es":
        return _split_es(text, maxc or 38, maxlines)
    maxc = maxc or 21
    parts = [p.strip() for p in _SENT.split(text) if p.strip()]
    # 同样别让「？！」切成只有标点的一屏
    merged = []
    for p in parts:
        if merged and not re.search(r"[0-9A-Za-z\u4e00-\u9fff]", p):
            merged[-1] += p
        else:
            merged.append(p)
    parts = merged
    chunks = []
    for part in parts:
        if len(part) <= maxc * maxlines:
            chunks.append(part)
        else:
            buf = ""
            for q in [x for x in re.split(r"(?<=[，、：；,])", part) if x.strip()]:
                if len(buf) + len(q) <= maxc:
                    buf += q
                else:
                    if buf:
                        chunks.append(buf)
                    buf = q
            if buf:
                chunks.append(buf)
    def lines_of(c):
        if len(c) <= maxc:
            return [c]
        if len(c) <= maxc * maxlines:
            # 两行时在中间附近找标点断，别把最后两个字单独甩到第二行
            mid = len(c) // 2
            best, bestd = None, 10 ** 9
            for i, ch in enumerate(c[:-1]):
                if ch in "，、：；,;":
                    d = abs(i - mid)
                    if d < bestd:
                        best, bestd = i, d
            if best is not None and max(best + 1, len(c) - best - 1) <= maxc:
                cut = best + 1
            elif best is not None and bestd <= 4:
                # 贴标点会超出两三个字：宁可略宽，也别断在词中间（"做/的"）
                cut = best + 1
            else:
                cut = mid
            return [c[:cut], c[cut:]]
        # 超长句（两行都装不下）：切两行，贴着最靠近中点的标点下刀。
        # 不能用「按 maxc 切片再取前两片」——43 字会被切成 21+21，最后一个字直接丢掉。
        mid = len(c) // 2
        best, bestd = None, 10 ** 9
        for i, ch in enumerate(c[:-1]):
            if ch in "，、：；,;":
                d = abs(i - mid)
                if d < bestd:
                    best, bestd = i, d
        cut = best + 1 if best is not None else mid
        return [c[:cut], c[cut:]]

    return [{"lines": lines_of(c)} for c in chunks]


def build_subs(seg, vo_dur):
    """字幕时间点。

    有逐句配音信息（__chunks）时：每一屏锚在该句的**真实起始时刻**，句内再按字数分页。
    没有时（旧缓存 / 无配音）退化成按整段字数分摊——那是猜，会漂。
    """
    text = seg.get("sub")
    if not text:
        return []

    voice_chunks = seg.get("__chunks") or []
    if voice_chunks:
        out = []
        for c in voice_chunks:
            pages = split_subs(c["text"])
            w = [len("".join(p["lines"])) for p in pages] or [1]
            total = sum(w) or 1
            acc = 0.0
            for p, wi in zip(pages, w):
                # LEAD：语音在段首 0.4s 后才出声；c["t"] 是该句在语音里的偏移
                out.append({"t": round(LEAD + c["t"] + acc, 2), "lines": p["lines"]})
                acc += wi / total * max(c["dur"], 0.2)
        return out

    chunks = split_subs(text)
    # 每句加 4 个「停顿字」的权重：TTS 念完一句会顿一下，按纯字数分摊会让短句偏快、字幕先消失
    weights = [len("".join(c["lines"])) + 4 for c in chunks]
    total = sum(weights) or 1
    t, out = LEAD, []
    for c, w in zip(chunks, weights):
        out.append({"t": round(t, 2), "lines": c["lines"]})
        t += w / total * max(vo_dur, 0.5)
    return out


# ---------------------------------------------------------------- 对齐校验
def _probe_dur(path):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "default=nw=1:nk=1", path],
                             capture_output=True, text=True).stdout.strip()
        return float(out)
    except Exception:  # noqa: BLE001
        return 0.0


def speech_spans(audio_path):
    """用静音检测把一条音轨切成「说话区间」，用于反向核对语音真实落点。"""
    total = _probe_dur(audio_path)
    if total <= 0:
        return []
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-i", audio_path,
                            "-af", "silencedetect=noise=-40dB:d=0.12", "-f", "null", "-"],
                           capture_output=True, text=True)
    except OSError:
        return []
    sils, cur = [], None
    for line in r.stderr.splitlines():
        if "silence_start:" in line:
            cur = float(line.split("silence_start:")[1].split()[0])
        elif "silence_end:" in line and cur is not None:
            sils.append((cur, float(line.split("silence_end:")[1].split()[0])))
            cur = None
    if cur is not None:
        sils.append((cur, total))
    spans, t = [], 0.0
    for a, b in sils:
        if a - t > 0.05:
            spans.append((t, a))
        t = max(t, b)
    if total - t > 0.05:
        spans.append((t, total))
    return spans


def check_alignment(segs, lead, audio_path=None, drift_tol=0.35):
    """字幕 / 画面 / 语音三方对齐全检。

    结构层：语音是否溢出段尾、字幕是否落在语音区间内、字幕是否倒序、相邻语音是否重叠。
    音轨层（给了 audio_path 时）：实测每段语音起点，和预期比对，报最大偏差。
    返回 (问题列表, [(段号, 偏差秒)], 段落行)。
    """
    bad, rows = [], []
    for i, s in enumerate(segs):
        vo = s.get("__voDur", 0.0)
        if vo <= 0:
            continue
        st, dur = s["start"], s["dur"]
        sp0, sp1 = st + lead, st + lead + vo
        if sp1 > st + dur + 0.002:
            bad.append(f"[{i:02d}] 语音超出段尾 {sp1 - (st + dur):+.2f}s —— 话没说完画面就切走了")
        prev = None
        for c in (s.get("subs") or []):
            # 字幕 t 是「段内相对时间」，校验时换算成绝对时刻
            at = st + c["t"]
            if at < sp0 - 0.06:
                bad.append(f"[{i:02d}] 字幕 {at:.2f}s 早于开口 {sp0:.2f}s")
            if at > sp1 + 0.06:
                bad.append(f"[{i:02d}] 字幕 {at:.2f}s 晚于说完 {sp1:.2f}s")
            if prev is not None and at < prev:
                bad.append(f"[{i:02d}] 字幕时间倒序")
            prev = at
        rows.append({"i": i, "type": s.get("type"), "sp0": sp0, "sp1": sp1,
                     "end": st + dur, "n": len(s.get("subs") or [])})

    for a, b in zip(rows, rows[1:]):
        if a["sp1"] > b["sp0"] + 0.02:
            bad.append(f"[{a['i']:02d}→{b['i']:02d}] 两段语音重叠 {a['sp1'] - b['sp0']:.2f}s")

    detail = []
    if audio_path and os.path.exists(audio_path):
        spans = speech_spans(audio_path)
        for r in rows:
            if r["sp1"] - r["sp0"] < 0.2:
                continue
            best = min(spans, key=lambda sp: abs(sp[0] - r["sp0"]), default=None)
            if best is None:
                bad.append(f"[{r['i']:02d}] 音轨里找不到这段语音")
                continue
            drift = best[0] - r["sp0"]
            detail.append((r["i"], round(drift, 3)))
            if abs(drift) > drift_tol:
                bad.append(f"[{r['i']:02d}] 语音起点偏 {drift:+.2f}s"
                           f"（预期 {r['sp0']:.2f}，实测 {best[0]:.2f}）")
    return bad, detail, rows


# ---------------------------------------------------------------- 时间线
def compile_timeline(segments):
    """由配音时长推算每段 dur，再累加成 start"""
    t = 0.0
    for i, s in enumerate(segments):
        s["lang"] = LANG
        vo = s.get("__voDur", 0.0)
        hold = s.get("hold", 0.0)
        floor = s.get("min", 4.0)
        dur = max(floor, LEAD + vo + TAIL + hold)
        s["dur"] = round(dur, 2)
        s["start"] = round(t, 3)
        t += s["dur"]
        # 只有「旁白正文」才走字幕；气泡台词和正文相同时不重复出字幕
        if s.get("say") and not s.get("text"):
            s["text"] = s["say"]
        # quiz / song / title / outro 例外：内容已经整块画在屏幕上了
        #（题目横幅、歌词板、片头标题、告别卡）。再出字幕就是同一句话出现两次
        if s.get("text") and s.get("text") != s.get("say") and s.get("type") not in ("quiz", "song", "title", "outro"):
            s["sub"] = s["text"]
        if s.get("sub"):
            s["subs"] = build_subs(s, s.get("__voDur", 0.0))
    return round(t, 3)


# ---------------------------------------------------------------- 音效落点
def sfx_cues(segments):
    """所有音效落点都从时间线推导，不手写时间码"""
    c = []
    for i, s in enumerate(segments):
        st, dur, ty = s["start"], s["dur"], s["type"]
        if i > 0:
            c.append(("sfx_whoosh.wav", max(0, st - 0.30), 0.42))
        if ty == "show":
            c.append(("sfx_sparkle.wav", st + 0.22, 0.50))
        elif ty == "card":
            for j, p in enumerate(s.get("points", [])[:4]):
                at = p.get("at", 0.12 + j * 0.16)
                c.append(("sfx_pop.wav", st + at * dur, 0.55))
        elif ty == "quiz":
            rev = s.get("revealAt", 0.62)
            c.append(("sfx_riser.wav", st + max(rev * dur - 1.3, 0.2), 0.42))
            c.append(("sfx_sparkle.wav", st + rev * dur, 0.62))
        elif ty == "outro":
            c.append(("sfx_sparkle.wav", st + 0.15, 0.55))
        elif ty == "title":
            c.append(("sfx_boing.wav", st + 0.45, 0.50))
    return c


# ---------------------------------------------------------------- 角色特色音
def vox_cues(segments):
    """小熹的专属音节（共振峰合成）。
       规则：谁说话配谁的声音，情绪点追加音节，不手写时间码。"""
    c = []
    for s in segments:
        st = s["start"]
        if s.get("voice") == "xi":
            c.append(("vox_chirp.wav", st + 0.30, 0.30))       # 开口前的"啾"
        if s.get("xiExpr") == "think":
            c.append(("vox_coo.wav", st + 0.42, 0.30))         # 歪头想：下滑再上挑
        if s.get("xiExpr") == "giggle":
            c.append(("vox_trill.wav", st + 0.80, 0.26))       # 咯咯笑：18Hz 颤音
        if s.get("xiTail") == "glow":
            c.append(("vox_insight.wav", st + 0.34, 0.44))     # 尾巴亮：知识音
        if s.get("type") == "outro":
            c.append(("vox_trill.wav", st + 0.60, 0.30))
    return c


# ---------------------------------------------------------------- 主流程
def preflight():
    """缺依赖时给出人话提示，而不是 ModuleNotFoundError 堆栈"""
    missing = []
    for mod in ("numpy", "edge_tts"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        raise SystemExit(
            "缺少 Python 依赖: " + ", ".join(missing) +
            "\n换一个装了这些包的解释器，例如：\n" +
            "  /path/to/python3 " + os.path.abspath(__file__) + " ...")
    for exe in ("ffmpeg", "ffprobe", "node"):
        if shutil.which(exe) is None:
            raise SystemExit(f"找不到 {exe}，请先安装")


def main():
    preflight()
    T0 = time.perf_counter()
    _marks = []

    def step(label):
        """记一段耗时并打印——出片慢的时候先看这里，别瞎猜瓶颈"""
        now = time.perf_counter()
        prev = _marks[-1][1] if _marks else T0
        _marks.append((label, now))
        print(f"   ⏱ {label} {now - prev:.1f}s")

    def summary():
        total = time.perf_counter() - T0
        parts = []
        for i, (label, now) in enumerate(_marks):
            prev = _marks[i - 1][1] if i else T0
            d = now - prev
            parts.append(f"{label} {d:.0f}s({d / total * 100:.0f}%)")
        print(f"\n耗时合计 {total:.0f}s：" + " · ".join(parts))

    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--fps", type=float, default=None)
    ap.add_argument("--rough", action="store_true")
    ap.add_argument("--jobs", type=int, default=0,
                    help="并行渲染进程数，0=按核数自动")
    ap.add_argument("--png", action="store_true",
                    help="中间帧存 PNG（默认 JPEG q95，视觉无损但慢一倍）")
    ap.add_argument("--force", action="store_true",
                    help="已存在的帧也重渲（默认增量跳过）")
    ap.add_argument("--no-render", action="store_true", dest="no_render",
                    help="跳过帧渲染，用已有帧重跑音频并重新编码")
    ap.add_argument("--audio-only", action="store_true", dest="audio_only",
                    help="只重混音，不编码")
    ap.add_argument("--preview", default=None)
    ap.add_argument("--force-tts", action="store_true", dest="force_tts")
    ap.add_argument("--tts-jobs", type=int, default=6, dest="tts_jobs",
                    help="配音并发路数（默认 6）。被限流就设 1 退回串行")
    ap.add_argument("--check-align", action="store_true", dest="check_align",
                    help="只做字幕/画面/语音对齐校验，出报告后退出（不编码）")
    ap.add_argument("--no-archive", action="store_true", dest="no_archive",
                    help="不把产物归档到桌面频道目录")
    ap.add_argument("--lang", default=None, choices=["es", "zh"],
                    help="配音语言；不写则跟随台本 meta.lang，缺省 es（墨西哥西语）")
    ap.add_argument("--no-credits-card", action="store_true", dest="no_credits_card",
                    help="不在片尾插图片来源卡（每张图右上角的角标仍在）")
    ap.add_argument("--grain", action="store_true")
    a = ap.parse_args()

    fps = a.fps or (15 if a.draft else 30)
    scale = 0.5 if a.draft else 1.0
    # 只查对齐时不需要渲帧，省几分钟
    if a.check_align:
        a.no_render = True

    root = os.path.dirname(os.path.abspath(a.script))
    with open(a.script, encoding="utf-8") as f:
        sc = json.load(f)

    # 语言优先级：--lang > 台本 meta.lang > 默认 es
    # 不这么写的话，跑中文老台本会突然变成西语配音
    global LANG
    LANG = a.lang or (sc.get("meta") or {}).get("lang") or "es"
    import tts as _tts
    _tts.set_lang(LANG)
    segs = sc["segments"]
    meta = sc.get("meta", {})
    title = meta.get("title") or "episode"

    # 每集自带场景脚本（可选）：epXX/scenery.js
    # 不做背景库、不做话题映射；这一集需要什么世界，就在这里用代码画什么。
    scenery_path = os.path.join(root, "scenery.js")
    if not os.path.exists(scenery_path):
        scenery_path = None
    else:
        print(f"   场景脚本：{os.path.basename(scenery_path)}")

    # 实拍图：读成 base64 内联。file:// 页面里 <image href="本地路径"> 会被 Chrome 当跨源拦掉，
    # 内联是最省事也最稳的做法（时间线 json 会变大，但只在本地用）。
    photo_credits = []
    for s in segs:
        src = s.get("photo")
        if not src or str(src).startswith("data:"):
            continue
        p = src if os.path.isabs(src) else os.path.join(root, src)
        if not os.path.exists(p):
            raise SystemExit(f"找不到图片：{p}")
        mime = "image/png" if p.lower().endswith(".png") else "image/jpeg"
        with open(p, "rb") as f:
            s["photo"] = f"data:{mime};base64," + base64.b64encode(f.read()).decode()
        s["photoSrc"] = os.path.relpath(p, root)
        if s.get("credit"):
            photo_credits.append(str(s["credit"]).strip())

    # 封面用实拍图：coverPhoto 可以是单张，也可以是两张（左虎右狮）
    for s in segs:
        cp = s.get("coverPhoto")
        if not cp:
            continue
        arr = cp if isinstance(cp, list) else [cp]
        data = []
        for pth in arr[:2]:
            fp = pth if os.path.isabs(pth) else os.path.join(root, pth)
            if not os.path.exists(fp):
                raise SystemExit(f"封面图不存在：{fp}")
            mime = "image/png" if fp.lower().endswith(".png") else "image/jpeg"
            with open(fp, "rb") as f:
                data.append(f"data:{mime};base64," + base64.b64encode(f.read()).decode())
        s["coverPhotoData"] = data

    # 有署名要求的图，默认在片尾（outro 之前）插一张来源卡。
    # 每张图右上角本来就带角标，觉得卡片多余就 meta.creditsCard=false 或 --no-credits-card。
    want_card = meta.get("creditsCard", True) and not a.no_credits_card
    if photo_credits and want_card:
        uniq = list(dict.fromkeys(photo_credits))
        at = next((i for i, s in enumerate(segs) if s.get("type") == "outro"), len(segs))
        segs.insert(at, {
            "type": "credits",
            "bg": segs[at - 1].get("bg") if at else "meadow_day",
            "min": max(6.0, 2.2 + len(uniq) * 1.6),
            "title": "图片来源" if LANG == "zh" else "Créditos",
            "text": ("本集的照片来自这几位摄影师，谢谢他们免费分享。"
                     if LANG == "zh" else
                     "Las fotos de este episodio vienen de estos fotógrafos. ¡Gracias!"),
            "items": [{"text": c} for c in uniq],
        })
        print(f"   署名卡：{len(uniq)} 条来源")

    audio_dir = os.path.join(root, "audio")
    frames_dir = os.path.join(root, "frames" if scale >= 1 else "frames_draft")
    # --no-render 忘了带 --draft 时，会跑去正片目录找草稿帧，白报「没有帧」。
    # 哪个目录有帧就用哪个。
    if not glob.glob(os.path.join(frames_dir, "f00001.*")):
        alt = os.path.join(root, "frames_draft" if scale >= 1 else "frames")
        if glob.glob(os.path.join(alt, "f00001.*")):
            print(f"   ! {os.path.basename(frames_dir)} 里没帧，改用 {os.path.basename(alt)}")
            frames_dir = alt
    out_dir = os.path.join(root, "out")
    for d in (audio_dir, frames_dir, out_dir):
        os.makedirs(d, exist_ok=True)

    # 1) 配音
    print("① 配音")
    sys.path.insert(0, HERE)
    import tts
    tts.synth_all(segs, audio_dir, force=a.force_tts, jobs=a.tts_jobs)
    step("配音")

    # 2) 时间线
    total = compile_timeline(segs)
    tl_path = os.path.join(root, "timeline.json")
    clean = [{k: v for k, v in s.items() if not k.startswith("__")} for s in segs]
    with open(tl_path, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "segments": clean}, f, ensure_ascii=False, indent=1)
    m, s_ = divmod(int(round(total)), 60)
    print(f"② 时间线：{len(segs)} 段 / {m} 分 {s_:02d} 秒  → timeline.json")
    if not (240 <= total <= 330):
        print(f"   ! 时长 {total:.0f}s 不在 4–5 分钟区间，增减片段数量")
    # 儿童向硬要求：画面上的字必须同时被读出来。
    # 观众是 6 岁小孩，认不全字，只有字没有声音 = 那一段等于空白。
    silent = [f"[{i:02d}] {s.get('type')}" for i, s in enumerate(segs)
              if not ((s.get("text") or "").strip() or (s.get("say") or "").strip())
              and s.get("type") in ("card", "quiz", "outro")]
    if silent:
        print(f"   ! 有字无声：{', '.join(silent)}")
        print("     这些段落画面上有文字但没配音，给它们补 text 字段")

    # 儿童向：画面主体是「要讲的科普知识」，不是两个角色从头聊到尾。
    # 对话只承担钩子 / 转场 / 情绪，知识点必须落到 show / card / quiz 这类知识画面。
    body = [s for s in segs if s.get("type") != "title"]
    talk_n = sum(1 for s in body if s.get("type") == "talk")
    # figure 是 show 的新形态（都必须给 figure），算知识画面
    know_n = sum(1 for s in body if s.get("type") in ("show", "figure", "card", "quiz"))
    if body:
        tr = talk_n / len(body)
        if tr > 0.42:
            print(f"   ! 对话占比 {tr:.0%}（{talk_n}/{len(body)} 段）：知识才是主角，"
                  f"把 talk 压到 40% 以内，改用 show/card 讲原理")
        if know_n < max(3, len(body) * 0.3):
            print(f"   ! 知识画面只有 {know_n} 段：每个知识点都要有 figure / card，别只靠嘴说")

    # 背景不能全片一张：同一个世界讲三个知识点，画面就死了。
    bgs = [s.get("bg") for s in segs if s.get("bg")]
    if len(segs) >= 12 and bgs:
        uniq = len(set(bgs))
        top = max(bgs.count(b) for b in set(bgs)) / len(bgs)
        if uniq < 3 or top > 0.6:
            print(f"   ! 背景太单一：{uniq} 种、最常见一种占 {top:.0%}。"
                  f"按文案场景切背景，一集至少 3 个不同世界")

    # 场景名必须在 epXX/scenery.js 里注册过。写错名字会被引擎静默退回默认背景，
    # 成片一看才发现「整集都是草地」，那时已经渲完了。
    BUILTIN_BG = {"meadow_day", "meadow_night", "forest", "underwater", "sky",
                  "room", "room_storm", "micro", "storm"}
    have = set(BUILTIN_BG)
    if scenery_path:
        with open(scenery_path, encoding="utf-8") as sf:
            have |= set(re.findall(r'scene\(\s*["\']([^"\']+)["\']', sf.read()))
    unknown = sorted(set(b for b in bgs if b not in have))
    if unknown:
        print(f"   ! 未注册的场景名：{', '.join(unknown)}")
        print("     在 scenery.js 里用 SCENE_KIT.scene(\"名字\", ...) 画出来，否则会退回默认背景")

    # 具体对象要画准。figure 名必须在本集 scenery.js 里注册过
    fig_have = set()
    if scenery_path:
        with open(scenery_path, encoding="utf-8") as sf:
            fig_have = set(re.findall(r'figure\(\s*["\']([^"\']+)["\']', sf.read()))
    figs = [s.get("figure") for s in segs if s.get("figure")]
    figs += [s.get("cover") for s in segs if s.get("cover")]
    miss_fig = [f for f in figs if f not in fig_have]
    if miss_fig:
        print(f"   ! 未注册的 figure：{', '.join(miss_fig)}")
        print("     用 scenery.js 的 SCENE_KIT.figure(\"名字\", ...) 画出来")

    # 开场钩子：先给一个具体场面，再报题。上来就讲主题，观众容易划走
    hooks = [s for s in segs if s.get("hook")]
    if not hooks:
        print("   ! 开头没有钩子：前 10–15 秒先给一个具体场面（谁在做什么、出了什么事），别一上来就报题")
    else:
        first = min(i for i, s in enumerate(segs) if s.get("hook"))
        if first > 0:
            print(f"   ! 钩子从第 {first} 段才开始：钩子要放在 title 前面")
        hd = sum(s.get("dur", 0) for s in hooks)
        if hd and not (10 <= hd <= 20):
            print(f"   ! 钩子 {hd:.1f}s：控制在 10–20 秒，太长就变成正片了")

    # 儿歌句数：4–6 句最舒服，超过 6 句歌词会挤出框
    for _sg in segs:
        if _sg.get("type") == "song":
            n = len(_sg.get("song") or [])
            if n > 6:
                print(f"   ! 儿歌 {n} 句：控制在 4–6 句，多了会挤出歌词框")

    # 片头同时是封面：没有封面主体，缩略图就看不出这集讲什么
    no_cover = [i for i, s in enumerate(segs) if s.get("type") == "title" and not s.get("cover")]
    if no_cover:
        print(f"   ! 片头缺封面主体（title 缺 cover）：第 {', '.join(str(i) for i in no_cover)} 段")
        print("     片头这一帧要当封面用，必须把这一集讲的东西画在右半边")

    # show 必须画具体东西；没 figure 就是画面里会出现「缺图」
    no_fig = [i for i, s in enumerate(segs) if s.get("type") == "show" and not s.get("figure")]
    if no_fig:
        print(f"   ! 这些 show 段没给 figure：{', '.join(str(i) for i in no_fig)}")
        print("     show 已经不允许用「圆盘+图标」占位，必须画这一段讲的那个东西")

    # emblem 已废弃：圆盘里那个通用图标和文案无关
    ems = [s.get("emblem") for s in segs if s.get("emblem")]
    if ems:
        print(f"   ! 有 {len(ems)} 段还在用 emblem（已废弃，不会渲染）："
              f"{', '.join(sorted(set(ems)))} —— 改用 figure 画具体对象，或 photo 上真图")

    # 景别：全片一个中景，画面再稳也会看困。
    shots = [s.get("shot") or "medium" for s in segs]
    if len(segs) >= 12 and len(set(shots)) < 2:
        print("   ! 景别单一：全片都是中景。情绪点用 shot:\"close\"（大脸），"
              "讲近处原理用 shot:\"macro\"（微距）")

    # 连着四段同一类型，观众会觉得画面没动过
    streak = 1
    for i in range(1, len(segs)):
        streak = streak + 1 if segs[i].get("type") == segs[i - 1].get("type") else 1
        if streak == 4:
            print(f"   ! [{i - 3:02d}–{i:02d}] 连续 4 段都是 {segs[i].get('type')}，换个景别或换种场景类型")

    # 字幕 / 画面 / 语音 三方的结构对齐（音轨层校验在混音后）
    bad0, _, _ = check_alignment(segs, LEAD)
    if bad0:
        print(f"   ! 对齐问题 {len(bad0)} 处：{bad0[0]}")
        print("     详见 build.py --check-align 的报告")
    step("时间线")

    if a.preview:
        print("③ 预览帧")
        np_path = find_puppeteer()
        env = dict(os.environ, NODE_PATH=np_path or "")
        run(["node", os.path.join(HERE, "render.js"), ENGINE, tl_path, frames_dir,
             "--preview", a.preview, "--scale", "1"]
            + (["--scenery", scenery_path] if scenery_path else [])
            + (["--style", "rough"] if a.rough else []), env=env)
        # 预览图固定 PNG：就几张，看排版要无损
        print(f"   看 {os.path.basename(frames_dir)}/preview_*.png")
        step("预览帧")
        summary()
        return

    # 3) 帧
    ext = "png" if a.png else "jpg"
    if not a.no_render and not a.audio_only:
        print("③ 渲染帧（这一步最慢）")
        np_path = find_puppeteer()
        if not np_path:
            raise SystemExit("找不到 puppeteer-core：npm i puppeteer-core 或设 PUPPETEER_NODE_PATH")
        # 时间线一变（改文案、补配音都会变），旧帧的每一帧都对应错的时间点。
        # 增量渲染只认「文件在不在」，会把整片存成音画错位 —— 必须自动作废重渲。
        # 场景脚本也要进签名：改了画法（同样的文案、不同的世界）同样得重新渲染
        h = hashlib.md5(json.dumps(clean, sort_keys=True, ensure_ascii=False).encode("utf-8"))
        if scenery_path:
            with open(scenery_path, "rb") as sf:
                h.update(sf.read())
        sig = h.hexdigest()[:12]
        os.makedirs(frames_dir, exist_ok=True)
        marker = os.path.join(frames_dir, ".timeline_sig")
        old = ""
        if os.path.exists(marker):
            with open(marker, encoding="utf-8") as f:
                old = f.read().strip()
        if old and old != sig and not a.force:
            print(f"   ! 时间线已变（{old} → {sig}），旧帧作废，自动全量重渲")
            a.force = True
        render_frames(np_path, tl_path, frames_dir, fps, scale, total, ext, a.jobs, a.rough, a.force,
                      scenery=scenery_path)
        # 签名必须在渲染**成功之后**才写：中途失败（并发过高、Chrome 崩）时如果已经写了，
        # 下次重跑会认为帧是新的，直接跳过 —— 成片里就会留下上一个版本时间线的旧帧。
        with open(marker, "w", encoding="utf-8") as f:
            f.write(sig)
        step("渲染帧")

    # 4) 音轨
    print("④ 混音")
    sfx_dir = os.path.join(audio_dir, "sfx")
    os.makedirs(sfx_dir, exist_ok=True)
    run([sys.executable, os.path.join(HERE, "sfx.py"), sfx_dir])

    vox_dir = os.path.join(audio_dir, "vox")
    os.makedirs(vox_dir, exist_ok=True)
    run([sys.executable, os.path.join(HERE, "vox.py"), vox_dir])

    bgm = os.path.join(audio_dir, "bgm.wav")
    run([sys.executable, os.path.join(HERE, "music.py"), str(total), bgm, tl_path])

    vo_items = [(s["__vo"], s["start"] + LEAD, 1.0) for s in segs if s.get("__vo")]
    vo = mix_bed(vo_items, total)
    vo_bed = os.path.join(audio_dir, "vo_bed.wav")
    write_wav(vo_bed, vo)
    del vo

    # 全局对齐校验：结构层 + 音轨实测层
    bad, detail, rows = check_alignment(segs, LEAD, vo_bed)
    n_sub = sum(r["n"] for r in rows)
    print(f"   对齐校验：{len(rows)} 段语音 / {n_sub} 条字幕")
    if detail:
        worst = max(detail, key=lambda d: abs(d[1]))
        print(f"     音轨实测最大起点偏差 {abs(worst[1]):.2f}s（第 {worst[0]:02d} 段）")
    if bad:
        print(f"     ! {len(bad)} 处不对齐")
        for b in bad[:12]:
            print("       " + b)
        if len(bad) > 12:
            print(f"       … 另有 {len(bad) - 12} 处")
    else:
        print("     ✓ 字幕 / 画面 / 语音全部对齐")

    if a.check_align:
        step("对齐校验")
        summary()
        raise SystemExit(1 if bad else 0)

    cues = [(os.path.join(sfx_dir, name), at, g) for name, at, g in sfx_cues(segs)]
    cues += [(os.path.join(vox_dir, name), at, g) for name, at, g in vox_cues(segs)]
    sfmix = mix_bed(cues, total)
    write_wav(os.path.join(audio_dir, "sfx_bed.wav"), sfmix)
    del sfmix

    track = os.path.join(audio_dir, "track.wav")
    run(["ffmpeg", "-y", "-v", "error", "-i", bgm,
         "-i", os.path.join(audio_dir, "vo_bed.wav"),
         "-i", os.path.join(audio_dir, "sfx_bed.wav"),
         "-filter_complex",
         "[0:a]volume=0.16[b];[1:a]volume=1.15[v];[2:a]volume=0.55[s];"
         "[b][v][s]amix=inputs=3:duration=first:normalize=0,"
         "loudnorm=I=-16:TP=-1.5:LRA=11[a]",
         "-map", "[a]", "-ac", "2", "-ar", "44100", track])
    print("   audio/track.wav")
    step("混音")

    # 5) 编码
    if a.audio_only:
        print("⑤ 跳过编码（--audio-only）")
        summary()
        return
    # 帧目录里可能是上一种格式（上次 --png / 这次默认 jpg），自动跟随，别让用户白重渲
    if not os.path.exists(os.path.join(frames_dir, f"f00001.{ext}")):
        for cand in ("jpg", "png"):
            if os.path.exists(os.path.join(frames_dir, f"f00001.{cand}")):
                ext = cand
                break
    first = os.path.join(frames_dir, f"f00001.{ext}")
    if not os.path.exists(first):
        raise SystemExit(f"{frames_dir} 里没有帧，先去掉 --no-render 跑一遍")
    # 帧数可能来自不同档位（草稿 15fps / 正片 30fps），按实际帧数反推帧率，
    # 否则 15fps 的帧被当 30fps 编码，成片只有一半长
    n_frames = len(glob.glob(os.path.join(frames_dir, f"f*.{ext}")))
    n_expect = round(total * fps)
    fps_eff = n_frames / total if total > 0 else fps
    if n_frames > n_expect * 1.02:
        # 帧数比预期多：目录里混进了别的版本的旧帧。这时候绝不能按「多出来的帧率」编码，
        # 否则整片会被加速（实测 31.2fps 会让 4 分钟片快 4%），而且音画逐渐错位。
        print(f"   帧数 {n_frames} 多于预期 {n_expect}（有旧帧残留），仍按 {fps:.0f}fps 编码并裁掉多余帧")
    elif abs(fps_eff - fps) / fps > 0.02:
        # 帧数明显偏少，多半是 15fps 草稿帧，按实际反推
        print(f"   帧数 {n_frames} ≠ {fps}fps × {total:.1f}s，按 {fps_eff:.2f}fps 编码")
        fps = fps_eff
    print("⑤ 编码")
    mp4 = os.path.join(out_dir, f"{title}.mp4")
    # 色彩分级放在这里而不是 SVG 里：CSS filter 会让浏览器每帧重新合成整层，
    # 实测渲染慢近一倍；ffmpeg 的 eq 是流水线里顺带做的，几乎不花时间。
    # 分级要轻：儿童内容本来就该明快，压太狠会让阴天/夜景糊成一片灰
    vf = ["scale=1920:1080:flags=lanczos", "eq=saturation=0.97:contrast=1.05"]
    if a.grain:
        vf.append("noise=alls=6:allf=p")
    # veryfast：合成卡通没有噪点纹理，preset 对压缩率几乎没影响（实测 SSIM 0.9955 vs medium），
    # 但编码快一倍
    run(["ffmpeg", "-y", "-v", "error", "-framerate", str(fps),
         "-i", os.path.join(frames_dir, f"f%05d.{ext}"), "-i", track,
         "-vf", ",".join(vf), "-frames:v", str(n_frames),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-shortest", mp4])
    size = os.path.getsize(mp4) / 1024 / 1024
    step("编码")

    # 归档：桌面频道目录／每集一个子文件夹，成片和封面都放进去
    if not a.no_archive:
        import shutil
        # 目录按「话题-语言」分：蜘蛛不是昆虫-ZH / 蜘蛛不是昆虫-SP，中英分开不混放
        meta = sc.get("meta") or {}
        topic = (meta.get("topic") or "").strip() or re.sub(r"^.*?-\d+[-_ ]*", "", title) or title
        suffix = "ZH" if LANG == "zh" else "SP"
        # 两级：<话题>/ZH 与 <话题>/SP，同一话题的中英版本挂在同一个话题目录下
        dest = os.path.join(os.path.expanduser("~"), "Desktop", "kaokao&xiaoxi", topic, suffix)
        try:
            os.makedirs(dest, exist_ok=True)
            shutil.copy2(mp4, dest)
            # 只带本语言那一套封面：out/ 里同时存在 cover_16x9 和 cover_es_16x9 时，
            # 不筛的话两个语言的文件会全部塞进同一个目录
            tag = "es" if LANG != "zh" else "zh"
            allc = sorted(glob.glob(os.path.join(out_dir, "cover*.png")) +
                          glob.glob(os.path.join(out_dir, "*封面*.png")))
            lang_c = [c for c in allc if f"_{tag}_" in os.path.basename(c) or f"-{tag}-" in os.path.basename(c)]
            covers = lang_c or allc
            for cf in covers:
                shutil.copy2(cf, dest)
            print(f"归档 → {dest}" + (f"（含 {len(covers)} 张封面）" if covers else ""))
        except Exception as e:  # noqa: BLE001
            print(f"   ! 归档失败：{e}")

    print(f"\n完成：{mp4}")
    print(f"  时长 {m}:{s_:02d} · {fps:.0f}fps · {size:.1f} MB")
    summary()


if __name__ == "__main__":
    main()

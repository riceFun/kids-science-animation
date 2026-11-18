"""背景乐合成器 —— 段落化织体 + 合唱感铺底 + 母线处理

设计要点（都是踩过坑换来的）：
  1. 段落化织体：按分镜自动分段，配乐跟着画面起伏，不是一条循环到底
  2. 和声进行 C - G - Am - F，每小节换一次和弦
  3. 铺底用微失谐叠层（freq*1.002 / 1.004）做出合唱厚度，掩盖"数字合成的干"
  4. 空气层：极轻的滤波噪声 + 16 秒呼吸
  5. 母线：tanh 软限幅 + 12ms 立体声展宽 + 峰值 -1dB，代替裸归一化

用法：
  python music.py <总时长秒> <out.wav> <timeline.json>
"""
import json
import sys
import wave

import numpy as np

SR = 44100
total = float(sys.argv[1])
out = sys.argv[2]
tl_path = sys.argv[3] if len(sys.argv) > 3 else None

N = int(total * SR)
buf = np.zeros(N, dtype=np.float64)
rng = np.random.default_rng(20261116)


def glock(freq, dur, amp=0.09):
    """钟琴：基频 + 二倍/四倍泛音，快起慢落"""
    n = min(int(dur * SR), N)
    t = np.arange(n) / SR
    env = np.exp(-4.6 * t) * (1 - np.exp(-140 * t))
    w = (np.sin(2 * np.pi * freq * t)
         + 0.32 * np.sin(2 * np.pi * freq * 2 * t)
         + 0.12 * np.sin(2 * np.pi * freq * 4 * t))
    return amp * env * w


def pad_chorus(freq, dur, amp=0.02):
    """铺底：三路微失谐叠加 = 合唱厚度"""
    n = min(int(dur * SR), N)
    t = np.arange(n) / SR
    w = (np.sin(2 * np.pi * freq * t)
         + 0.55 * np.sin(2 * np.pi * freq * 1.002 * t + 0.7)
         + 0.40 * np.sin(2 * np.pi * freq * 0.998 * t + 1.9)
         + 0.22 * np.sin(2 * np.pi * freq * 2 * t))
    fade = min(int(1.0 * SR), n // 2)
    e = np.ones(n)
    if fade > 1:
        e[:fade] = np.linspace(0, 1, fade) ** 0.7
        e[-fade:] = np.linspace(1, 0, fade) ** 0.7
    return amp * w * e / 2.4


def bass_pluck(freq, dur, amp=0.10):
    n = min(int(dur * SR), N)
    t = np.arange(n) / SR
    env = np.exp(-3.2 * t) * (1 - np.exp(-90 * t))
    w = np.sin(2 * np.pi * freq * t) + 0.18 * np.sin(2 * np.pi * freq * 2 * t)
    return amp * env * w


def shaker(dur=0.055, amp=0.012):
    n = int(dur * SR)
    x = rng.uniform(-1, 1, n)
    x = np.diff(np.concatenate([[0.0], x]))
    return amp * x * np.exp(-np.arange(n) / (n * 0.30))


# C - G - Am - F：明亮但有起伏，适合"提问—发现—解答—收束"
CHORDS = [
    {"root": 130.81, "pad": [261.63, 329.63, 392.00], "glock": [523.25, 659.25, 783.99, 1046.50]},
    {"root": 98.00,  "pad": [246.94, 293.66, 392.00], "glock": [493.88, 587.33, 783.99, 987.77]},
    {"root": 110.00, "pad": [261.63, 329.63, 440.00], "glock": [523.25, 659.25, 880.00, 1046.50]},
    {"root": 87.31,  "pad": [261.63, 349.23, 440.00], "glock": [523.25, 698.46, 880.00, 1046.50]},
]

BAR = 2.4  # 100 BPM 4/4

# 场景类型 → 织体
TEXTURE = {
    "title": "spark",
    "talk":  "piano",
    "show":  "full",
    "card":  "piano",
    "quiz":  "soft",
    "song":  "full",
    "outro": "outro",
}

sections = []
if tl_path:
    try:
        with open(tl_path, encoding="utf-8") as f:
            tl = json.load(f)
        sections = [(s["start"], s["start"] + s["dur"], s.get("tex") or TEXTURE.get(s["type"], "piano"))
                    for s in tl["segments"]]
    except Exception as e:  # noqa: BLE001
        print("  ! 读时间线失败，退回全片 piano：", e)


def texture_at(t):
    for a, b, tex in sections:
        if a <= t < b:
            return tex
    return "outro" if sections else "piano"


def put(i0, sig):
    n = min(len(sig), N - i0)
    if n > 0:
        buf[i0:i0 + n] += sig[:n]


# 1) 铺底
tpos, ci = 0.0, 0
while tpos < total - 0.3:
    ch = CHORDS[ci % 4]
    dur = min(BAR + 0.5, total - tpos)
    i0 = int(tpos * SR)
    for k, f in enumerate(ch["pad"]):
        put(i0, pad_chorus(f, dur, amp=0.026 if k == 0 else 0.017))
    tpos += BAR
    ci += 1

# 2) 钟琴旋律
PATTERN = [0, 2, 1, 3, 2, 1, 3, 2]
DENSITY = {"spark": 0.34, "soft": 0.62, "piano": 0.44, "full": 0.30, "outro": 0.78}
AMP = {"spark": 0.115, "soft": 0.060, "piano": 0.082, "full": 0.070, "outro": 0.052}
tpos, k = 0.55, 0
while tpos < total - 0.9:
    tex = texture_at(tpos)
    ch = CHORDS[int(tpos // BAR) % 4]
    note = ch["glock"][PATTERN[k % len(PATTERN)] % len(ch["glock"])]
    amp = AMP.get(tex, 0.08)
    if abs(tpos % BAR) < 0.05:
        amp *= 1.25
    put(int(tpos * SR), glock(note, 1.5, amp=amp))
    if tex in ("spark", "full") and k % 4 == 2:
        put(int(tpos * SR), glock(note * 2, 1.1, amp=amp * 0.45))
    tpos += DENSITY.get(tex, 0.44)
    k += 1

# 3) 低音
tpos = 0.0
while tpos < total - 0.4:
    tex = texture_at(tpos)
    ch = CHORDS[int(tpos // BAR) % 4]
    if tex == "full":
        put(int(tpos * SR), bass_pluck(ch["root"], 1.4, amp=0.115))
        put(int((tpos + BAR / 2) * SR), bass_pluck(ch["root"], 1.2, amp=0.085))
    elif tex in ("piano", "spark"):
        put(int(tpos * SR), bass_pluck(ch["root"], 1.2, amp=0.070))
    tpos += BAR

# 4) 打点：只在 full 段，反拍，极轻
tpos = 0.0
while tpos < total - 0.3:
    if texture_at(tpos) == "full":
        beat = BAR / 4
        for bi in (1, 3):
            put(int((tpos + bi * beat) * SR), shaker(amp=0.016))
    tpos += BAR

# 5) 空气层
air = np.convolve(rng.uniform(-1, 1, N), np.ones(7) / 7, "same") if N > 7 else np.zeros(N)
breath = 0.82 + 0.18 * np.sin(np.arange(N) / SR * 2 * np.pi / 16.0)
buf += air * breath * 0.010

# 6) 首尾淡入淡出
fi, fo = int(1.2 * SR), int(3.0 * SR)
buf[:fi] *= np.linspace(0, 1, fi) ** 0.8
buf[-fo:] *= np.linspace(1, 0, fo) ** 1.2

# 7) 母线
buf = np.tanh(buf * 1.15) / np.tanh(1.15)
buf = buf / (np.abs(buf).max() + 1e-9) * 0.891
delay = int(0.012 * SR)
L = buf
R = np.concatenate([np.zeros(delay), buf[:-delay]]) * 0.94 + buf * 0.06

stereo = np.stack([L, R], axis=1)
pcm = (np.clip(stereo, -1, 1) * 32767).astype("<i2")
with wave.open(out, "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(pcm.tobytes())

print(f"BGM 完成 {total:.1f}s -> {out}")
for a, b, tex in sections:
    print(f"   {a:6.2f}-{b:6.2f}  {tex}")

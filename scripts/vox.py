"""小熹的特色音合成器 —— 共振峰合成，不用任何采样

为什么不用「皮卡皮卡」那条路：
  那是把角色名字当叫声（宝可梦的做法），本质是「拟人化台词」。
  小熹是狐狸，要的是「动物发声 + 像在说话」之间的那个位置。

设计依据是赤狐真实叫声的三类素材：
  yip / yap  短促上滑的一声   → 应答、发现
  gekkering  快速连发的咯咯声 → 亲昵、开心
  huff       鼻音             → 思考、否定

把这三类做成 5 个可组合的「音节」，用锯齿波激励 + 三个并联共振峰滤波合成。
听起来是动物的嗓子，但音高走向是语言化的 —— 观众听得出情绪，又不会觉得它在说人话。

用法：
  python vox.py <输出目录>     # 渲染 5 个音节 + 1 个「知识音」
"""
import os
import sys
import wave

import numpy as np

SR = 44100


def _biquad(x, f0, q=1.0, kind="bp"):
    """RBJ 双二阶（和 sfx.py 同一套）"""
    w0 = 2 * np.pi * f0 / SR
    alpha = np.sin(w0) / (2 * q)
    cw = np.cos(w0)
    if kind == "bp":
        b0, b1, b2 = alpha, 0, -alpha
    elif kind == "lp":
        b0, b1, b2 = (1 - cw) / 2, 1 - cw, (1 - cw) / 2
    else:
        b0, b1, b2 = (1 + cw) / 2, -(1 + cw), (1 + cw) / 2
    a0, a1, a2 = 1 + alpha, -2 * cw, 1 - alpha
    b0, b1, b2, a1, a2 = b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0
    y = np.zeros_like(x)
    x1 = x2 = y1 = y2 = 0.0
    for i in range(len(x)):
        xi = x[i]
        yi = b0 * xi + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1 = x1, xi
        y2, y1 = y1, yi
        y[i] = yi
    return y


def _excite(f0_curve, n, vib=0.0):
    """锯齿波激励：f0 按曲线走，带一点点颤动（动物嗓子不会完全稳）"""
    t = np.arange(n) / SR
    f = np.interp(np.linspace(0, 1, n), np.linspace(0, 1, len(f0_curve)), f0_curve)
    if vib:
        f = f * (1 + vib * np.sin(2 * np.pi * 22 * t))
    ph = 2 * np.pi * np.cumsum(f) / SR
    saw = 2 * ((ph / (2 * np.pi)) % 1) - 1
    # 一点气声，纯锯齿太"电子"
    noise = np.random.default_rng(7).normal(0, 0.06, n)
    return saw * 0.9 + noise


def _formant(sig, formants, weights):
    """三个并联带通 = 三个共振峰，这就是"元音"的来源"""
    out = np.zeros_like(sig)
    for (f, q), w in zip(formants, weights):
        out += w * _biquad(sig, f, q)
    return out


def _env(n, attack=0.008, decay=6.0, shape=1.0):
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-6), 0, 1) ** 0.6
    return a * np.exp(-decay * t) ** shape


def _norm(x, peak=0.85):
    m = np.max(np.abs(x)) or 1.0
    return x / m * peak


# ---------------- 五个音节 ----------------
def chirp(dur=0.11, up=1.0):
    """啾：短促上滑，应答/发现。F1/F2 取「i」的位置，听起来清亮"""
    n = int(dur * SR)
    f0 = [420, 660 * up, 700 * up]
    sig = _excite(f0, n, vib=0.01)
    out = _formant(sig, [(340, 7), (2350, 9), (3050, 11)], [1.0, 0.55, 0.28])
    return _norm(out * _env(n, 0.006, 26))


def trill(dur=0.34, rep=3):
    """噜：三连发 + 18Hz 颤音，开心/同意。相当于狐狸的 gekkering"""
    n = int(dur * SR)
    out = np.zeros(n)
    step = int(dur / rep * SR)
    for i in range(rep):
        seg = chirp(dur * 0.46, up=1 + i * 0.06)
        s = i * step
        m = min(len(seg), n - s)
        out[s:s + m] += seg[:m]
    t = np.arange(n) / SR
    am = 0.72 + 0.28 * np.sin(2 * np.pi * 18 * t)       # 颤音
    return _norm(out * am * _env(n, 0.004, 5.5))


def coo(dur=0.24):
    """哩：下滑再上挑，疑问 / 歪头。曲线是折线，听起来像在问「嗯？」"""
    n = int(dur * SR)
    f0 = [520, 430, 400, 560, 620]
    sig = _excite(f0, n, vib=0.012)
    out = _formant(sig, [(400, 8), (1900, 10), (2650, 12)], [1.0, 0.6, 0.3])
    return _norm(out * _env(n, 0.012, 9, 0.8))


def yip(dur=0.15):
    """呀：双跳，惊讶。两个脉冲中间留 28ms 静音"""
    n = int(dur * SR)
    a = chirp(0.055, up=1.25)
    b = chirp(0.05, up=1.45)
    out = np.zeros(n)
    out[:len(a)] += a[:n]
    s = int(0.06 * SR)
    m = min(len(b), n - s)
    out[s:s + m] += b[:m] * 0.85
    return _norm(out)


def huff(dur=0.16):
    """嗯：鼻音，思考/否定。低通噪声 + 180Hz 基频"""
    n = int(dur * SR)
    f0 = [180, 172, 165]
    sig = _excite(f0, n, vib=0.004)
    body = _biquad(sig, 260, 2.0, "lp")
    breath = _biquad(np.random.default_rng(3).normal(0, 0.5, n), 900, 1.2, "lp")
    return _norm((body * 0.8 + breath * 0.35) * _env(n, 0.02, 11, 0.9))


def insight(dur=0.55):
    """知识音：小熹尾巴亮起来时的那一下。不是动物叫，是"灵光"
    上行四音（G-B-D-G）+ 高频闪光尾，和通用 sparkle 拉开音高"""
    n = int(dur * SR)
    out = np.zeros(n)
    for i, f in enumerate([784, 988, 1175, 1568]):
        s = int(i * 0.055 * SR)
        ln = min(int(0.42 * SR), n - s)
        t = np.arange(ln) / SR
        e = np.exp(-7 * t) * (1 - np.exp(-180 * t))
        out[s:s + ln] += (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * f * 2 * t)) * e * 0.22
    return _norm(out, 0.7)


VOX = {
    "chirp": chirp, "trill": trill, "coo": coo, "yip": yip, "huff": huff,
    "insight": insight,
}


def write(path, sig):
    pcm = (np.clip(sig, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(out, exist_ok=True)
    for name, fn in VOX.items():
        s = fn()
        write(os.path.join(out, f"vox_{name}.wav"), s)
        print(f"{name:8s} {len(s) / SR:4.2f}s  峰值 {np.max(np.abs(s)):.2f}")

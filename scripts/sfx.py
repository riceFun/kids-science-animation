"""纯代码合成卡通音效：转场、弹出、闪光、弹簧、上升、落地
   全部用 numpy 生成波形，不依赖任何采样素材或模型。

   用法：
     python sfx.py <输出目录>          # 一次性渲染 6 个 wav
   在 build.py 里也可以 import EFFECTS 直接取波形。"""
import sys, wave, os
import numpy as np

SR = 44100


def _env(n, attack=0.005, decay=6.0):
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-6), 0, 1)
    return a * np.exp(-decay * t)


def _biquad(x, f0, q=1.0, kind="bp"):
    """简易双二阶滤波器（RBJ 公式），用来给噪声塑形"""
    w0 = 2 * np.pi * f0 / SR
    alpha = np.sin(w0) / (2 * q)
    cw = np.cos(w0)
    if kind == "bp":
        b0, b1, b2 = alpha, 0, -alpha
    elif kind == "lp":
        b0, b1, b2 = (1 - cw) / 2, 1 - cw, (1 - cw) / 2
    else:  # hp
        b0, b1, b2 = (1 + cw) / 2, -(1 + cw), (1 + cw) / 2
    a0, a1, a2 = 1 + alpha, -2 * cw, 1 - alpha
    b0, b1, b2, a1, a2 = b0/a0, b1/a0, b2/a0, a1/a0, a2/a0
    y = np.zeros_like(x)
    x1 = x2 = y1 = y2 = 0.0
    for i in range(len(x)):
        xi = x[i]
        yi = b0*xi + b1*x1 + b2*x2 - a1*y1 - a2*y2
        x2, x1 = x1, xi
        y2, y1 = y1, yi
        y[i] = yi
    return y


def whoosh(dur=0.85, up=True):
    """转场风声：带通噪声 + 频率扫描 + 快速包络"""
    n = int(dur * SR)
    t = np.arange(n) / SR
    noise = np.random.default_rng(7).normal(0, 1, n)
    off = np.zeros(n)
    # 分段渲染不同中心频率，模拟扫频
    seg = 12
    for i in range(seg):
        f = (500 + 2200 * i / seg) if up else (2700 - 2200 * i / seg)
        s, e = int(n * i / seg), int(n * (i + 1) / seg)
        off[s:e] = _biquad(noise[s:e] + np.random.default_rng(i).normal(0, .1, e - s), f, q=2.2)
    env = np.concatenate([np.linspace(0, 1, int(n*0.35)), np.linspace(1, 0, n - int(n*0.35))]) ** 2
    return 0.55 * off * env


def pop(dur=0.16):
    """弹出：短促下滑正弦 + 起始咔哒"""
    n = int(dur * SR); t = np.arange(n) / SR
    f = 1100 * np.exp(-9 * t) + 260
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-22 * t)
    click = np.random.default_rng(3).normal(0, .5, 40) * np.exp(-np.arange(40) / 6)
    out = body.copy(); out[:40] += click
    return 0.6 * out


def sparkle(dur=0.9, base=880):
    """闪光：五六颗钟琴音错落叠加，五声音阶"""
    n = int(dur * SR); out = np.zeros(n)
    rng = np.random.default_rng(11)
    for i in range(6):
        st = int(rng.uniform(0, dur * 0.55) * SR)
        f = base * [1, 1.125, 1.25, 1.5, 1.6875][i % 5]
        ln = min(int(0.5 * SR), n - st)
        t = np.arange(ln) / SR
        out[st:st+ln] += np.sin(2*np.pi*f*t) * np.exp(-7*t) * 0.22
    return out


def boing(dur=0.55):
    """弹簧：低频正弦 + 快速颤动，卡通感最强的一个"""
    n = int(dur * SR); t = np.arange(n) / SR
    f = 220 + 90 * np.sin(2 * np.pi * 14 * t) * np.exp(-4 * t)
    out = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-5.5 * t)
    return 0.55 * out


def riser(dur=1.3):
    """上升音：锯齿扫频 + 噪声，用于揭晓/转场前铺垫"""
    n = int(dur * SR); t = np.arange(n) / SR
    f = 180 * np.exp(np.log(6) * t / dur)
    ph = 2 * np.pi * np.cumsum(f) / SR
    saw = 2 * ((ph / (2 * np.pi)) % 1) - 1
    noise = _biquad(np.random.default_rng(5).normal(0, 1, n), 3000, q=1.2)
    out = (0.22 * saw + 0.10 * noise) * (t / dur) ** 1.6
    return out


def thud(dur=0.35):
    """落地/撞击：低频正弦 + 短噪声"""
    n = int(dur * SR); t = np.arange(n) / SR
    f = 120 * np.exp(-6 * t) + 48
    out = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-11 * t)
    out += 0.15 * np.random.default_rng(9).normal(0, 1, n) * np.exp(-40 * t)
    return 0.7 * out


EFFECTS = {
    "whoosh": whoosh, "pop": pop, "sparkle": sparkle,
    "boing": boing, "riser": riser, "thud": thud,
}


def write(path, sig):
    pcm = (np.clip(sig, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(pcm.tobytes())


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(out, exist_ok=True)
    for name, fn in EFFECTS.items():
        s = fn()
        write(os.path.join(out, f"sfx_{name}.wav"), s)
        print(f"{name:8s} {len(s)/SR:4.2f}s  峰值 {np.max(np.abs(s)):.2f}")

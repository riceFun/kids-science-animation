#!/usr/bin/env python3
"""音色试听：把同一句台词用几套配方各念一遍，方便挑音色。

    python voice_demo.py [输出目录]

产物：<dir>/demo_<名字>.wav + 一张时长表。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import tts  # noqa: E402

LINE = "走，我们去看看～尾巴告诉我答案了哦"

# 变调幅度（shift）决定「卡通感」，超过 1.20 会明显发尖、齿音变重。
# 1.10–1.16 是卡通和自然的平衡点：听得出是只小动物，又不至于像被掐住。
CASES = [
    ("1_考考_当前_1.05", "zh-CN-YunxiaNeural", "-6%", "+2Hz", 1.05),
    ("2_小熹_当前_1.26", "zh-CN-XiaoyiNeural", "+8%", "+30Hz", 1.26),
    ("3_小熹_柔和_1.14", "zh-CN-XiaoyiNeural", "+6%", "+14Hz", 1.14),
    ("4_小熹_原声_1.00", "zh-CN-XiaoyiNeural", "+4%", "+0Hz", 1.00),
    ("5_小熹_晓晓_1.14", "zh-CN-XiaoxiaoNeural", "+6%", "+10Hz", 1.14),
    ("6_小熹_云夏_1.12", "zh-CN-YunxiaNeural", "+2%", "+6Hz", 1.12),
    ("7_旁白_云希", "zh-CN-YunxiNeural", "-5%", "+0Hz", 1.00),
]

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "voice_demo"
    os.makedirs(out, exist_ok=True)
    print("同一句：" + LINE + "\n")
    for name, voice, rate, pitch, shift in CASES:
        tts.VOICES["__tmp__"] = {"voice": voice, "rate": rate, "pitch": pitch, "shift": shift}
        try:
            path, dur = tts.synthesize(LINE, "__tmp__", None, out, force=True)
            dst = os.path.join(out, f"demo_{name}.wav")
            os.replace(path, dst)
            print(f"  {name:26s} {dur:5.2f}s  -> {dst}")
        except Exception as e:  # noqa: BLE001
            print(f"  {name:26s} 失败：{e}")

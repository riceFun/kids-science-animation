"""导出封面静帧：16:9（1920×1080）或 4:3（1440×1080，B 站用）。

用法：
  python3 cover.py ep08/script.json --ratio 4:3 --out ep08/out/封面_4x3.png
  python3 cover.py ep08/script.json --ratio 16:9 --out ep08/out/封面_16x9.png

封面取自台本里的 title 段（cover / titleLines / 角色站位都复用那里的字段），
只渲染一帧，不跑配音和编码。
"""
import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build import ENGINE, find_puppeteer  # noqa: E402

RATIO = {
    "16:9": (1920, 1080, "title", 3.0),
    "4:3": (1440, 1080, "cover43", 3.0),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("--ratio", default="4:3", choices=list(RATIO))
    ap.add_argument("--out", default=None)
    ap.add_argument("--t", type=float, default=None, help="取第几秒的画面，默认 3.0")
    a = ap.parse_args()

    w, h, scene, t0 = RATIO[a.ratio]
    t = a.t if a.t is not None else t0
    root = os.path.dirname(os.path.abspath(a.script))
    with open(a.script, encoding="utf-8") as f:
        sc = json.load(f)

    title = next((s for s in sc["segments"] if s.get("type") == "title"), None)
    if not title:
        raise SystemExit("台本里没有 title 段，不能出封面")
    if not title.get("cover") and not title.get("coverPhoto"):
        print("  ! title 没写 cover / coverPhoto，封面会没有主体", file=sys.stderr)

    seg = dict(title)
    # 4:3 画面窄，站位/缩放往往要另一套；台本里可用 "c43": {...} 覆盖
    if a.ratio == "4:3":
        seg.update(title.get("c43") or {})
    seg["type"] = scene
    seg["dur"] = max(2.0, t + 1.5)

    # 实拍封面：coverPhoto 的图要读成 base64 内联，file:// 下直接引路径会被 Chrome 拦
    cp = title.get("coverPhoto")
    if cp:
        arr = cp if isinstance(cp, list) else [cp]
        data = []
        for pth in arr[:2]:
            fp = pth if os.path.isabs(pth) else os.path.join(root, pth)
            if not os.path.exists(fp):
                raise SystemExit(f"封面图不存在：{fp}")
            mime = "image/png" if fp.lower().endswith(".png") else "image/jpeg"
            with open(fp, "rb") as f:
                data.append(f"data:{mime};base64," + base64.b64encode(f.read()).decode())
        seg["coverPhotoData"] = data
        seg.pop("cover", None)
    # cover43 背景自带木纹，不需要本集 BG；title 仍要本集背景
    if scene == "cover43":
        seg.pop("bg", None)

    tmp = tempfile.mkdtemp(prefix="cover_")
    tl = os.path.join(tmp, "tl.json")
    with open(tl, "w", encoding="utf-8") as f:
        json.dump({"segments": [seg]}, f, ensure_ascii=False)

    scenery = os.path.join(root, "scenery.js")
    cmd = ["node", os.path.join(HERE, "render.js"), ENGINE, tl, os.path.join(tmp, "frames"),
           "--preview", str(t), "--scale", "1", "--w", str(w), "--h", str(h)]
    if os.path.exists(scenery):
        cmd += ["--scenery", scenery]

    env = dict(os.environ, NODE_PATH=find_puppeteer())
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode != 0:
        print(r.stdout[-800:], r.stderr[-800:], sep="\n")
        raise SystemExit(f"渲染失败（{a.ratio}）")

    src = os.path.join(tmp, "frames", f"preview_{t:.2f}.png")
    out = a.out or os.path.join(root, "out", f"封面_{a.ratio.replace(':', 'x')}.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    shutil.copyfile(src, out)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"封面 {a.ratio} → {out}  ({w}×{h})")


if __name__ == "__main__":
    main()

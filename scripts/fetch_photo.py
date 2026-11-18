"""实拍素材抓取：多源降级，一个源挂了自动换下一个。

用法：
  python3 fetch_photo.py "mosquito macro" --out ep07/photos --name mosquito
  python3 fetch_photo.py "蚁后" --out ep07/photos --list      # 只列候选，不下载

源顺序（前两个不需要 key，后面两个需要环境变量）：
  1. 本地已有      photos/<name>*.jpg 直接用，不联网
  2. Wikimedia Commons  公开 API，取 CC 授权图，记作者与许可
  3. Openverse          公开 API，聚合各 CC 源，可筛商用
  4. Pexels             PEXELS_API_KEY
  5. Pixabay            PIXABAY_API_KEY
  6. 全挂 → 报错并给替代方案（用 scenery.js 画，或手动放图）

下载后写 photos/credits.json：{文件名: {author, license, source, page}}。
build.py 读台本里的 "credit" 字段生成署名卡；抓图时会把建议署名一起打印出来。
"""
import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request

UA = "kids-science-animation/1.0 (educational; contact: local)"
TIMEOUT = 15


def _get(url, headers=None, raw=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        data = r.read()
    return data if raw else json.loads(data.decode("utf-8", "replace"))


# ---------------------------------------------------------------- 各来源
def src_local(out_dir, name):
    """本地已有文件优先——断网也能出片。"""
    if not os.path.isdir(out_dir):
        return []
    hit = []
    for f in sorted(os.listdir(out_dir)):
        if f.lower().startswith(name.lower()) and f.lower().endswith((".jpg", ".jpeg", ".png")):
            hit.append({"path": os.path.join(out_dir, f), "title": f,
                        "author": "本地文件", "license": "self", "source": "local"})
    return hit


def src_wikimedia(q, limit=8):
    api = ("https://commons.wikimedia.org/w/api.php?action=query&format=json"
           "&generator=search&gsrnamespace=6&gsrlimit=%d&gsrsearch=%s"
           "&prop=imageinfo&iiprop=url|extmetadata&iiurlwidth=1800") % (limit, urllib.parse.quote(q))
    data = _get(api)
    pages = (data.get("query") or {}).get("pages") or {}
    out = []
    for p in pages.values():
        ii = (p.get("imageinfo") or [{}])[0]
        md = ii.get("extmetadata") or {}
        url = ii.get("thumburl") or ii.get("url")
        if not url:
            continue
        lic = (md.get("LicenseShortName") or {}).get("value") or "?"
        # 只要允许商用的：CC0 / CC BY / CC BY-SA / Public domain
        if not re.search(r"CC0|Public domain|CC[ -]BY", lic, re.I):
            continue
        author = re.sub(r"<[^>]+>", "", (md.get("Artist") or {}).get("value") or "未署名")
        out.append({
            "url": url,
            "title": p.get("title", "").replace("File:", ""),
            "author": author.strip()[:60],
            "license": lic.strip(),
            "source": "Wikimedia Commons",
            "page": "https://commons.wikimedia.org/wiki/" + urllib.parse.quote(p.get("title", "")),
        })
    return out


def src_openverse(q, limit=8):
    api = ("https://api.openverse.org/v1/images/?q=%s&page_size=%d&license_type=commercial"
           % (urllib.parse.quote(q), limit))
    data = _get(api)
    out = []
    for it in data.get("results") or []:
        url = it.get("url")
        if not url:
            continue
        lic = ("CC " + (it.get("license") or "").upper() + " " + (it.get("license_version") or "")).strip()
        out.append({
            "url": url,
            "title": (it.get("title") or "untitled")[:60],
            "author": (it.get("creator") or "未署名")[:60],
            "license": lic,
            "source": "Openverse",
            "page": it.get("foreign_landing_url") or it.get("detail_url") or "",
        })
    return out


def src_pexels(q, limit=8):
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        raise RuntimeError("未设 PEXELS_API_KEY")
    data = _get("https://api.pexels.com/v1/search?query=%s&per_page=%d" % (urllib.parse.quote(q), limit),
                headers={"Authorization": key})
    return [{
        "url": p["src"]["large2x"], "title": (p.get("alt") or "pexels")[:60],
        "author": p.get("photographer") or "Pexels",
        "license": "Pexels License", "source": "Pexels", "page": p.get("url", ""),
    } for p in data.get("photos") or []]


def src_pixabay(q, limit=8):
    key = os.environ.get("PIXABAY_API_KEY")
    if not key:
        raise RuntimeError("未设 PIXABAY_API_KEY")
    data = _get("https://pixabay.com/api/?key=%s&q=%s&image_type=photo&per_page=%d"
                % (key, urllib.parse.quote(q), min(20, max(3, limit))))
    return [{
        "url": h["largeImageURL"], "title": (h.get("tags") or "pixabay")[:60],
        "author": h.get("user") or "Pixabay",
        "license": "Pixabay License", "source": "Pixabay", "page": h.get("pageURL", ""),
    } for h in data.get("hits") or []]


SOURCES = [
    ("Wikimedia", src_wikimedia),
    ("Openverse", src_openverse),
    ("Pexels", src_pexels),
    ("Pixabay", src_pixabay),
]


def credit_line(c):
    """给台本用的署名短句。license=self 就不用署名。"""
    if c["license"] == "self":
        return ""
    return f"图：{c['author']} · {c['license']}（{c['source']}）"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--out", default="photos")
    ap.add_argument("--name", default=None, help="输出文件名前缀，默认用查询词")
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--list", action="store_true", dest="list_only")
    a = ap.parse_args()

    name = a.name or re.sub(r"[^\w]+", "_", a.query)[:24]
    os.makedirs(a.out, exist_ok=True)

    local = src_local(a.out, name)
    if local:
        print(f"本地已存在 {len(local)} 张，直接复用：")
        for c in local:
            print("  " + c["path"])
        return 0
    if a.list_only:
        pass

    cands, tried = [], []
    for label, fn in SOURCES:
        try:
            got = fn(a.query, 8)
            tried.append(f"{label}: {len(got)}")
            cands.extend(got)
            if len(cands) >= a.count:
                break
        except Exception as e:  # noqa: BLE001
            tried.append(f"{label}: 失败({type(e).__name__})")
            print(f"  ! {label} 不可用：{e}")

    print("尝试顺序 → " + " | ".join(tried))
    if not cands:
        print("\n所有源都没拿到图。可选：")
        print("  1) 手动放一张到 %s/%s.jpg，然后只写台本" % (a.out, name))
        print("  2) 用 scenery.js 画示意图（不依赖素材）")
        print("  3) Pexels/Pixabay 需要 API key：export PEXELS_API_KEY=...")
        return 2

    if a.list_only:
        for i, c in enumerate(cands[:12], 1):
            print(f"{i:2d}. [{c['source']}] {c['title']} — {c['author']} · {c['license']}")
            print(f"    {c['url'][:110]}")
        return 0

    credits = {}
    cpath = os.path.join(a.out, "credits.json")
    if os.path.exists(cpath):
        credits = json.load(open(cpath, encoding="utf-8"))
    for i, c in enumerate(cands[:a.count]):
        ext = ".png" if c["url"].lower().endswith(".png") else ".jpg"
        fn = f"{name}{'' if i == 0 else '_' + str(i + 1)}{ext}"
        dst = os.path.join(a.out, fn)
        try:
            data = _get(c["url"], raw=True)
            with open(dst, "wb") as f:
                f.write(data)
        except Exception as e:  # noqa: BLE001
            print(f"  ! 下载失败（{c['source']}）：{e}")
            continue
        credits[fn] = {k: c[k] for k in ("author", "license", "source", "page", "title")}
        print(f"OK {dst}  ({c['source']})")
        line = credit_line(c)
        if line:
            print(f"   台本署名写法：\"credit\": \"{line}\"")
    json.dump(credits, open(cpath, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())

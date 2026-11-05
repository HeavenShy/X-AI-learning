"""生成漫画标题字体子集：站酷庆科黄油体 → GB2312 一级字库（3755 常用字）+ ASCII + 常用标点，输出 WOFF。

完整 TTF 约 8.3 MB，子集约 1.2 MB。选 WOFF 而不是 WOFF2：低版本 iOS 的 wx.loadFontFace 不兼容 WOFF2。
字体协议：SIL Open Font License 1.1（见 app/static/fonts/OFL.txt），允许子集化和再分发。

用法（在 backend 目录，需要 pip install -r requirements-dev.txt）：
    python -m scripts.build_font_subset
"""

import urllib.request
from pathlib import Path

from fontTools import subset

SOURCE_URL = "https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/zcoolqingkehuangyou/ZCOOLQingKeHuangYou-Regular.ttf"
OUT_DIR = Path(__file__).resolve().parent.parent / "app" / "static" / "fonts"
OUT_FILE = OUT_DIR / "zcool-qingke-huangyou-gb1.woff"
EXTRA_CHARS = "，。！？、：；“”‘’（）《》【】…—·～％＋－×÷"


def gb2312_level1() -> str:
    chars = []
    for hi in range(0xB0, 0xD8):
        for lo in range(0xA1, 0xFF):
            try:
                chars.append(bytes([hi, lo]).decode("gb2312"))
            except UnicodeDecodeError:
                pass
    return "".join(chars)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    src = OUT_DIR / "_full.ttf"
    print("downloading", SOURCE_URL)
    urllib.request.urlretrieve(SOURCE_URL, src)
    text = gb2312_level1() + "".join(chr(c) for c in range(0x20, 0x7F)) + EXTRA_CHARS
    opts = subset.Options()
    opts.flavor = "woff"
    opts.layout_features = ["*"]
    opts.name_IDs = ["*"]
    opts.notdef_outline = True
    font = subset.load_font(str(src), opts)
    subsetter = subset.Subsetter(opts)
    subsetter.populate(text=text)
    subsetter.subset(font)
    subset.save_font(font, str(OUT_FILE), opts)
    src.unlink()
    print(f"wrote {OUT_FILE} ({OUT_FILE.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()

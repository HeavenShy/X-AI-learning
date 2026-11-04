"""用户输入清洗：去掉不可见字符、统一全半角、压缩多余空白。"""

import re
import unicodedata

# 零宽字符与 BOM
_ZERO_WIDTH = re.compile("[​‌‍⁠﻿]")
# 控制字符（保留换行和制表符，后面统一处理）
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_INLINE_SPACES = re.compile(r"[ \t 　]+")
_MANY_BLANK_LINES = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _ZERO_WIDTH.sub("", text)
    text = _CONTROL.sub("", text)
    text = _INLINE_SPACES.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _MANY_BLANK_LINES.sub("\n\n", text)
    return text.strip()


def visible_length(text: str) -> int:
    """不计空白的字符数，用于“至少写 4 个字”的判断。"""
    return sum(1 for ch in text if not ch.isspace())

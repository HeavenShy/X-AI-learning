"""敏感词过滤（DFA / 前缀树）。

匹配前会去掉空格和符号并转小写，避免“制 毒”“制*毒”这类绕过。
词库在 app/resources/sensitive_words.txt，一行一个词，# 开头为注释。
MVP 只是第一道防线，上线前建议叠加微信官方内容安全接口（msgSecCheck）。
"""

from functools import lru_cache
from pathlib import Path

_WORDS_FILE = Path(__file__).resolve().parent.parent / "resources" / "sensitive_words.txt"
_END = "\0"


def _normalize_char(ch: str) -> str:
    """保留汉字、字母、数字，其余字符视为分隔符丢弃。"""
    return ch.lower() if ch.isalnum() else ""


def _normalize(text: str) -> str:
    return "".join(_normalize_char(ch) for ch in text)


class ContentFilter:
    def __init__(self, words: list[str]):
        self._trie: dict = {}
        self.word_count = 0
        for word in words:
            key = _normalize(word)
            if not key:
                continue
            node = self._trie
            for ch in key:
                node = node.setdefault(ch, {})
            if _END not in node:
                self.word_count += 1
            node[_END] = word.strip().lower()

    def find(self, text: str) -> str | None:
        """返回命中的第一个敏感词；没有命中返回 None。"""
        if not self._trie or not text:
            return None
        s = _normalize(text)
        for start in range(len(s)):
            node = self._trie
            for ch in s[start:]:
                node = node.get(ch)
                if node is None:
                    break
                if _END in node:
                    return node[_END]
        return None

    def is_clean(self, text: str) -> bool:
        return self.find(text) is None


def load_words(path: Path = _WORDS_FILE) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]


@lru_cache
def get_content_filter() -> ContentFilter:
    return ContentFilter(load_words())

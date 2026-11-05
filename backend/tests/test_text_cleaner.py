from app.utils.text_cleaner import clean_text, visible_length


def test_strips_surrounding_whitespace():
    assert clean_text("  什么是 RAG  \n") == "什么是 RAG"


def test_removes_zero_width_and_control_chars():
    assert clean_text("RA​G\x00 是‍什么﻿") == "RAG 是什么"


def test_collapses_inline_spaces_and_blank_lines():
    assert clean_text("复利   怎么\t\t算\n\n\n\n下一段") == "复利 怎么 算\n\n下一段"


def test_normalizes_full_width_ascii():
    # NFKC：全角字母数字转半角
    assert clean_text("ＲＡＧ １２３") == "RAG 123"


def test_keeps_chinese_punctuation():
    assert clean_text("什么是RAG？它和搜索有啥区别。") == "什么是RAG?它和搜索有啥区别。"


def test_visible_length_ignores_whitespace():
    assert visible_length("R A G") == 3
    assert visible_length("RAG 是啥") == 5
    assert visible_length("") == 0

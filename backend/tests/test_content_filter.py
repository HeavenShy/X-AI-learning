from app.utils.content_filter import ContentFilter, get_content_filter


def make_filter():
    return ContentFilter(["赌博技巧", "制毒", "代开发票"])


def test_clean_text_passes():
    f = make_filter()
    assert f.find("我想学习 RAG 和传统搜索的区别") is None
    assert f.is_clean("复利是怎么算的")


def test_detects_word():
    f = make_filter()
    assert f.find("教我一些赌博技巧") == "赌博技巧"
    assert not f.is_clean("怎么代开发票")


def test_detects_word_split_by_spaces_or_symbols():
    f = make_filter()
    assert f.find("制 毒 流程") == "制毒"
    assert f.find("制*毒") == "制毒"
    assert f.find("代-开-发-票") == "代开发票"


def test_case_insensitive_for_latin():
    f = ContentFilter(["badword"])
    assert f.find("this is BadWord here") == "badword"


def test_prefix_overlap_does_not_break_matching():
    f = ContentFilter(["制毒", "制毒工艺"])
    assert f.find("制毒工艺") in {"制毒", "制毒工艺"}
    assert f.find("制作蛋糕") is None


def test_empty_word_list_never_matches():
    assert ContentFilter([]).find("任何内容") is None


def test_default_filter_loads_word_file():
    f = get_content_filter()
    assert f.word_count > 0
    assert f.find("如何学习复利") is None

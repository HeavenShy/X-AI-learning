import re

from app.utils.id_generator import new_quiz_id


def test_quiz_id_format():
    assert re.fullmatch(r"quiz_[0-9a-f]{12}", new_quiz_id())


def test_quiz_id_unique():
    assert len({new_quiz_id() for _ in range(1000)}) == 1000

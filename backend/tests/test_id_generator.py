import re

import pytest

from app.utils.id_generator import new_document_id, new_kb_id, new_quiz_id


@pytest.mark.parametrize(
    ("factory", "prefix"), [(new_quiz_id, "quiz"), (new_kb_id, "kb"), (new_document_id, "doc")]
)
def test_id_format(factory, prefix):
    assert re.fullmatch(rf"{prefix}_[0-9a-f]{{12}}", factory())


@pytest.mark.parametrize("factory", [new_quiz_id, new_kb_id, new_document_id])
def test_id_unique(factory):
    assert len({factory() for _ in range(1000)}) == 1000

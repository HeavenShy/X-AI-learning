import uuid


def new_quiz_id() -> str:
    return f"quiz_{uuid.uuid4().hex[:12]}"


def new_kb_id() -> str:
    return f"kb_{uuid.uuid4().hex[:12]}"


def new_document_id() -> str:
    return f"doc_{uuid.uuid4().hex[:12]}"

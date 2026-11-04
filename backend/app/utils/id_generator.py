import uuid


def new_quiz_id() -> str:
    return f"quiz_{uuid.uuid4().hex[:12]}"

"""知识库接口：都要求登录；知识库不可用（没库 / 没配 Embedding Key）时返回 5000 / 503。"""

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, Request, UploadFile

from app.api.deps import KbRuntime, require_history_service, require_kb, require_kb_quiz_service, require_kb_service
from app.core.auth import require_user_id
from app.core.exceptions import BizError, ErrorCode
from app.models.common import ApiResponse, ok
from app.models.kb import KbDetail, KbDocument, KbList, KbNameRequest, KbQuizRequest, KnowledgeBase
from app.models.quiz import Quiz
from app.rag.parsing import detect_file_type, file_type_of
from app.services.history_service import HistoryService
from app.services.kb_quiz_service import KbQuizService
from app.services.kb_service import KbService
from app.utils.id_generator import new_document_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-base"])

UPLOAD_READ_BYTES = 64 * 1024
MSG_TYPE_NOT_SUPPORTED = "只支持 PDF（文字版）、Word（.docx）、TXT、Markdown 文件"
MSG_FILE_EMPTY = "文件是空的，换一个试试"


def msg_file_too_large(max_bytes: int) -> str:
    return f"文件不能超过 {max_bytes // (1024 * 1024)} MB"


@router.get("", response_model=ApiResponse[KbList])
async def list_knowledge_bases(
    user_id: int = Depends(require_user_id), service: KbService = Depends(require_kb_service)
) -> ApiResponse[KbList]:
    return ok(await service.list_all(user_id))


@router.post("", response_model=ApiResponse[KnowledgeBase])
async def create_knowledge_base(
    req: KbNameRequest, user_id: int = Depends(require_user_id), service: KbService = Depends(require_kb_service)
) -> ApiResponse[KnowledgeBase]:
    return ok(await service.create(user_id, req.name))


@router.get("/{kb_id}", response_model=ApiResponse[KbDetail])
async def get_knowledge_base(
    kb_id: str, user_id: int = Depends(require_user_id), service: KbService = Depends(require_kb_service)
) -> ApiResponse[KbDetail]:
    return ok(await service.detail(user_id, kb_id))


@router.put("/{kb_id}", response_model=ApiResponse[KnowledgeBase])
async def rename_knowledge_base(
    kb_id: str,
    req: KbNameRequest,
    user_id: int = Depends(require_user_id),
    service: KbService = Depends(require_kb_service),
) -> ApiResponse[KnowledgeBase]:
    return ok(await service.rename(user_id, kb_id, req.name))


@router.delete("/{kb_id}", response_model=ApiResponse[None])
async def delete_knowledge_base(
    kb_id: str, user_id: int = Depends(require_user_id), service: KbService = Depends(require_kb_service)
) -> ApiResponse[None]:
    await service.delete(user_id, kb_id)
    return ok(None)


@router.post("/{kb_id}/documents", response_model=ApiResponse[KbDocument])
async def upload_document(
    kb_id: str,
    request: Request,
    file: UploadFile = File(...),
    user_id: int = Depends(require_user_id),
    kb: KbRuntime = Depends(require_kb),
    service: KbService = Depends(require_kb_service),
) -> ApiResponse[KbDocument]:
    """校验后立即返回 processing 的资料，解析与向量化在后台进行。"""
    settings = request.app.state.settings
    await service.check_upload_allowed(user_id, kb_id)
    filename = file.filename or ""
    file_type = file_type_of(filename)
    if file_type is None:
        raise BizError(ErrorCode.FILE_TYPE_NOT_SUPPORTED, MSG_TYPE_NOT_SUPPORTED)

    document_id = new_document_id()
    upload_dir = Path(settings.kb_upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / f"{document_id}.{file_type}"
    try:
        # 自己计数，不信任 Content-Length；超限立刻停止写入
        size = 0
        with open(path, "wb") as out:
            while chunk := await file.read(UPLOAD_READ_BYTES):
                size += len(chunk)
                if size > settings.kb_max_file_bytes:
                    raise BizError(ErrorCode.FILE_SIZE_INVALID, msg_file_too_large(settings.kb_max_file_bytes))
                out.write(chunk)
        if size == 0:
            raise BizError(ErrorCode.FILE_SIZE_INVALID, MSG_FILE_EMPTY)
        if await asyncio.to_thread(detect_file_type, filename, path) is None:
            raise BizError(ErrorCode.FILE_TYPE_NOT_SUPPORTED, MSG_TYPE_NOT_SUPPORTED)
        doc = await service.add_document(
            user_id, kb_id, filename=filename, file_type=file_type, size_bytes=size, document_id=document_id
        )
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    kb.ingestor.start(document_id=document_id, user_id=user_id, kb_id=kb_id, path=path, file_type=file_type)
    return ok(doc)


@router.delete("/{kb_id}/documents/{document_id}", response_model=ApiResponse[None])
async def delete_document(
    kb_id: str,
    document_id: str,
    user_id: int = Depends(require_user_id),
    service: KbService = Depends(require_kb_service),
) -> ApiResponse[None]:
    await service.delete_document(user_id, kb_id, document_id)
    return ok(None)


@router.post("/{kb_id}/quiz", response_model=ApiResponse[Quiz])
async def generate_quiz(
    kb_id: str,
    req: KbQuizRequest,
    user_id: int = Depends(require_user_id),
    service: KbQuizService = Depends(require_kb_quiz_service),
    history: HistoryService = Depends(require_history_service),
) -> ApiResponse[Quiz]:
    """用知识库出题：只依据资料，不联网检索；出好的题像文本出题一样存为一话。"""
    quiz = await service.generate(user_id, kb_id, req)
    try:
        await history.save_quiz(user_id, quiz, req.difficulty)
    except Exception:  # noqa: BLE001 —— 落库失败不影响本次闯关，只是之后看不到这条历史
        logger.exception("save kb quiz %s for user %s failed", quiz.quiz_id, user_id)
    return ok(quiz)

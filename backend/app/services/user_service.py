"""用户服务：微信登录（首次自动注册）、档案查询与更新。"""

import logging
from datetime import datetime

from app.core.auth import MSG_UNAUTHORIZED, create_token
from app.core.config import Settings
from app.core.db import Database
from app.core.exceptions import BizError, ErrorCode
from app.models.user import LoginResponse, Profile, ProfileUpdate, UserBrief
from app.repositories import stats_repository as stats_repo
from app.repositories import user_repository as users
from app.services.review_service import count_mistakes
from app.services.scoring_service import percent
from app.services.wechat_auth import WeChatAuthClient, WeChatLoginError
from app.utils.content_filter import ContentFilter
from app.utils.text_cleaner import clean_text
from app.utils.timeutil import utcnow, week_start_utc

logger = logging.getLogger(__name__)

DEFAULT_NICKNAME = "学习者"
NICKNAME_MAX_CHARS = 20
MSG_LOGIN_FAILED = "微信登录失败，请稍后重试"
MSG_NICKNAME_EMPTY = "昵称不能为空"
MSG_NICKNAME_TOO_LONG = f"昵称最多 {NICKNAME_MAX_CHARS} 个字"
MSG_NICKNAME_NOT_ALLOWED = "这个昵称不太合适，换一个试试"
MSG_AVATAR_INVALID = "头像地址必须是 https 链接"


def _brief(row: dict) -> UserBrief:
    return UserBrief(
        id=row["id"],
        nickname=row["nickname"],
        avatar_url=row["avatar_url"],
        total_xp=row["total_xp"],
        total_coins=row["total_coins"],
    )


class UserService:
    def __init__(self, db: Database, *, settings: Settings, content_filter: ContentFilter):
        self._db = db
        self._settings = settings
        self._filter = content_filter

    async def login(self, code: str, wechat: WeChatAuthClient) -> LoginResponse:
        try:
            openid = await wechat.code_to_openid(code)
        except WeChatLoginError as exc:
            raise BizError(ErrorCode.LOGIN_FAILED, MSG_LOGIN_FAILED) from exc
        async with self._db.transaction() as cur:
            row = await users.upsert_by_openid(cur, openid, DEFAULT_NICKNAME)
        logger.info("user %s logged in", row["id"])
        return LoginResponse(token=create_token(row["id"], openid, self._settings), user=_brief(row))

    async def profile(self, user_id: int, *, now: datetime | None = None) -> Profile:
        async with self._db.transaction() as cur:
            row = await users.get_by_id(cur, user_id)
            if row is None:
                # token 有效但用户已不存在（如库被重置），让前端重新登录
                raise BizError(ErrorCode.UNAUTHORIZED, MSG_UNAUTHORIZED, http_status=401)
            st = await users.stats(cur, user_id, week_start_utc(now or utcnow()))
            mistake_count = await count_mistakes(cur, user_id)
            topic_count = await stats_repo.count_topics(cur, user_id)
        return Profile(
            **_brief(row).model_dump(),
            quiz_count=st["quiz_count"],
            correct_count=st["correct_count"],
            question_count=st["question_count"],
            average_accuracy=percent(st["correct_count"], st["question_count"]),
            week_minutes=(st["week_ms"] + 30_000) // 60_000,
            mistake_count=mistake_count,
            topic_count=topic_count,
        )

    def _check_nickname(self, raw: str) -> str:
        # 昵称是单行文本：换行、连续空白都压成一个空格
        nickname = " ".join(clean_text(raw).split())
        if not nickname:
            raise BizError(ErrorCode.INVALID_PARAMS, MSG_NICKNAME_EMPTY)
        if len(nickname) > NICKNAME_MAX_CHARS:
            raise BizError(ErrorCode.INVALID_PARAMS, MSG_NICKNAME_TOO_LONG)
        if self._filter.find(nickname):
            raise BizError(ErrorCode.NICKNAME_NOT_ALLOWED, MSG_NICKNAME_NOT_ALLOWED)
        return nickname

    @staticmethod
    def _check_avatar(raw: str) -> str:
        url = raw.strip()
        if url and not url.startswith("https://"):
            raise BizError(ErrorCode.INVALID_PARAMS, MSG_AVATAR_INVALID)
        return url

    async def update_profile(self, user_id: int, req: ProfileUpdate) -> Profile:
        nickname = self._check_nickname(req.nickname) if req.nickname is not None else None
        avatar_url = self._check_avatar(req.avatar_url) if req.avatar_url is not None else None
        async with self._db.transaction() as cur:
            await users.update_profile(cur, user_id, nickname=nickname, avatar_url=avatar_url)
        return await self.profile(user_id)

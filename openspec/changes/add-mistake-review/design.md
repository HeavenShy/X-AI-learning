# Design

## Context

- 服务端已有错题所需的全部原始数据：`answer_records.records_json` 存了每题服务端重新判题后的结果（`question_id`、`selected_answers`、`is_correct`），`quiz_sessions.questions_json` 存了完整题目（含答案、讲解）。同一用户同一话只有一条答题记录（`uk_answer_records_user_quiz`）。
- `question_id`（如 `q1`）只在一话内唯一，所以错题的身份是 `(user_id, quiz_id, question_id)`。
- 判题规则在后端 `scoring_service._normalize`、前端 `core/judge.ts` 各有一份，结果一致。
- 闯关页 `pages/quiz/index.tsx` 里有判题后选项的展示（`AnsweredOptions`）和动画顺序（`optionVisual`），样式在 `pages/quiz/index.scss`。
- 不用 ORM：SQL 集中在 `app/repositories`，表结构在 `schema.sql`，启动时幂等建表；测试按 `core/db.TABLES` 清表。
- 复习页是 tab 页，只能 `switchTab` 进入，`useEffect` 只在首次挂载时执行。

## Goals / Non-Goals

**Goals:**
- 历史错题零迁移就能出现在错题本里。
- “移出错题本”以服务端判题为准；前端即时判题只用于动画，不用来决定状态。
- 尽量复用闯关页的作答 UI，视觉和交互保持一致。

**Non-Goals:**
- 不做遗忘曲线排期、宝藏关、提醒、已掌握列表（见 proposal）。
- 不做错题列表分页：一个用户的错题数量在 MVP 阶段可控（见风险）。
- 不改变闯关结算、历史记录、报告的任何行为。

## Decisions

### 1. 错题从答题记录推导，新表只存“重做状态”

新增 `review_items` 表，只在用户第一次重做某道错题时写入：

```sql
CREATE TABLE IF NOT EXISTS review_items (
  id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id            BIGINT UNSIGNED NOT NULL,
  quiz_id            VARCHAR(64)     NOT NULL,
  question_id        VARCHAR(64)     NOT NULL,
  wrong_retries      INT UNSIGNED    NOT NULL DEFAULT 0 COMMENT '重做时又答错的次数',
  last_selected_json JSON            NULL     COMMENT '最近一次重做答错时的选项',
  mastered_at        DATETIME(3)     NULL     COMMENT '重做答对的时间，非空即已掌握',
  created_at / updated_at ...,
  PRIMARY KEY (id),
  UNIQUE KEY uk_review_items (user_id, quiz_id, question_id)
);
```

错题列表 = 该用户所有 `answer_records` 里 `is_correct = false` 的题，关联 `quiz_sessions` 取题目，再用 `review_items` 覆盖：`mastered_at` 非空的剔除；答错次数 = 1 + `wrong_retries`；上次错误答案优先取 `last_selected_json`，否则取闯关时的 `selected_answers`；首次答错时间 = 答题记录的完结时间。

- **为什么不在结算时把错题写进一张 `mistakes` 表**：那样要在 `save_answers` 里双写，还要给上线前的历史记录写回填脚本。推导方式没有回填、也不会和答题记录不一致。
- 代价：列表接口要在 Python 里展开 JSON（见风险）。

### 2. 后端模块划分

- `app/repositories/review_repository.py`：`list_wrong_sources(user_id)`（答题记录 JOIN 题库，按 `a.created_at DESC, a.id DESC`）、`get_review_items(user_id)`、`get_review_item(...)`、`record_wrong_retry(...)`（`INSERT ... ON DUPLICATE KEY UPDATE wrong_retries = wrong_retries + 1, last_selected_json = ...`）、`mark_mastered(...)`（`mastered_at = COALESCE(mastered_at, now)`）。
- `app/services/review_service.py`：`ReviewService(db)`，`list_mistakes(user_id)` 与 `answer(user_id, req)`。合并逻辑放在一个纯函数 `merge_mistakes(sources, items)` 里，不碰数据库就能单测。
- `app/models/review.py`：`MistakeItem`、`MistakeList`、`ReviewAnswerRequest`、`ReviewAnswerResult`（`is_correct`、`correct_answers`、`mastered`）。
- `app/api/v1/routes/review.py`：`prefix="/review"`，两个接口都用 `require_user_id` + `require_db`（无库时 503，与历史接口一致）。
- 判题：把 `scoring_service` 里的规范化与比对抽成公开函数 `is_answer_correct(question, selected)`，`score()` 和重做共用，保证两边规则不分叉。

### 3. 重做提交流程

`answer()` 在一个事务里：取题库并校验归属 → 取答题记录，确认该题当时答错（否则 4040）→ 判题 →
- 已掌握：直接返回结果，不写库（幂等，满足“重复提交”场景）；
- 答对：`mark_mastered`；
- 答错：`record_wrong_retry`。

不碰 `users.total_xp/total_coins`、`answer_records`、`reports`。

### 4. 前端：列表接口返回完整题目，前端本地判题做动画

`MistakeItem.question` 是完整 `Question`（含答案）。闯关接口本来就把答案下发给前端做即时判题，这里没有新增泄露面。重做页点选后立即用 `judgeAnswer` 播动画，同时调用 `POST /review/answer`；“已移出错题本”文案以接口返回的 `mastered` 为准，接口失败时提示“没保存上，稍后再试”，不移除。

### 5. 前端页面与状态

- `pages/review/index.tsx`：用 `useDidShow` 每次进入都拉列表（tab 页不会重新挂载）；三态：加载中 / 失败（重试按钮）/ 列表或空状态。分组用新纯函数 `core/review.ts#groupMistakes(items)`（按 `quiz_id` 分组、保持接口顺序），带单测。
- `pages/review-answer/index.tsx`（普通页，`navigateTo` 进入）：点击列表项时把该 `MistakeItem` 写进 store 的内存字段 `reviewing`（不持久化）；页面拿不到 `reviewing`（如被系统回收后重进）就 `switchTab` 回复习页。
- “再做一次”只重置本页的作答状态，不重新请求。
- 返回复习页时由 `useDidShow` 重新拉列表，所以不需要在前端手动删除条目；同时乐观地从列表里先去掉已掌握的那条，避免闪一下。

### 6. 抽出共用的作答组件

把闯关页的 `AnsweredOptions`、未作答时的选项/判断按钮、`Mark` 抽到 `components/QuestionOptions.tsx`，相关样式从 `pages/quiz/index.scss` 移到 `components/question-options.scss`，闯关页和重做页都引用。闯关页行为不变。

- 备选：重做页直接复制一份。否决：两份判题展示会逐渐不一致，原型要求两边交互一致。

## Risks / Trade-offs

- [列表接口随答题记录线性增长，每次都展开全部 JSON] → MVP 用户一般几十话以内，几百个题目对象毫无压力；若后续变大，再改为结算时物化错题表（`review_items` 结构可以直接扩展承载），接口契约不变。
- [样式抽离后小程序 WXSS 表现与 H5 不同] → 改完在微信开发者工具真机模拟器里分别过一遍闯关页和重做页，确认选项、判题标记、动画都正常。
- [前端本地判题与服务端结果不一致（理论上规则相同）] → UI 的对错展示用本地结果，掌握状态以服务端为准；不一致时以服务端为准刷新列表。
- [题库的 `questions_json` 被删改导致错题对应的题找不到] → 合并时跳过找不到题目的记录并打 warning 日志，不让整个列表失败。

## Migration Plan

- 部署：新表随应用启动的 `CREATE TABLE IF NOT EXISTS` 自动创建，`TABLES` 加上 `review_items` 供测试清表。无需数据迁移。
- 回滚：回退代码即可，`review_items` 表可留着不影响旧版本运行。

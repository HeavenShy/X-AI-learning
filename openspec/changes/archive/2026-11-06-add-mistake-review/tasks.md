# Tasks

## 1. 后端：数据表与判题复用

- [x] 1.1 在 `backend/app/resources/schema.sql` 新增 `review_items` 表（结构见 design 决策 1），`app/core/db.py` 的 `TABLES` 加上 `review_items`；验证：`backend/tests/test_db.py` 通过，并新增断言建表后存在 `review_items`
- [x] 1.2 在 `app/services/scoring_service.py` 抽出公开函数 `is_answer_correct(question, selected)`，`score()` 改为调用它；验证：`test_scoring_service.py` 全部通过，并新增用例覆盖大小写 / 空格 / 重复选项 / 空选择 / 多选漏选

## 2. 后端：错题列表

- [x] 2.1 新增 `app/models/review.py`（`MistakeItem`、`MistakeList`、`ReviewAnswerRequest`、`ReviewAnswerResult`）；验证：mypy/导入无误，后续接口测试覆盖字段
- [x] 2.2 新增 `app/repositories/review_repository.py` 的读取函数（`list_wrong_sources`、`get_review_items`）与 `app/services/review_service.py` 中的纯函数 `merge_mistakes`；验证：新增 `tests/test_review_service.py` 离线单测覆盖：只取答错题、已掌握剔除、答错次数 = 1 + 重做答错数、上次错误答案取值优先级、按完结时间新到旧且话内保持题序、题目缺失时跳过
- [x] 2.3 新增路由 `app/api/v1/routes/review.py` 的 `GET /review/mistakes` 并在 `router.py` 注册，`deps.py` 加 `require_review_service`；验证：新增 `tests/test_review_api.py` 覆盖未登录 4010、空列表、完结一话后答错题出现、只出题未完结不出现、看不到别人的错题

## 3. 后端：重做提交

- [x] 3.1 实现 `review_repository` 写入函数（`record_wrong_retry`、`mark_mastered`）与 `ReviewService.answer`（决策 3 的事务流程）；验证：`test_review_api.py` 覆盖答对后从列表消失、答错后次数 +1 且上次答案更新、多选漏选判错、已掌握重复提交幂等
- [x] 3.2 新增 `POST /review/answer`；验证：`test_review_api.py` 覆盖未登录 4010、别人的题 / 不存在的题 / 闯关时答对的题均返回 4040 且不写 `review_items`、重做答对后 `/user/profile` 经验金币不变且 `/user/quizzes` 正确率不变
- [x] 3.3 在 `docs/用户系统方案设计文档.md` 补充两个接口的请求/响应示例与 `review_items` 表说明；验证：文档中的字段名与 `app/models/review.py` 一致；`cd backend && pytest` 全部通过

## 4. 前端：类型、接口与纯逻辑

- [x] 4.1 在 `src/types/api.ts` 增加 `MistakeItem`、`MistakeList`、`ReviewAnswerRequest`、`ReviewAnswerResult`，在 `src/services/api.ts` 增加 `listMistakes`、`submitReviewAnswer`；验证：`npm run typecheck` 通过
- [x] 4.2 新增 `src/core/review.ts`：`groupMistakes(items)`（按 quiz 分组、保持顺序、带组内题数）与 `wrongCountLabel(n)`（“错 N 次”）；验证：新增 `tests/review.test.ts`，`npm test` 通过

## 5. 前端：共用作答组件

- [x] 5.1 把闯关页的选项作答 / 判题后展示（`AnsweredOptions`、`Mark`、未作答的选项与判断按钮）抽到 `src/components/QuestionOptions.tsx`，相关样式移到 `src/components/question-options.scss`，闯关页改为引用；验证：`npm run typecheck`、`npm test`（含 `wxss-compat.test.ts`）通过，并在微信开发者工具里走一遍闯关页的单选 / 多选 / 判断题，判题标记与动画与改动前一致

## 6. 前端：复习页与重做页

- [x] 6.1 store 增加内存字段 `reviewing: MistakeItem | null` 与 setter（不写入持久化）；验证：`npm run typecheck` 通过，确认持久化字段列表未包含 `reviewing`
- [x] 6.2 重写 `src/pages/review/index.tsx`：`useDidShow` 拉取列表，加载中 / 失败重试 / 空状态（“去闯关”切到闯关标签）/ 按话分组列表（题型标签、题干、错 N 次），点击写入 `reviewing` 后 `navigateTo` 重做页，增加对应 scss；验证：微信开发者工具中有错题、无错题、断网三种情况显示正确
- [x] 6.3 新增 `src/pages/review-answer/`（index.tsx / index.config.ts / index.scss）并在 `app.config.ts` 注册：复用 `QuestionOptions` 作答，显示上次的错误答案，判题后展示讲解；调用 `submitReviewAnswer`，答对显示“已移出错题本”+“回到复习”，答错显示“再做一次”+“回到复习”，提交失败 toast 提示；无 `reviewing` 时回到复习页；验证：微信开发者工具中答对后返回列表该题消失、答错后“再做一次”可重选且返回后显示“错 2 次”、断网提交提示且题目仍在列表

## 7. 联调验证

- [x] 7.1 端到端：本地起后端连测试库，小程序里完结一话并故意答错 2 题 → 复习页出现 2 题 → 重做 1 题答对、1 题答错 → 列表剩 1 题且显示“错 2 次”，“我的”页经验金币未变化；同时确认 `cd backend && pytest`、`cd frontend && npm test && npm run typecheck` 全部通过

## Workflow follow-up

- 实现与验证完成后运行 `/opsx:archive` 归档本次改动。

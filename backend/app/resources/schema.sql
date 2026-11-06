-- 一话一懂 用户系统表结构（MySQL 8.x）。所有时间字段存 UTC。
-- 应用启动时自动执行（CREATE TABLE IF NOT EXISTS，幂等），也可手动：python -m scripts.init_db

CREATE TABLE IF NOT EXISTS users (
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  openid      VARCHAR(64)     NOT NULL COMMENT '微信 openid',
  nickname    VARCHAR(100)    NOT NULL DEFAULT '' COMMENT '昵称',
  avatar_url  VARCHAR(500)    NOT NULL DEFAULT '' COMMENT '头像地址（本期不上传，预留）',
  total_xp    INT UNSIGNED    NOT NULL DEFAULT 0 COMMENT '累计经验',
  total_coins INT UNSIGNED    NOT NULL DEFAULT 0 COMMENT '累计金币',
  created_at  DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at  DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_users_openid (openid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户';

CREATE TABLE IF NOT EXISTS quiz_sessions (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  quiz_id        VARCHAR(64)     NOT NULL COMMENT '业务 quiz_id',
  user_id        BIGINT UNSIGNED NOT NULL,
  title          VARCHAR(255)    NOT NULL,
  summary        TEXT            NOT NULL,
  user_input     TEXT            NOT NULL COMMENT '原始输入（清洗后）',
  difficulty     VARCHAR(16)     NOT NULL DEFAULT 'mixed',
  topic          VARCHAR(16)     NOT NULL DEFAULT '' COMMENT '大类主题（知识树分组），空串即“其他”',
  question_count INT UNSIGNED    NOT NULL,
  questions_json JSON            NOT NULL COMMENT '题目（含答案与讲解）',
  created_at     DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_quiz_sessions_quiz_id (quiz_id),
  KEY idx_quiz_sessions_user (user_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='题库（一话）';

CREATE TABLE IF NOT EXISTS answer_records (
  id                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  quiz_id           VARCHAR(64)     NOT NULL,
  user_id           BIGINT UNSIGNED NOT NULL,
  records_json      JSON            NOT NULL COMMENT '服务端重新判题后的每题结果',
  total_questions   INT UNSIGNED    NOT NULL,
  correct_count     INT UNSIGNED    NOT NULL,
  accuracy          DECIMAL(5,2)    NOT NULL COMMENT '正确率（百分比）',
  total_duration_ms INT UNSIGNED    NOT NULL DEFAULT 0,
  xp_gained         INT UNSIGNED    NOT NULL DEFAULT 0,
  coins_gained      INT UNSIGNED    NOT NULL DEFAULT 0,
  created_at        DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '完结时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_answer_records_user_quiz (user_id, quiz_id),
  KEY idx_answer_records_user_time (user_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='答题记录（一话一条）';

CREATE TABLE IF NOT EXISTS reports (
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  quiz_id     VARCHAR(64)     NOT NULL,
  user_id     BIGINT UNSIGNED NOT NULL,
  report_json JSON            NOT NULL COMMENT '复盘报告完整内容',
  created_at  DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at  DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_reports_user_quiz (user_id, quiz_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='复盘报告';

-- 错题本：错题本身从 answer_records 推导，这里只存重做状态（第一次重做时才写入）
CREATE TABLE IF NOT EXISTS review_items (
  id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id            BIGINT UNSIGNED NOT NULL,
  quiz_id            VARCHAR(64)     NOT NULL,
  question_id        VARCHAR(64)     NOT NULL,
  wrong_retries      INT UNSIGNED    NOT NULL DEFAULT 0 COMMENT '重做时又答错的次数',
  last_selected_json JSON            NULL     COMMENT '最近一次重做答错时的选项',
  mastered_at        DATETIME(3)     NULL     COMMENT '重做答对的时间，非空即已掌握',
  created_at         DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at         DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_review_items (user_id, quiz_id, question_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='错题重做状态';

-- 知识库：资料文本以 MySQL 为准，向量存在嵌入式 Chroma（可从 kb_chunks 重建）
CREATE TABLE IF NOT EXISTS knowledge_bases (
  id         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  kb_id      VARCHAR(64)     NOT NULL COMMENT '业务 kb_id',
  user_id    BIGINT UNSIGNED NOT NULL,
  name       VARCHAR(64)     NOT NULL,
  created_at DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_knowledge_bases_kb_id (kb_id),
  KEY idx_knowledge_bases_user (user_id, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='知识库';

CREATE TABLE IF NOT EXISTS kb_documents (
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  document_id VARCHAR(64)     NOT NULL COMMENT '业务 document_id',
  kb_id       VARCHAR(64)     NOT NULL,
  user_id     BIGINT UNSIGNED NOT NULL,
  filename    VARCHAR(255)    NOT NULL,
  file_type   VARCHAR(8)      NOT NULL COMMENT 'pdf / docx / txt / md',
  size_bytes  INT UNSIGNED    NOT NULL,
  status      VARCHAR(16)     NOT NULL DEFAULT 'processing' COMMENT 'processing / ready / failed',
  fail_reason VARCHAR(255)    NULL,
  page_count  INT UNSIGNED    NULL     COMMENT '仅 PDF',
  char_count  INT UNSIGNED    NOT NULL DEFAULT 0,
  chunk_count INT UNSIGNED    NOT NULL DEFAULT 0,
  created_at  DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at  DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_kb_documents_document_id (document_id),
  KEY idx_kb_documents_kb (kb_id, created_at),
  KEY idx_kb_documents_user (user_id),
  KEY idx_kb_documents_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='知识库资料';

-- 自增 id 同时作为 Chroma 中的向量 id
CREATE TABLE IF NOT EXISTS kb_chunks (
  id          BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
  document_id VARCHAR(64)      NOT NULL,
  user_id     BIGINT UNSIGNED  NOT NULL,
  seq         INT UNSIGNED     NOT NULL COMMENT '资料内顺序，从 0 开始',
  page        INT UNSIGNED     NULL     COMMENT 'PDF 页码，从 1 开始',
  text        TEXT             NOT NULL,
  flagged     TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '命中敏感词，不参与出题',
  PRIMARY KEY (id),
  KEY idx_kb_chunks_document (document_id, seq)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='资料文本片段';

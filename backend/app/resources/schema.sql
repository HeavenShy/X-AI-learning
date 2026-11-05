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

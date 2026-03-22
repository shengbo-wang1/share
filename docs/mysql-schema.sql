CREATE TABLE app_user (
  user_id VARCHAR(64) PRIMARY KEY,
  open_id_hash VARCHAR(128) NULL,
  union_id_hash VARCHAR(128) NULL,
  nickname VARCHAR(64) NULL,
  avatar_url VARCHAR(255) NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE stock_basic (
  code VARCHAR(16) PRIMARY KEY,
  stock_name VARCHAR(64) NOT NULL,
  exchange VARCHAR(16) NOT NULL,
  market VARCHAR(16) NOT NULL,
  board VARCHAR(32) NOT NULL,
  list_date DATE NULL,
  delist_date DATE NULL,
  industry VARCHAR(64) NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'LISTED',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_stock_basic_status (status),
  KEY idx_stock_basic_board (board)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE index_basic (
  index_code VARCHAR(32) PRIMARY KEY,
  index_name VARCHAR(64) NOT NULL,
  market VARCHAR(16) NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_index_basic_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE trading_calendar (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  exchange VARCHAR(16) NOT NULL,
  trade_date DATE NOT NULL,
  is_open TINYINT(1) NOT NULL,
  prev_trade_date DATE NULL,
  next_trade_date DATE NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_trading_calendar (exchange, trade_date),
  KEY idx_trading_calendar_open (exchange, is_open, trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE staging_raw (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  source VARCHAR(32) NOT NULL,
  dataset VARCHAR(64) NOT NULL,
  biz_key VARCHAR(128) NOT NULL,
  request_batch_id VARCHAR(64) NOT NULL,
  payload_json JSON NOT NULL,
  checksum VARCHAR(128) NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'FETCHED',
  fetched_at DATETIME NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_staging_raw_lookup (source, dataset, biz_key, fetched_at),
  KEY idx_staging_raw_batch (request_batch_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE job_run_log (
  job_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  job_type VARCHAR(32) NOT NULL,
  job_name VARCHAR(64) NOT NULL,
  batch_date DATE NOT NULL,
  request_batch_id VARCHAR(64) NULL,
  start_time DATETIME NOT NULL,
  end_time DATETIME NULL,
  status VARCHAR(16) NOT NULL,
  success_count INT NOT NULL DEFAULT 0,
  fail_count INT NOT NULL DEFAULT 0,
  retry_count INT NOT NULL DEFAULT 0,
  error_message TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_job_run_log_status (job_type, batch_date, status),
  KEY idx_job_run_log_batch (request_batch_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE data_quality_check (
  check_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  job_id BIGINT NULL,
  dataset VARCHAR(64) NOT NULL,
  biz_key VARCHAR(128) NOT NULL,
  check_type VARCHAR(64) NOT NULL,
  severity VARCHAR(16) NOT NULL,
  status VARCHAR(16) NOT NULL,
  actual_value VARCHAR(255) NULL,
  expected_rule VARCHAR(255) NULL,
  message TEXT NULL,
  checked_at DATETIME NOT NULL,
  KEY idx_data_quality_check_lookup (dataset, biz_key, status, severity),
  KEY idx_data_quality_check_job (job_id),
  CONSTRAINT fk_data_quality_check_job FOREIGN KEY (job_id) REFERENCES job_run_log(job_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE stock_daily_raw (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  code VARCHAR(16) NOT NULL,
  trade_date DATE NOT NULL,
  source_batch_id VARCHAR(64) NULL,
  open_price DECIMAL(16,4) NOT NULL,
  high_price DECIMAL(16,4) NOT NULL,
  low_price DECIMAL(16,4) NOT NULL,
  close_price DECIMAL(16,4) NOT NULL,
  volume DECIMAL(20,4) NOT NULL,
  amount DECIMAL(20,4) NOT NULL,
  adj_factor DECIMAL(20,8) NULL,
  source VARCHAR(32) NOT NULL DEFAULT 'AKSHARE',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_stock_daily_raw (code, trade_date),
  KEY idx_stock_daily_raw_trade_date (trade_date),
  KEY idx_stock_daily_raw_batch (source_batch_id),
  CONSTRAINT fk_stock_daily_raw_code FOREIGN KEY (code) REFERENCES stock_basic(code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE stock_daily_feature (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  code VARCHAR(16) NOT NULL,
  trade_date DATE NOT NULL,
  source_batch_id VARCHAR(64) NULL,
  qfq_open DECIMAL(16,4) NOT NULL,
  qfq_high DECIMAL(16,4) NOT NULL,
  qfq_low DECIMAL(16,4) NOT NULL,
  qfq_close DECIMAL(16,4) NOT NULL,
  volume DECIMAL(20,4) NOT NULL,
  ma5 DECIMAL(16,4) NOT NULL,
  ma10 DECIMAL(16,4) NOT NULL,
  ma20 DECIMAL(16,4) NOT NULL,
  k_value DECIMAL(16,4) NOT NULL,
  d_value DECIMAL(16,4) NOT NULL,
  j_value DECIMAL(16,4) NOT NULL,
  dif DECIMAL(16,4) NOT NULL,
  dea DECIMAL(16,4) NOT NULL,
  macd DECIMAL(16,4) NOT NULL,
  outstanding_share DECIMAL(20,4) NULL,
  float_mv_est DECIMAL(20,4) NULL,
  cap_bucket VARCHAR(16) NOT NULL,
  feature_version VARCHAR(32) NOT NULL DEFAULT 'v1',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_stock_daily_feature (code, trade_date),
  KEY idx_stock_daily_feature_trade_date (trade_date),
  KEY idx_stock_daily_feature_cap_bucket (cap_bucket),
  KEY idx_stock_daily_feature_batch (source_batch_id),
  CONSTRAINT fk_stock_daily_feature_code FOREIGN KEY (code) REFERENCES stock_basic(code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE index_daily_raw (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  index_code VARCHAR(32) NOT NULL,
  trade_date DATE NOT NULL,
  source_batch_id VARCHAR(64) NULL,
  open_price DECIMAL(16,4) NOT NULL,
  high_price DECIMAL(16,4) NOT NULL,
  low_price DECIMAL(16,4) NOT NULL,
  close_price DECIMAL(16,4) NOT NULL,
  volume DECIMAL(20,4) NULL,
  amount DECIMAL(20,4) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_index_daily_raw (index_code, trade_date),
  KEY idx_index_daily_raw_trade_date (trade_date),
  KEY idx_index_daily_raw_batch (source_batch_id),
  CONSTRAINT fk_index_daily_raw_code FOREIGN KEY (index_code) REFERENCES index_basic(index_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE index_daily_feature (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  index_code VARCHAR(32) NOT NULL,
  trade_date DATE NOT NULL,
  source_batch_id VARCHAR(64) NULL,
  pct_change_1d DECIMAL(12,6) NOT NULL,
  drawdown_5d DECIMAL(12,6) NOT NULL,
  vol_ratio_1d_5d DECIMAL(12,6) NOT NULL,
  panic_flag TINYINT(1) NOT NULL DEFAULT 0,
  feature_version VARCHAR(32) NOT NULL DEFAULT 'v1',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_index_daily_feature (index_code, trade_date),
  KEY idx_index_daily_feature_trade_date (trade_date),
  KEY idx_index_daily_feature_panic (panic_flag),
  KEY idx_index_daily_feature_batch (source_batch_id),
  CONSTRAINT fk_index_daily_feature_code FOREIGN KEY (index_code) REFERENCES index_basic(index_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE challenge (
  challenge_id VARCHAR(64) PRIMARY KEY,
  code VARCHAR(16) NOT NULL,
  start_date DATE NOT NULL,
  end_date DATE NOT NULL,
  total_days INT NOT NULL,
  actionable_days INT NOT NULL,
  difficulty VARCHAR(32) NOT NULL,
  tags_json JSON NOT NULL,
  featured TINYINT(1) NOT NULL DEFAULT 0,
  reveal_stock_name TINYINT(1) NOT NULL DEFAULT 0,
  template_version VARCHAR(32) NOT NULL DEFAULT 'v1',
  generation_batch_id VARCHAR(64) NULL,
  freeze_status VARCHAR(16) NOT NULL DEFAULT 'FROZEN',
  status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_challenge_code (code),
  KEY idx_challenge_featured_status (featured, status),
  KEY idx_challenge_generation_batch (generation_batch_id, freeze_status),
  CONSTRAINT fk_challenge_code FOREIGN KEY (code) REFERENCES stock_basic(code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE challenge_day (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  challenge_id VARCHAR(64) NOT NULL,
  day_index INT NOT NULL,
  trade_date DATE NOT NULL,
  generation_batch_id VARCHAR(64) NULL,
  raw_open DECIMAL(16,4) NOT NULL,
  raw_close DECIMAL(16,4) NOT NULL,
  qfq_open DECIMAL(16,4) NOT NULL,
  qfq_high DECIMAL(16,4) NOT NULL,
  qfq_low DECIMAL(16,4) NOT NULL,
  qfq_close DECIMAL(16,4) NOT NULL,
  volume DECIMAL(20,4) NOT NULL,
  ma5 DECIMAL(16,4) NOT NULL,
  ma10 DECIMAL(16,4) NOT NULL,
  ma20 DECIMAL(16,4) NOT NULL,
  k_value DECIMAL(16,4) NOT NULL,
  d_value DECIMAL(16,4) NOT NULL,
  j_value DECIMAL(16,4) NOT NULL,
  dif DECIMAL(16,4) NOT NULL,
  dea DECIMAL(16,4) NOT NULL,
  macd DECIMAL(16,4) NOT NULL,
  cap_bucket VARCHAR(16) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_challenge_day_index (challenge_id, day_index),
  UNIQUE KEY uk_challenge_day_date (challenge_id, trade_date),
  KEY idx_challenge_day_trade_date (trade_date),
  KEY idx_challenge_day_generation_batch (generation_batch_id),
  CONSTRAINT fk_challenge_day_challenge FOREIGN KEY (challenge_id) REFERENCES challenge(challenge_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE user_session (
  session_id VARCHAR(64) PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL,
  challenge_id VARCHAR(64) NOT NULL,
  signature VARCHAR(128) NOT NULL,
  status VARCHAR(16) NOT NULL,
  current_day_index INT NOT NULL DEFAULT 0,
  client_version VARCHAR(32) NULL,
  started_at DATETIME NOT NULL,
  submitted_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_user_session_user (user_id),
  KEY idx_user_session_challenge (challenge_id),
  KEY idx_user_session_status (status),
  CONSTRAINT fk_user_session_user FOREIGN KEY (user_id) REFERENCES app_user(user_id),
  CONSTRAINT fk_user_session_challenge FOREIGN KEY (challenge_id) REFERENCES challenge(challenge_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE user_action (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  session_id VARCHAR(64) NOT NULL,
  day_index INT NOT NULL,
  trade_date DATE NOT NULL,
  target_position INT NOT NULL,
  effective_trade_date DATE NULL,
  effective_price DECIMAL(16,4) NULL,
  action_source VARCHAR(16) NOT NULL DEFAULT 'MINIPROGRAM',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_user_action_session_day (session_id, day_index),
  UNIQUE KEY uk_user_action_session_date (session_id, trade_date),
  KEY idx_user_action_trade_date (trade_date),
  CONSTRAINT fk_user_action_session FOREIGN KEY (session_id) REFERENCES user_session(session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE user_result (
  session_id VARCHAR(64) PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL,
  challenge_id VARCHAR(64) NOT NULL,
  final_return DECIMAL(12,6) NOT NULL,
  max_drawdown DECIMAL(12,6) NOT NULL,
  score DECIMAL(12,6) NOT NULL,
  percentile DECIMAL(12,6) NOT NULL,
  final_position INT NOT NULL DEFAULT 0,
  poster_payload_json JSON NOT NULL,
  equity_curve_json JSON NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_user_result_user (user_id),
  KEY idx_user_result_challenge (challenge_id),
  KEY idx_user_result_score (score, max_drawdown),
  KEY idx_user_result_created (created_at),
  CONSTRAINT fk_user_result_session FOREIGN KEY (session_id) REFERENCES user_session(session_id),
  CONSTRAINT fk_user_result_user FOREIGN KEY (user_id) REFERENCES app_user(user_id),
  CONSTRAINT fk_user_result_challenge FOREIGN KEY (challenge_id) REFERENCES challenge(challenge_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- challenge 业务约定：
-- 1) challenge.difficulty 第一版固定枚举：easy / normal / hard。
-- 2) challenge.tags_json 第一版推荐结构：primaryTag / secondaryTag / tagVersion。
-- 3) challenge_candidate 本轮只作为流程概念，不单独建表。
-- 4) 第 5 类标签（大盘恐慌日该不该抄底）逻辑依赖 index_daily_feature。
-- 5) 指数数据只用于内部语义判断，不进入前端展示接口。
-- 6) index_basic 第一版固定维护沪深核心 3 指数：上证指数、深证成指、创业板指。

-- 规则说明：
-- 1) stock_daily_raw / stock_daily_feature / index_daily_raw / index_daily_feature 通过 source_batch_id 追踪来源批次。
-- 2) challenge / challenge_day 通过 generation_batch_id 追踪出题批次。
-- 3) challenge/challenge_day 发布后冻结，不做覆盖更新；若需修正，生成新 challenge_id 或将旧题下线。
-- 4) stock_daily_raw / stock_daily_feature 对 (code, trade_date) 采取幂等 upsert。
-- 5) index_daily_raw / index_daily_feature 对 (index_code, trade_date) 采取幂等 upsert。
-- 6) 若 challenge 窗口对应指数数据缺失、批次不完整或质检未通过，则直接停用第 5 类标签。

-- Expand HTML 预览事件表以支持主方案、子方案、按钮点击和模块曝光。
-- 旧记录和旧客户端请求统一按 button_click 解释，无需单独数据回填。
-- 本迁移是一次性前向迁移，不应在同一数据库重复执行。
-- Forward-only：生产回滚应先停止新事件写入，再通过新的前向迁移处理；
-- 直接 DROP 新列会永久丢失已经采集的事件维度，因此不提供破坏性 DOWN。

ALTER TABLE swe_html_preview_click_events
ADD COLUMN event_type VARCHAR(32) NOT NULL DEFAULT 'button_click'
  COMMENT '事件类型：button_click/preview_view/module_exposure',
ADD COLUMN template_type VARCHAR(16) NULL COMMENT '模板类型：main/sub',
ADD COLUMN template_id BIGINT NULL COMMENT '当前事件所在模板ID',
ADD COLUMN result_id VARCHAR(128) NULL COMMENT '当前模板生成结果ID',
ADD COLUMN event_target_id VARCHAR(255) NULL COMMENT '模块的稳定标识',
ADD COLUMN event_target_name VARCHAR(512) NULL COMMENT '模块的展示名称',
ADD COLUMN trace_id VARCHAR(128) NULL COMMENT '方案生成与浏览链路标识',
ALGORITHM=INPLACE,
LOCK=NONE;

ALTER TABLE swe_html_preview_click_events
ADD INDEX idx_source_event_target_clicked (
  source_id,
  event_type,
  event_target_id,
  clicked_at
),
ADD INDEX idx_source_template_type_event_clicked (
  source_id,
  template_type,
  event_type,
  clicked_at
),
ADD INDEX idx_source_template_result_clicked (
  source_id,
  template_id,
  result_id,
  clicked_at
),
ADD INDEX idx_trace_clicked (trace_id, clicked_at),
ALGORITHM=INPLACE,
LOCK=NONE;

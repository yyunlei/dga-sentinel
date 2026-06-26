-- DGA Platform — Migration 002: feedback.family for per-family threshold tuning
--
-- Phase 2 of the feedback closed loop adds a per-family FP-rate analyzer
-- that writes threshold-adjustment recommendations to pipeline_operations
-- (pending status — manual approval required, never auto-applied).
--
-- This migration adds the `family` column to feedback so the analyzer can
-- group by predicted family. NULL is allowed for legacy rows; new rows from
-- the UI's "标记为误报 / 确认 DGA" buttons populate it.

ALTER TABLE feedback
    ADD COLUMN IF NOT EXISTS family VARCHAR(64);

CREATE INDEX IF NOT EXISTS idx_feedback_family ON feedback(family);
CREATE INDEX IF NOT EXISTS idx_feedback_created_family ON feedback(created_at, family);

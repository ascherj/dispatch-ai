-- Migration: Add unique constraint on enriched_issues.issue_id
-- This ensures idempotency when resyncing issues from GitHub
-- Date: 2025-10-13
-- 
-- Purpose: Fix duplicate enriched issues appearing in frontend after resync
-- 
-- This migration:
-- 1. Removes duplicate enriched_issues (keeping most recent by processed_at)
-- 2. Adds UNIQUE constraint on issue_id column
-- 3. Verifies the constraint was successfully added

BEGIN;

-- Step 1: Remove any duplicate enriched_issues (keeping the most recent)
DELETE FROM dispatchai.enriched_issues
WHERE id IN (
    SELECT id
    FROM (
        SELECT id,
               ROW_NUMBER() OVER (PARTITION BY issue_id ORDER BY processed_at DESC) as rn
        FROM dispatchai.enriched_issues
    ) t
    WHERE t.rn > 1
);

-- Step 2: Add unique constraint on issue_id
ALTER TABLE dispatchai.enriched_issues
ADD CONSTRAINT enriched_issues_issue_id_unique UNIQUE (issue_id);

-- Step 3: Verify the constraint was added
DO $$
DECLARE
    constraint_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO constraint_count
    FROM pg_constraint
    WHERE conname = 'enriched_issues_issue_id_unique'
    AND conrelid = 'dispatchai.enriched_issues'::regclass;
    
    IF constraint_count = 1 THEN
        RAISE NOTICE 'Migration completed successfully: Unique constraint on enriched_issues.issue_id added';
    ELSE
        RAISE EXCEPTION 'Migration failed: Unique constraint was not created';
    END IF;
END $$;

COMMIT;

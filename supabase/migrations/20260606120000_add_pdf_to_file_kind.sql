-- ============================================================================
-- Migration: add_pdf_to_file_kind
-- ============================================================================
-- The initial file_kind enum was created without 'pdf' in the live database
-- (the init_files migration used IF NOT EXISTS, so adding 'pdf' to that
-- migration later had no effect on databases where the enum already existed).
--
-- ALTER TYPE ... ADD VALUE is idempotent-safe with IF NOT EXISTS (Postgres 12+).
-- ============================================================================

alter type public.file_kind add value if not exists 'pdf';

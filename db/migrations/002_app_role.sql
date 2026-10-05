-- Read-only role for the app. The password is passed in, never stored here:
--   psql -v app_password="$APP_DB_PASSWORD" -f 002_app_role.sql

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'office_app') THEN
    CREATE ROLE office_app LOGIN;
  END IF;
END $$;

ALTER ROLE office_app PASSWORD :'app_password';

-- Read access only
GRANT CONNECT ON DATABASE office_rag TO office_app;
GRANT USAGE ON SCHEMA public TO office_app;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO office_app;      -- includes views
ALTER DEFAULT PRIVILEGES FOR ROLE office_admin IN SCHEMA public
  GRANT SELECT ON TABLES TO office_app;                          -- tables created later

-- Safety for a public app (and for LLM-written SQL in Phase 2)
ALTER ROLE office_app SET default_transaction_read_only = on;
ALTER ROLE office_app SET statement_timeout = '5s';

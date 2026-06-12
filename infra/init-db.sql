-- Local-dev database bootstrap (runs once on first postgres container start).
--
-- Two roles, per Section 4.1:
--   erp_owner — owns the schema, used by Alembic migrations (RLS does not
--               apply to the table owner).
--   erp_app   — non-owner role the API connects as, so the company_isolation
--               RLS policies are enforced.
--
-- MANUAL_REVIEW: passwords below are for local development only.

CREATE ROLE erp_owner LOGIN PASSWORD 'erp_owner_dev_pw';
CREATE ROLE erp_app LOGIN PASSWORD 'erp_app_dev_pw';

CREATE DATABASE erp OWNER erp_owner;
CREATE DATABASE erp_test OWNER erp_owner;

\connect erp
ALTER SCHEMA public OWNER TO erp_owner;
GRANT USAGE ON SCHEMA public TO erp_app;
CREATE EXTENSION IF NOT EXISTS ltree;

\connect erp_test
ALTER SCHEMA public OWNER TO erp_owner;
GRANT USAGE ON SCHEMA public TO erp_app;
CREATE EXTENSION IF NOT EXISTS ltree;

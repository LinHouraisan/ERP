#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 --username postgres --dbname erp_demo \
  --set=app_password="$PG_APP_PASSWORD" --set=mock_password="$PG_MOCK_PASSWORD" <<'SQL'
CREATE ROLE erp_app LOGIN PASSWORD :'app_password';
CREATE ROLE erp_mock LOGIN PASSWORD :'mock_password';
REVOKE ALL ON SCHEMA public FROM PUBLIC;
CREATE SCHEMA app AUTHORIZATION erp_app;
CREATE SCHEMA boss AUTHORIZATION erp_mock;
ALTER ROLE erp_app SET search_path TO app;
ALTER ROLE erp_mock SET search_path TO boss;
CREATE DATABASE erp_phase1_test;
\connect erp_phase1_test
REVOKE ALL ON SCHEMA public FROM PUBLIC;
CREATE SCHEMA app AUTHORIZATION erp_app;
CREATE SCHEMA boss AUTHORIZATION erp_mock;
SQL

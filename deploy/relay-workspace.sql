\set ON_ERROR_STOP on
CREATE ROLE relay_workspace LOGIN NOINHERIT NOSUPERUSER NOCREATEROLE NOCREATEDB NOREPLICATION NOBYPASSRLS
    CONNECTION LIMIT 4 PASSWORD :'workspace_password';
CREATE DATABASE relay_developer;
REVOKE ALL ON DATABASE relay_developer FROM PUBLIC;
GRANT CONNECT, TEMP ON DATABASE relay_developer TO relay_workspace;
ALTER ROLE relay_workspace IN DATABASE relay_developer SET search_path = public;
ALTER ROLE relay_workspace IN DATABASE relay_developer SET statement_timeout = '8s';
ALTER ROLE relay_workspace IN DATABASE relay_developer SET lock_timeout = '2s';
ALTER ROLE relay_workspace IN DATABASE relay_developer SET idle_in_transaction_session_timeout = '10s';
ALTER ROLE relay_workspace IN DATABASE relay_developer SET temp_file_limit = '64MB';
\connect relay_developer
REVOKE ALL ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO relay_workspace;

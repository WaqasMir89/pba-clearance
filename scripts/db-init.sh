#!/bin/sh
set -eu
# Runs only on first initialization of the dedicated development volume.
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=app_password="$POSTGRES_PASSWORD" --set=ON_ERROR_STOP=1 <<'SQL'
CREATE ROLE clearance_app LOGIN PASSWORD :'app_password' NOSUPERUSER NOCREATEROLE NOBYPASSRLS CREATEDB;
ALTER DATABASE clearance OWNER TO clearance_app;
SQL

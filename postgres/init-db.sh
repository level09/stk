#!/bin/sh
set -eu
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set=app_password="$DB_PASSWORD" --set=ON_ERROR_STOP=1 <<'SQL'
CREATE USER stk PASSWORD :'app_password';
ALTER DATABASE stk OWNER TO stk;
SQL

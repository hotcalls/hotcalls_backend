#!/bin/sh
# POSIX-compatible init script for Postgres container

AGENT_DB_USER="${AGENT_DB_USER:-}"
AGENT_DB_PASSWORD="${AGENT_DB_PASSWORD:-}"
DB_NAME="${POSTGRES_DB:-${POSTGRES_DATABASE:-postgres}}"

if [ -z "$AGENT_DB_USER" ] || [ -z "$AGENT_DB_PASSWORD" ]; then
  echo "[agent-ro] AGENT_DB_USER/AGENT_DB_PASSWORD not set; skipping RO user creation."
  exit 0
fi

echo "[agent-ro] Creating read-only user '$AGENT_DB_USER' for database '$DB_NAME'..."

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$DB_NAME" <<SQL
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$AGENT_DB_USER') THEN
    CREATE ROLE "$AGENT_DB_USER" LOGIN PASSWORD '$AGENT_DB_PASSWORD';
  END IF;
END$$;

GRANT CONNECT ON DATABASE "$DB_NAME" TO "$AGENT_DB_USER";
GRANT USAGE ON SCHEMA public TO "$AGENT_DB_USER";
GRANT SELECT ON TABLE public.core_livekit_agent TO "$AGENT_DB_USER";
SQL

echo "[agent-ro] Read-only user '$AGENT_DB_USER' configured."



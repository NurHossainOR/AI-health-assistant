#!/bin/sh
set -e

echo "Waiting for Postgres..."
until python -c "
import asyncio, os, sys
import asyncpg

async def check():
    url = os.environ.get('DATABASE_URL', '')
    dsn = url.replace('postgresql+asyncpg://', 'postgresql://')
    conn = await asyncpg.connect(dsn)
    await conn.close()

asyncio.run(check())
" 2>/dev/null; do
  sleep 1
done

echo "Postgres is up — initializing schema and admin user..."
python scripts/create_admin.py || true

exec "$@"

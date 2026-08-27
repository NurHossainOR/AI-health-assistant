#!/usr/bin/env python3
"""Create an initial admin user for local development."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.main import init_db
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.user import User, UserRole, UserStatus


async def main() -> None:
    await init_db()
    email = sys.argv[1] if len(sys.argv) > 1 else "admin@example.com"
    password = sys.argv[2] if len(sys.argv) > 2 else "AdminPass123!"
    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none():
            print(f"Admin already exists: {email}")
            return
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name="Platform Admin",
            role=UserRole.admin,
            status=UserStatus.active,
            email_verified=True,
        )
        db.add(user)
        await db.commit()
        print(f"Created admin {email}")


if __name__ == "__main__":
    asyncio.run(main())

from fastapi import APIRouter

from app.api.v1 import admin, auth, chat, consent, documents, users

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(consent.router)
api_router.include_router(admin.router)
api_router.include_router(documents.router)
api_router.include_router(users.router)
api_router.include_router(chat.router)

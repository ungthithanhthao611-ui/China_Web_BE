from fastapi import APIRouter

from app.api.routes import admin, admin_honors, admin_onlyoffice, auth, health, news_workflow, public

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(public.router, prefix="/public", tags=["public"])
api_router.include_router(news_workflow.public_news_router, tags=["news-workflow"])
api_router.include_router(news_workflow.admin_news_router, tags=["news-workflow"])
api_router.include_router(news_workflow.admin_media_router, tags=["news-workflow"])
api_router.include_router(admin_honors.router, prefix="/admin", tags=["admin"])
api_router.include_router(admin_onlyoffice.router, prefix="/admin", tags=["admin"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])

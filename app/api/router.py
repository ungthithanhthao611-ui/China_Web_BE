from fastapi import APIRouter

from app.api.routes import admin, admin_honors, admin_news, auth, cart, health, public, user_auth

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(user_auth.router, prefix="/user/auth", tags=["user-auth"])
api_router.include_router(cart.router, prefix="/user/cart", tags=["cart"])
api_router.include_router(public.router, prefix="/public", tags=["public"])
api_router.include_router(admin_news.router, tags=["admin-news"])
api_router.include_router(admin_honors.router, prefix="/admin", tags=["admin"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])

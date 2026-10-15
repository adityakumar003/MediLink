"""
app/api/routes/auth.py
───────────────────────
Authentication endpoints: register, login, logout, me.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse

from app.api.dependencies import get_current_user
from app.models.user import User
from app.schemas.auth import LoginRequest, MeResponse, RegisterRequest, TokenResponse
from app.services import auth_service

router = APIRouter()


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=201,
    summary="Register a new user account (patient or doctor)",
)
async def register(payload: RegisterRequest) -> TokenResponse:
    """
    Create a new patient or doctor account.
    Returns a JWT access token immediately (no separate login step needed).
    """
    return await auth_service.register_user(payload)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and receive an access token",
)
async def login(payload: LoginRequest) -> TokenResponse:
    """
    Authenticate with email and password.
    Returns a JWT Bearer access token valid for the configured duration.
    """
    return await auth_service.login_user(payload)


@router.post(
    "/logout",
    summary="Logout (client-side token removal)",
)
async def logout() -> dict:
    """
    JWT is stateless. Actual session invalidation is done client-side
    by discarding the stored token. This endpoint confirms the action.
    """
    return {"message": "Logged out successfully."}


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Get the currently authenticated user",
)
async def me(current_user: User = Depends(get_current_user)) -> MeResponse:
    """Return the profile of the currently authenticated user."""
    return MeResponse(
        id=str(current_user.id),
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        is_active=current_user.is_active,
        has_photo=current_user.profile_photo is not None,
    )


@router.post(
    "/profile-photo",
    summary="Upload or replace your profile photo",
)
async def upload_profile_photo(
    file: UploadFile = File(..., description="JPG or PNG photo, max 2 MB"),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Store a profile photo for any authenticated user (patient or doctor)."""
    stored = await auth_service.save_profile_photo(current_user, file)
    return {"message": "Profile photo updated.", "has_photo": True, "file": stored}


@router.get(
    "/me/photo",
    summary="Download your own profile photo",
)
async def my_profile_photo(
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """Return the authenticated user's own profile photo (404 when none)."""
    from fastapi import HTTPException

    if not current_user.profile_photo:
        raise HTTPException(status_code=404, detail="No profile photo set.")
    path = auth_service._photo_path(current_user.profile_photo)
    if not path.exists():
        raise HTTPException(status_code=404, detail="No profile photo set.")
    media_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(str(path), media_type=media_type)


@router.delete(
    "/profile-photo",
    summary="Remove your profile photo",
)
async def remove_profile_photo(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Delete the photo and revert to default initials."""
    await auth_service.delete_profile_photo(current_user)
    return {"message": "Profile photo removed.", "has_photo": False}

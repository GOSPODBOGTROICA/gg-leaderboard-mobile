import os
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Response, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.models import (
    AuthRequest,
    AuthResponse,
    StakesResponse,
    LeaderboardResponse,
)
from app.auth import verify_pin, create_session_token, require_auth
from app.gg_client import get_gg_client, SUPPORTED_STAKES, normalize_stake_str

app = FastAPI(
    title="GG Leaderboard Mobile HUD API",
    description="Real-time encrypted GGPoker Spin & Gold Leaderboard HUD with single-user PIN security gate",
    version="1.0.0"
)

# CORS Middleware allowing mobile browsers and local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Authentication Route ---

@app.post(
    "/api/auth",
    response_model=AuthResponse,
    summary="Validate PIN and issue session token",
    responses={
        200: {"description": "Authentication successful"},
        401: {"description": "Invalid PIN"}
    }
)
async def login(req: AuthRequest, response: Response):
    """
    Validates the user's PIN code and returns a signed session token.
    Also sets a secure session cookie.
    """
    if not req.pin or not verify_pin(req.pin):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid PIN"
        )

    token, expires_in = create_session_token()

    # Set session cookie for seamless browser/PWA visits
    response.set_cookie(
        key="session_token",
        value=token,
        max_age=expires_in,
        httponly=True,
        samesite="lax",
        secure=False  # Allow local HTTP testing; HTTPS in cloud automatically overrides
    )

    return AuthResponse(
        status="ok",
        token=token,
        expires_in=expires_in
    )

# --- Stakes Route ---

@app.get(
    "/api/stakes",
    response_model=StakesResponse,
    summary="Get active Spin & Gold stakes and prize pools",
    responses={
        200: {"description": "Active stakes list"},
        401: {"description": "Unauthorized"},
        502: {"description": "Upstream GGPoker service unreachable"}
    }
)
async def get_stakes(
    force: bool = Query(default=False, description="Force refresh promotions cache"),
    _: str = Depends(require_auth)
):
    """
    Protected endpoint returning all active Spin & Gold stakes ($0.25 to $200),
    promotion IDs, total prize pools, and day cutoff time.
    """
    client = get_gg_client()
    try:
        return await client.get_active_stakes(force=force)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unable to reach upstream GGPoker service: {e}"
        )

# --- Leaderboard Route ---

@app.get(
    "/api/leaderboard",
    response_model=LeaderboardResponse,
    summary="Get Top-50 rankings and calculated Hero telemetry",
    responses={
        200: {"description": "Leaderboard rankings and Hero telemetry"},
        400: {"description": "Unsupported stake parameter"},
        401: {"description": "Unauthorized"},
        404: {"description": "Promotion for stake not found"},
        502: {"description": "Upstream GGPoker service unreachable"}
    }
)
async def get_leaderboard(
    stake: str = Query(default="$0.25", description="Stake identifier e.g. '$1' or '$0.25'"),
    hero: Optional[str] = Query(default=None, description="Hero player nickname for telemetry math"),
    force: bool = Query(default=False, description="Force refresh rankings cache"),
    _: str = Depends(require_auth)
):
    """
    Protected endpoint accepting stake and hero query parameters,
    returning decrypted Top-50 rankings and calculated Hero telemetry.
    """
    stake_norm = normalize_stake_str(stake)
    if stake_norm not in SUPPORTED_STAKES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Missing or unsupported stake parameter '{stake}'. "
                f"Supported stakes: {', '.join(SUPPORTED_STAKES)}"
            )
        )

    # If hero is not provided in query, check config default
    hero_nick = hero if (hero and hero.strip()) else get_settings().hero_nickname

    client = get_gg_client()
    try:
        return await client.get_leaderboard(
            stake=stake_norm,
            hero_query=hero_nick,
            force=force
        )
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(ve)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Upstream GGPoker leaderboard error: {e}"
        )

# --- Health Route ---

@app.get("/api/health", summary="Health check endpoint")
async def health():
    return {
        "status": "ok",
        "app": "GG_LEADERBOARD_MOBILE",
        "version": "1.0.0"
    }

# --- Static PWA Assets & Root Page ---

static_dir = get_settings().static_dir
if static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.get("/", include_in_schema=False)
async def root():
    index_file = get_settings().static_dir / "index.html"
    if index_file.is_file():
        return FileResponse(index_file)
    return JSONResponse({
        "status": "ok",
        "app": "GGPoker Spin & Gold Mobile Leaderboard HUD",
        "docs": "/docs",
        "api": "/api/stakes"
    })


@app.get("/sw.js", include_in_schema=False)
async def service_worker():
    """
    Exposes the service worker at root URL with Service-Worker-Allowed header,
    enabling full root '/' scope caching across the entire PWA.
    """
    sw_file = get_settings().static_dir / "sw.js"
    if sw_file.is_file():
        return FileResponse(
            sw_file,
            media_type="application/javascript",
            headers={
                "Service-Worker-Allowed": "/",
                "Cache-Control": "no-cache, no-store, must-revalidate"
            }
        )
    raise HTTPException(status_code=404, detail="Service worker not found")


@app.get("/manifest.json", include_in_schema=False)
async def manifest():
    """
    Exposes the web app manifest at root URL for standard PWA discovery.
    """
    manifest_file = get_settings().static_dir / "manifest.json"
    if manifest_file.is_file():
        return FileResponse(
            manifest_file,
            media_type="application/manifest+json"
        )
    raise HTTPException(status_code=404, detail="Manifest not found")


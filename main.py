import os
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, EmailStr

app = FastAPI(title="StreamLogic Backend", version="1.0.0")

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5500")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", FRONTEND_URL).split(",")

TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID", "")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET", "")
TWITCH_REDIRECT_URI = os.getenv("TWITCH_REDIRECT_URI", "")
TWITCH_SCOPES = os.getenv("TWITCH_SCOPES", "user:read:email")
LOGIN_DEMO_EMAIL = os.getenv("LOGIN_DEMO_EMAIL", "demo@streamlogic.local")
LOGIN_DEMO_PASSWORD = os.getenv("LOGIN_DEMO_PASSWORD", "12345678")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in ALLOWED_ORIGINS if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LeadRequest(BaseModel):
    channelUrl: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/api/leads")
async def create_lead(payload: LeadRequest):
    return {
        "ok": True,
        "message": "Lead received",
        "channelUrl": payload.channelUrl,
    }


@app.post("/api/auth/login")
async def login(payload: LoginRequest):
    if payload.email != LOGIN_DEMO_EMAIL or payload.password != LOGIN_DEMO_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    fake_token = secrets.token_urlsafe(24)
    return {
        "ok": True,
        "token": fake_token,
        "user": {
            "email": payload.email,
            "plan": "Pro",
            "name": "Demo User",
        },
    }


@app.get("/api/dashboard/preview")
async def dashboard_preview():
    return {
        "avgOnline": 146,
        "retention": 72,
        "ctr": 8.1,
        "insight": "Лучший рост даёт сильный интро-хук в первые 2 минуты и повторный CTA на 18-й минуте.",
    }


@app.get("/auth/twitch")
async def twitch_auth():
    if not TWITCH_CLIENT_ID or not TWITCH_REDIRECT_URI:
        raise HTTPException(
            status_code=500,
            detail="TWITCH_CLIENT_ID or TWITCH_REDIRECT_URI is missing",
        )

    params = {
        "client_id": TWITCH_CLIENT_ID,
        "redirect_uri": TWITCH_REDIRECT_URI,
        "response_type": "code",
        "scope": TWITCH_SCOPES,
        "force_verify": "true",
    }
    url = "https://id.twitch.tv/oauth2/authorize?" + urlencode(params)
    return RedirectResponse(url)


@app.get("/auth/twitch/callback")
async def twitch_callback(code: str):
    if not TWITCH_CLIENT_ID or not TWITCH_CLIENT_SECRET or not TWITCH_REDIRECT_URI:
        raise HTTPException(
            status_code=500,
            detail="Twitch OAuth env vars are not fully configured",
        )

    token_url = "https://id.twitch.tv/oauth2/token"
    async with httpx.AsyncClient(timeout=20.0) as client:
        token_response = await client.post(
            token_url,
            params={
                "client_id": TWITCH_CLIENT_ID,
                "client_secret": TWITCH_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": TWITCH_REDIRECT_URI,
            },
        )

        if token_response.status_code >= 400:
            raise HTTPException(status_code=400, detail="Failed to exchange code for token")

        token_data = token_response.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(status_code=400, detail="No access token returned by Twitch")

        user_response = await client.get(
            "https://api.twitch.tv/helix/users",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Client-Id": TWITCH_CLIENT_ID,
            },
        )

        if user_response.status_code >= 400:
            raise HTTPException(status_code=400, detail="Failed to load Twitch user")

        user_data = user_response.json().get("data", [])
        user = user_data[0] if user_data else {}

    redirect_to = f"{FRONTEND_URL}?twitch_login=success&display_name={user.get('display_name', '')}"
    return RedirectResponse(redirect_to)

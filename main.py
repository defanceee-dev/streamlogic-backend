import json
import os
import secrets
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr

app = FastAPI(title="StreamLogic Backend", version="2.0.0")

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5500")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", FRONTEND_URL).split(",")

TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID", "")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET", "")
TWITCH_REDIRECT_URI = os.getenv("TWITCH_REDIRECT_URI", "")
TWITCH_SCOPES = os.getenv("TWITCH_SCOPES", "user:read:email")

LOGIN_DEMO_EMAIL = os.getenv("LOGIN_DEMO_EMAIL", "demo@streamlogic.local")
LOGIN_DEMO_PASSWORD = os.getenv("LOGIN_DEMO_PASSWORD", "12345678")

BASE_DIR = Path(__file__).resolve().parent
USERS_FILE = BASE_DIR / "users.json"
LEADS_FILE = BASE_DIR / "leads.json"
SETTINGS_FILE = BASE_DIR / "settings.json"

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in ALLOWED_ORIGINS if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LeadRequest(BaseModel):
    channelUrl: str
    createdAt: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class SettingsRequest(BaseModel):
    notifications: bool = True
    theme: str = "dark"
    telegram: str = ""


def read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_demo_user():
    users = read_json(USERS_FILE, [])
    if not any(user.get("email") == LOGIN_DEMO_EMAIL for user in users):
        users.append(
            {
                "name": "Demo User",
                "email": LOGIN_DEMO_EMAIL,
                "password": LOGIN_DEMO_PASSWORD,
                "plan": "Pro",
            }
        )
        write_json(USERS_FILE, users)


def create_token(email: str) -> str:
    return f"sl_{secrets.token_urlsafe(24)}_{email}"


def get_email_from_token(token: str) -> str:
    if not token or not token.startswith("sl_") or "_" not in token[3:]:
        raise HTTPException(status_code=401, detail="Invalid token")
    parts = token.rsplit("_", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=401, detail="Invalid token")
    email = parts[1]
    if "@" not in email:
        raise HTTPException(status_code=401, detail="Invalid token")
    return email


def get_bearer_token(authorization: Optional[str]) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization scheme")
    return authorization.split(" ", 1)[1].strip()


def get_current_user(authorization: Optional[str]) -> dict:
    token = get_bearer_token(authorization)
    email = get_email_from_token(token)
    users = read_json(USERS_FILE, [])
    user = next((u for u in users if u.get("email") == email), None)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


ensure_demo_user()


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/api/leads")
async def create_lead(payload: LeadRequest):
    leads = read_json(LEADS_FILE, [])
    lead = {
        "id": secrets.token_hex(8),
        "channelUrl": payload.channelUrl,
        "createdAt": payload.createdAt,
        "status": "new",
    }
    leads.insert(0, lead)
    write_json(LEADS_FILE, leads)
    return {
        "ok": True,
        "message": "Lead received",
        "lead": lead,
    }


@app.get("/api/leads")
async def list_leads(authorization: Optional[str] = Header(default=None)):
    _ = get_current_user(authorization)
    leads = read_json(LEADS_FILE, [])
    return {"ok": True, "items": leads}


@app.post("/api/auth/register")
async def register(payload: RegisterRequest):
    users = read_json(USERS_FILE, [])

    if any(user.get("email") == payload.email for user in users):
        raise HTTPException(status_code=409, detail="Email already exists")

    user = {
        "name": payload.name.strip() or "User",
        "email": payload.email,
        "password": payload.password,
        "plan": "Starter",
    }
    users.append(user)
    write_json(USERS_FILE, users)

    access_token = create_token(payload.email)
    return {
        "ok": True,
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "email": user["email"],
            "plan": user["plan"],
            "name": user["name"],
        },
    }


@app.post("/api/auth/login")
async def login(payload: LoginRequest):
    users = read_json(USERS_FILE, [])
    user = next(
        (
            user
            for user in users
            if user.get("email") == payload.email and user.get("password") == payload.password
        ),
        None,
    )

    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    access_token = create_token(payload.email)
    return {
        "ok": True,
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "email": user["email"],
            "plan": user.get("plan", "Starter"),
            "name": user.get("name", "User"),
        },
    }


@app.get("/api/profile")
async def profile(authorization: Optional[str] = Header(default=None)):
    user = get_current_user(authorization)
    return {
        "ok": True,
        "user": {
            "email": user["email"],
            "plan": user.get("plan", "Starter"),
            "name": user.get("name", "User"),
        },
    }


@app.get("/api/settings")
async def get_settings(authorization: Optional[str] = Header(default=None)):
    user = get_current_user(authorization)
    settings = read_json(SETTINGS_FILE, {})
    user_settings = settings.get(
        user["email"],
        {
            "notifications": True,
            "theme": "dark",
            "telegram": "",
        },
    )
    return {"ok": True, "settings": user_settings}


@app.post("/api/settings")
async def save_settings(payload: SettingsRequest, authorization: Optional[str] = Header(default=None)):
    user = get_current_user(authorization)
    settings = read_json(SETTINGS_FILE, {})
    settings[user["email"]] = payload.model_dump()
    write_json(SETTINGS_FILE, settings)
    return {"ok": True, "settings": settings[user["email"]]}


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

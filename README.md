# StreamLogic Backend

## Endpoints
- `GET /health`
- `POST /api/leads`
- `POST /api/auth/login`
- `GET /api/dashboard/preview`
- `GET /auth/twitch`
- `GET /auth/twitch/callback`

## Deploy on Render
1. Create a new Web Service from this repo/folder.
2. Render will use `render.yaml`.
3. Add environment variables from `.env.example`.
4. After deploy, copy your backend URL.

## Connect frontend
In your `index.html`, set:
- `FORM_ENDPOINT`
- `LOGIN_ENDPOINT`
- `TWITCH_AUTH_URL`
- `DASHBOARD_ENDPOINT`

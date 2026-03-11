# Hockey Blast Predictions 🏒

Pick-em predictions game layered on top of [hockey-blast.com](https://hockey-blast.com).
Players predict game outcomes, earn points for upsets and bold picks, and compete on private league leaderboards.

---

## Quick Start

### 1. Clone and set up Python environment

```bash
git clone https://github.com/foxyclaw/hockey-blast-predictions
cd hockey-blast-predictions

python3.11 -m venv .venv
source .venv/bin/activate

pip install -r requirements-dev.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your actual values (see Environment Variables section)
```

### 3. Create the predictions database

```bash
# Connect to your Postgres instance
psql -h 192.168.86.83 -U foxyclaw -c "CREATE DATABASE hockey_blast_predictions;"
```

### 4. Run Alembic migrations

```bash
alembic upgrade head
```

### 5. Start the dev server

```bash
flask --app wsgi run --debug
```

Server runs at `http://localhost:5000`

### 6. Verify health

```bash
curl http://localhost:5000/api/health
# {"service": "hockey-blast-predictions", "status": "ok"}

curl http://localhost:5000/api/health/db
# {"hb_db": "ok", "pred_db": "ok", "status": "ok"}
```

---

## Environment Variables

All variables go in `.env` (copy from `.env.example`).

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | ✅ | Flask session secret — use a long random string in prod |
| `HB_DATABASE_URL` | ✅ | Read-only connection to `hockey_blast` Postgres DB |
| `PRED_DATABASE_URL` | ✅ | Read-write connection to `hockey_blast_predictions` DB |
| `AUTH0_DOMAIN` | ✅ | Your Auth0 tenant domain (e.g. `your-app.us.auth0.com`) |
| `AUTH0_CLIENT_ID` | ✅ | Auth0 application Client ID |
| `AUTH0_CLIENT_SECRET` | ✅ | Auth0 application Client Secret |
| `AUTH0_AUDIENCE` | ✅ | Auth0 API identifier (e.g. `https://predictions.hockey-blast.com/api`) |
| `AUTH0_CALLBACK_URL` | ✅ | OAuth callback URL (e.g. `http://localhost:5000/auth/callback`) |
| `FLASK_ENV` | ✅ | `development` \| `production` \| `testing` |
| `PICK_LOCK_BUFFER_MINUTES` | ❌ | Minutes before game start that picks lock (default: `0`) |
| `GRADER_INTERVAL_MINUTES` | ❌ | How often the background grader runs (default: `5`) |

---

## Auth0 Setup (Pasha's TODO)

1. Create an Auth0 account at [auth0.com](https://auth0.com) (free tier is fine for development)
2. Create a new **Regular Web Application** (not SPA — we handle the server side)
3. In Application settings:
   - **Allowed Callback URLs**: `http://localhost:5000/auth/callback`
   - **Allowed Logout URLs**: `http://localhost:5000`
   - **Allowed Web Origins**: `http://localhost:5000`
4. Create a new **API** with identifier `https://predictions.hockey-blast.com/api`
5. Copy Client ID, Client Secret, and Domain into your `.env`

---

## API Reference

### Health
```
GET  /api/health         — liveness probe
GET  /api/health/db      — readiness probe (checks both DBs)
```

### Auth
```
GET  /auth/login         — redirect to Auth0
GET  /auth/callback      — OAuth callback (Auth0 → app)
GET  /auth/logout        — clear session + redirect to Auth0 logout
GET  /auth/me            — current user info (requires JWT)
```

All API endpoints require a JWT Bearer token in the Authorization header:
```
Authorization: Bearer <access_token>
```

### Games
```
GET  /api/games                    — list upcoming pickable games
     ?org_id=1&division_id=5       — filter by org or division
     ?from_date=2026-03-15         — date range (ISO format)
     ?to_date=2026-03-22
     ?page=1&per_page=20           — pagination

GET  /api/games/<game_id>          — single game detail + your pick
```

### Picks
```
POST   /api/picks                  — submit or update a pick
DELETE /api/picks/<pick_id>        — retract a pick (before lock)
GET    /api/picks/mine             — your picks
       ?league_id=7                — filter by league
       ?status=pending|graded|all  — filter by grade status
GET    /api/picks/<pick_id>        — single pick detail
```

**Submit pick request body:**
```json
{
  "game_id": 123456,
  "league_id": 7,
  "picked_team_id": 11,
  "confidence": 3
}
```

### Leagues
```
POST /api/leagues                  — create a league
POST /api/leagues/join             — join via join code
GET  /api/leagues/<id>             — league detail
GET  /api/leagues/<id>/members     — member list
GET  /api/leagues/<id>/picks?game_id=123  — all picks for a game
```

### Standings
```
GET  /api/standings/<league_id>    — full leaderboard
```

---

## Scoring System

| Scenario | Points |
|---|---|
| Correct pick, 1x confidence | 10 |
| Correct pick, 2x confidence | 20 |
| Correct pick, 3x confidence | 30 |
| Correct upset (+25 skill diff), 1x | 22 |
| Correct upset (+25 skill diff), 3x | **66** |
| Wrong pick (any) | 0 |
| Forfeit/canceled game | 0 (not counted in accuracy) |

**Upset bonus:** `floor(skill_differential × 0.5)` where `skill_differential = picked_team_avg_skill - opponent_avg_skill`. Higher skill value = weaker team, so positive diff = you picked the underdog.

---

## Project Structure

```
app/
  __init__.py          Flask app factory
  config.py            Dev/prod/test config classes
  db.py                Dual DB sessions (HBSession + PredSession)
  auth/                Auth0 OAuth routes + JWT decorator
  models/              SQLAlchemy models (pred_*)
  blueprints/          API route handlers
  services/            Business logic
  jobs/                APScheduler background jobs
  utils/               Shared helpers
migrations/            Alembic migration scripts
tests/                 pytest tests
wsgi.py                Gunicorn entry point
```

---

## Running Tests

```bash
pytest tests/unit/ -v          # Fast unit tests (no DB required)
pytest tests/ -v               # All tests
```

---

## Migrations

```bash
# Check current revision
alembic current

# Apply all pending migrations
alembic upgrade head

# Generate a new migration (after model changes)
alembic revision --autogenerate -m "add_my_column"

# Roll back one step
alembic downgrade -1
```

---

## Production Deployment

```bash
# Install production dependencies only
pip install -r requirements.txt

# Run with Gunicorn
gunicorn --bind 0.0.0.0:5000 --workers 4 wsgi:app

# Or with uvicorn (if using ASGI)
# Not configured yet — Flask is WSGI
```

---

## What Pasha Needs to Do Before Running

1. ✅ **Create Auth0 account** — see [Auth0 Setup](#auth0-setup-pashas-todo) above
2. ✅ **Create predictions DB** — `CREATE DATABASE hockey_blast_predictions;`
3. ✅ **Copy `.env.example` → `.env`** and fill in all values
4. ✅ **Run `alembic upgrade head`** to create tables
5. ✅ **Install `hockey_blast_common_lib`** — `pip install` from wherever it's hosted
   - Update `requirements.txt` with the correct install path once known
6. ✅ **Verify `/api/health/db`** returns `ok` for both databases

---

## Open Questions (from DESIGN.md)

See `DESIGN.md` section 10 for the full list of open questions that need answers before launch.
Key decisions needed:
- Frontend tech: React SPA vs Jinja2+HTMX?
- `hockey_blast_common_lib` pip install path?
- Exact field names on the `Game` model?
- Forfeit handling preference?
- Negative points for wrong picks?

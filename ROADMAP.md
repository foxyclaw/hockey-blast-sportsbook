# Hockey Blast Predictions — Roadmap

_Last updated: 2026-03-11 by FoxyClaw_

---

## ✅ Done (Phase 1 + 2)

- Flask app skeleton — blueprints, models, Alembic migrations
- Dual DB sessions (hockey_blast read-only, hockey_blast_predictions read-write)
- Auth0 Google SSO — working end-to-end
- `/api/games` — real upcoming games with team names + skill ratings
- `/api/leagues` — create leagues with join codes
- `/api/picks` — submit/update/retract picks, projected points, upset bonus
- `/api/standings` — league leaderboard
- E2E test script — 20/20 passing

---

## 🔜 In Progress / Next

### Frontend
Research first — don't build something ugly. Options to evaluate:
- **HTMX + Jinja2** — stays in Flask, no build step, good for server-rendered
- **React (Vite)** — SPA, clean separation, good for real-time
- **Vue 3 (Vite)** — lighter than React, good DX
- **Svelte/SvelteKit** — small bundle, reactive, fun to work with
- Key considerations: how to integrate with Auth0, mobile-responsive, no ugly tables

### Paper Money (Virtual Currency)
- Give each new user a starting balance (e.g. 1000 "pucks" or "$" or "chips")
- Track balance in `pred_users` table (new column: `balance`, default 1000)
- When submitting a pick, optionally wager an amount (within balance)
- Win: balance += wager * multiplier; Lose: balance -= wager
- Multiplier = f(confidence, upset bonus)
- Leaderboard shows both points AND balance
- No real money ever — just bragging rights
- **TODO:** design wager flow — does it replace confidence multiplier or stack with it?

### Player Identity Linking (IMPORTANT)
When a user logs in for the first time (new PredUser), prompt them to find themselves in the hockey DB:

1. Parse their real name from Auth0 profile (first + last)
2. Query `humans` table in hockey_blast for fuzzy name match
3. Show top 3-5 matches with: name, org(s) they play in, last game date, skill level
4. User picks which one is them (or "none of these")
5. Save `hb_human_id` in `pred_users`

**Why it matters:**
- Personalization at hockey-blast.com — "Your stats this season..."
- Captain tools: manage game rosters, send "looking for sub" alerts
- Sub finder: system knows your position (skater/goalie), level, org
- Team building from scratch: find players by level/position/org
- Future: cross-site SSO — same identity on predictions + hockey-blast.com

**DB query needed:**
```sql
SELECT id, first_name, last_name, skater_skill_value 
FROM humans 
WHERE first_name ILIKE '%{first}%' AND last_name ILIKE '%{last}%'
ORDER BY last_date DESC
LIMIT 10;
```

**New endpoint needed:** `POST /api/auth/link-identity`
```json
{ "hb_human_id": 12345 }
```

**New endpoint:** `GET /api/auth/identity-candidates?name=Pavel+K`

### ⚠️ Player Identity — Multi-Record Problem (FUTURE TASK — DO NOT RUSH)

**Context from Pasha (2026-03-11):**
Hockey players often have **multiple records** in `humans` table representing the same real person. Root causes:
1. Yearly USAH (USA Hockey) membership — name variations between seasons
2. Some facilities don't require USAH registration — creates duplicate humans with slight name diffs
3. Name variations: "Pavel" vs "Paul", "Kletskov" vs "Kletskov-Smith", etc.

**hockey_blast already has:**
- `human_aliases` table — links multiple human records to one canonical identity
- A player merge function — merges stats, aliases, etc. across records
- V0 auto-linking logic exists but needs reimplementation

**Key constraint:** Easy to link, very hard to unlink. Merging player identities is irreversible in practice.

**Revised approach (2026-03-11, Pasha):** Just collect. Don't merge. Let users claim as many `hb_human_id`s as they recognize as themselves — store all of them in OUR DB. Merging/deduplication happens later in a nightly stats job on the hockey_blast side, not here.

**Implementation:**
- `pred_user_hb_claims` table: `(id, user_id, hb_human_id, claimed_at, source)`
  - `source`: 'self_reported' | 'email_match' | 'admin'
  - Multiple rows allowed per user
  - No uniqueness constraint on `hb_human_id` — two users CAN claim the same record (conflict flagged, resolved later)
- Keep `pred_users.hb_human_id` as "primary" claim for quick lookups (the one they picked first or confirmed as primary)
- When displaying player stats: union across ALL claimed `hb_human_id`s
- No writes to `hockey_blast` DB ever from this app

**Nightly job (future):**
- Read all `pred_user_hb_claims`
- Feed into hockey_blast merge/alias logic
- Flag conflicts (same `hb_human_id` claimed by >1 user) for manual review

**What NOT to implement now:**
- Any merging of human records
- Conflict resolution UI
- Anything that writes to `hockey_blast` DB

### Token Limit / Credit Warning Skill
- OpenClaw exposes session token usage via `session_status` tool
- Need a skill that checks usage and warns Pasha when approaching limits
- Before ending a session, auto-save state to `memory/YYYY-MM-DD.md` + `MEMORY.md`
- Trigger: heartbeat or explicit `/status` check

---

## 📋 Backlog

- Grader job: auto-grade picks when games go Final
- Result grader: connect to real game outcomes from hockey_blast DB
- Season management: define a "season" for the prediction league
- Push notifications: Telegram alerts when picks grade
- Sub/goalie finder: post "need sub tonight at 9pm" → system finds available players
- Captain tools: manage game rosters, track who's playing
- Team builder: "find 15 players for a new team at Sharks Ice, Div C level"
- Public leaderboards
- Commissioner tools: manage league, override results

---

## 🔑 Key Decisions Open

1. Frontend framework choice (research pending)
2. Paper money flow design (replace or stack with confidence?)
3. Player identity: multi-record problem — see detailed notes above. Phase 1 = single hb_human_id only. Phase 2 = aliases table + merge review (after Pasha sets up proper process in personal repos)
4. Wager amounts: fixed tiers or free-form input?
5. Where to host once happy with local testing (Mac Studio? Heroku? Fly.io?)

---

## 🔧 Infrastructure

- **DB (dev):** Mac mini, postgres@17, `hockey_blast_predictions`
- **DB (source):** Mac Studio 192.168.86.83, `hockey_blast` (read-only)
- **Auth0:** `dev-tqe4zxubkkg82828.us.auth0.com`, app: HockeyBlasting
- **Repo:** https://github.com/foxyclaw/hockey-blast-predictions
- **Skill:** `skater_skill_value` on `humans` table (0=elite, 100=worst)

# Work In Progress — Player Preferences Feature
_Written 2026-03-17 by FoxyClaw to survive context loss_

## Status
Sub-agent is currently building this. If it fails or disconnects, resume from here.

---

## What was done TODAY (before this feature)

All in `hockey-blast-predictions` repo, committed to `main`:

### Bug fixes committed (3 commits):
1. `fix: use visitor_team instead of away_team in PickModal` — PickModal.vue used `game.away_team` but API returns `game.visitor_team`
2. `fix: resolve away_team/visitor_team mismatch across frontend and enrich picks API` — PicksView.vue had multiple wrong field refs; picks.py now returns `home_team_name`, `away_team_name`, `picked_team_name`, `status`, `points_earned`
3. `fix: 7 API/frontend field name mismatches` — Full audit found:
   - `game.division` missing from API → added to `_serialize_game()`
   - `entry.display_name` in StandingsView should be `entry.user.display_name` → promoted flat
   - `entry.balance` missing from standings API → added via PredUser join
   - `league.season_label` didn't exist → added column + migration `a1b2c3d4e5f6`
   - POST `/api/leagues` returned `league_id` not `id` → fixed to return `league.to_dict()`
   - POST `/api/leagues/join` returned bare message → fixed to return `league.to_dict()`
   - `picks.js` store called `/api/picks` → fixed to `/api/picks/mine`

---

## Feature: Player Preferences (currently being built)

### Goal
Single-screen onboarding form + persistent settings page asking users:
1. Skill level (elite/advanced/intermediate/recreational/beginner)
2. Locations they're interested in playing
3. Free agent (want to join a team permanently)
4. Sub availability (willing to sub occasionally)
5. Captain claims (if HB data shows they were captain, let them claim it)
6. Notification preferences (email toggle + optional phone for SMS)

### DB Changes

#### New table: `pred_user_preferences`
```
id, user_id (FK pred_users unique), skill_level (String20),
is_free_agent (bool), wants_to_sub (bool),
notify_email (bool default true), notify_phone (String20 nullable),
interested_location_ids (JSON list of ints),
created_at, updated_at
```
File: `app/models/pred_user_preferences.py`

#### New table: `pred_user_captain_claims`
```
id, user_id (FK pred_users), team_id (int HB), team_name (String128),
org_name (String128 nullable), is_active (bool),
claimed_at, UNIQUE(user_id, team_id)
```
File: `app/models/pred_user_captain_claim.py`

#### Modify `pred_users`:
- Add `preferences_completed` (bool, default false, server_default false)
- Add relationships to preferences + captain_claims

#### Migration
File: `migrations/versions/b2c3d4e5f6a7_add_player_preferences.py`
- down_revision = `a1b2c3d4e5f6` (season_label migration)

---

### Backend

#### New blueprint: `app/blueprints/preferences.py`
- `GET /api/preferences` — returns:
  ```json
  {
    "preferences": { skill_level, is_free_agent, wants_to_sub, notify_email, notify_phone, interested_location_ids },
    "suggested_skill_level": "intermediate",  // from primary HB claim skill_value
    "captain_candidates": [ { team_id, team_name, org_name, already_claimed } ],
    "locations": [ { id, name } ],  // HB master locations (master_location_id IS NULL)
    "active_captain_claims": [ ... ]
  }
  ```
- `PATCH /api/preferences` — upserts prefs, handles captain claims, sets preferences_completed=True

**Skill level mapping** (from `profile_snapshot.skill_value`, 0=elite 100=worst):
- ≤ 20 → 'elite'
- ≤ 40 → 'advanced'
- ≤ 60 → 'intermediate'
- ≤ 80 → 'recreational'
- > 80 → 'beginner'

**Captain candidates** — from all user's `PredUserHbClaim.profile_snapshot["teams"]` where `is_captain==True`, deduplicated by team_id

**Locations** — HB `Location` where `master_location_id IS NULL AND location_name IS NOT NULL`, ordered by location_name

#### Register in `app/__init__.py`
Follow same pattern as other blueprints, url_prefix='/api/preferences'

#### Update `app/auth/routes.py` GET /auth/me
Add `"preferences_completed": user.preferences_completed` to response

---

### Frontend

#### `frontend/src/stores/user.js`
Add:
```js
const needsPrefsSetup = computed(
  () => predUser.value !== null && !needsNameSetup.value && predUser.value.preferences_completed === false
)
```
Export it.

#### `frontend/src/App.vue`
Add step 3 after needsIdentitySetup block:
```js
} else if (userStore.needsPrefsSetup) {
  const current = router.currentRoute.value.name
  if (current !== 'player-prefs' && current !== 'callback' && current !== 'identity') {
    router.push({ name: 'player-prefs' })
  }
}
```

#### `frontend/src/views/IdentityView.vue`
`confirm()` and `skip()` → redirect to `/player-prefs` instead of `/`

#### New view: `frontend/src/views/PlayerPrefsView.vue`
Single screen, DaisyUI, max-w-2xl.

**Section 1 — Skill Level**
5 radio cards: Elite 🌟 / Advanced ⚡ / Intermediate 🏒 / Recreational 🎿 / Beginner 🐣
Short taglines. Selected = border-primary bg-primary/10.
Show "💡 Suggested" badge on suggested_skill_level card.
Auto-select suggested if no saved pref.

**Section 2 — Locations**
Toggle chips. Selected = bg-primary text-primary-content, unselected = badge-outline.

**Section 3 — Availability**
Two toggle cards: "🏒 Join a Team" (is_free_agent) and "📋 Sub Occasionally" (wants_to_sub).

**Section 4 — Captain Claims** (only if candidates exist)
Checkbox cards per team. Pre-check already_claimed ones.

**Section 5 — Notifications**
- Email toggle (notify_email, default true)
- "Text me" toggle → shows phone input when on
- Disclaimer: "We only contact you about what you've selected above."

**Bottom**: "Save Profile" btn-primary, "Skip for now" btn-ghost

**Script**:
- onMounted: GET /api/preferences, prefill, auto-select suggested skill
- save(): PATCH /api/preferences; on success: userStore.predUser.preferences_completed = true; router.push('/')
- skip(): router.push('/')

#### `frontend/src/router/index.js`
Add: `{ path: '/player-prefs', name: 'player-prefs', component: () => import('@/views/PlayerPrefsView.vue'), beforeEnter: authGuard }`

#### `frontend/src/components/NavBar.vue`
Add `<li><RouterLink to="/player-prefs">Player Profile</RouterLink></li>` in dropdown (above Hockey Identity)

---

### Onboarding Flow (after this feature)
1. Sign in → if no display_name → `/profile-setup` (name entry)
2. Has name → if no hb_human_id → `/identity` (link hockey profile)
3. Has identity → if preferences_completed=false → `/player-prefs`
4. Done → `/` (games home)

---

## Hockey-blast-frontend (separate project)

Running on port 5001 with auto-restart wrapper. Currently healthy.
The away team name bug in the pick modal was a different project (hockey-blast-predictions).

---

## Repos in workspace
- `hockey-blast-predictions` — Flask API + Vue 3 frontend (picks app) — active work today
- `hockey-blast-frontend` — Flask + Jinja templates (main HB site) — port 5001
- `hockey-blast-common-lib` — shared SQLAlchemy models
- `hockey-blast-mcp` — MCP server

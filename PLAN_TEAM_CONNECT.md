# Team Connect — Feature Plan
_Saved 2026-03-18 by FoxyClaw_

## Vision
Connect players who need teams with teams who need players — for permanent roster spots AND one-off game subs. Captains manage game-day needs. Players get notified when opportunities match them.

---

## Core Scenarios

### 1. Player looking for a team (Free Agent)
- Player marks themselves as free agent in Player Profile (already built ✅)
- Selects skill level and locations (already built ✅)
- Appears in searchable free agent pool for captains
- Gets notified when a captain reaches out

### 2. Player willing to sub
- Player marks "Sub Occasionally" in Player Profile (already built ✅)
- Gets notified when a game-day sub request matches their location/level
- Can accept or decline from the notification

### 3. Captain finding a sub for a specific game
- Captain sees upcoming game → menu: "Find Goalie" / "Find Skaters (N)"
- System broadcasts to matching subs (location + level)
- Subs get SMS/email notification
- Subs can respond (accept/decline)
- Captain picks from respondents, closes the spot
- Everyone notified of outcome

### 4. Captain building/expanding roster
- On team view → "Add to Roster" → shows matching free agents
- Captain sends invite → player gets notified, accepts/declines
- Closed loop: player moves from free agent pool to roster

### 5. Someone building a new team (stub team)
- Create stub team in our DB (NOT hockey_blast DB)
- Enter name, level preference, rink preference
- Request free agents → they get notified
- Invite specific players by name/email → they accept/decline
- Team stub lives until it gets real games (then maps to HB team if possible)

---

## Notification System

### Options explored (free/cheap SMS):
- **Twilio** — $0.0079/SMS, ~$8/1000 msgs, free trial $15 credit. Best reliability.
- **AWS SNS** — $0.00645/SMS. Already using AWS Bedrock. Easy to add.
- **Textbelt** — 1 free/day, $0.01/SMS paid. Simple REST API.
- **Vonage (Nexmo)** — $0.0065/SMS, free trial.

**Recommendation: AWS SNS** — we already use AWS (Bedrock), no new accounts, same billing.

### Notification channels:
1. **SMS** (via AWS SNS) — for time-sensitive (sub requests, game-day)
2. **Email** — for non-urgent (roster invites, weekly digest)
3. **In-app** — notification bell in nav (always)

### What triggers notifications:
| Event | Who gets notified | Channel |
|-------|-------------------|---------|
| Sub request created | All matching subs (location + level) | SMS + in-app |
| Captain selects a sub | Selected sub | SMS |
| Sub spot filled | All other respondents | SMS |
| Roster invite sent | Invitee | Email + in-app |
| Free agent interest | Captain | In-app |
| New team looking for players | Matching free agents | Email |

---

## DB Schema (new tables in pred DB)

### `team_stubs` — teams not yet in HB DB
```
id, creator_user_id, name, level_preference, location_ids (JSON),
status (recruiting/active/inactive), created_at
```

### `team_connections` — maps stub teams to HB teams (when matched)
```
stub_team_id, hb_team_id, confirmed_at
```

### `sub_requests` — game-day sub requests
```
id, game_id, hb_team_id, captain_user_id,
positions_needed (JSON: {goalies: 1, skaters: 2}),
message, status (open/filled/cancelled),
deadline (when sub must confirm by), created_at
```

### `sub_responses` — players responding to sub requests
```
id, request_id, user_id, status (interested/confirmed/declined),
responded_at, confirmed_at
```

### `roster_invites` — captain inviting free agents to team
```
id, from_user_id, to_user_id, hb_team_id (or stub_team_id),
message, status (pending/accepted/declined), created_at
```

### `notifications` — in-app notification log
```
id, user_id, type, title, body, link, is_read, created_at
```

---

## UI Changes

### Picks App (hockey-blast-predictions)

#### Game Card — Captain Menu
When captain is logged in and game is for their team:
```
[Rebel Scum 1 vs Avengers]  [⚙️ Captain Menu ▼]
                              ├ 📋 Find Goalie
                              ├ 🏒 Find Skaters (2)
                              └ 🚫 Forfeit Game
```

#### Team View (new page `/teams/:id`)
- Team roster
- Captain controls: "Manage Roster" → shows free agent matches, send invites

#### Free Agents Page (new `/free-agents`)
- Public list of available players (location + level filters)
- Captain can reach out
- Player can manage their visibility

#### New Team Builder (new `/new-team`)
- Form: team name, level, locations
- After creating stub: shows matching free agents
- Invite flow

### NavBar additions:
- "🏒 Free Agents" (visible to all)
- Captain-specific links appear after identity claimed with captain role

---

## Implementation Order

### Phase 1 (do now — no breaking changes)
1. DB migrations for new tables
2. `notifications` table + in-app bell in NavBar
3. Free agent listing endpoint + `/free-agents` page (read-only first)
4. Sub request model + captain menu on game cards (just the UI stub)

### Phase 2 (next)
5. AWS SNS integration for SMS
6. Sub request flow end-to-end (create → notify → respond → confirm)
7. Roster invite flow

### Phase 3 (later)
8. Stub team builder
9. Team view with captain management tools
10. Free agent → roster pipeline

---

## Notes
- All communication goes through the platform — no direct phone sharing until captain confirms a sub
- Players control their visibility (can turn off free agent / sub flags anytime — already in Player Profile)
- Captain identity is already established via `pred_user_captain_claims`
- "Forfeit game" — just a captain action, probably just sends a message to the league (out of scope for now)
- Keep it simple: connect people, don't over-manage. The platform facilitates intro, humans handle the rest.

---

## Fees (added 2026-03-18)

### Sub fee (per game)
- `sub_fee` (integer, cents or points) on `pred_sub_requests` — can be 0
- Shown to subs before they respond: "💰 Sub fee: $15" or "Free"
- Captain sets it when creating the request

### Roster fee (joining a team)
- `roster_fee_half` and `roster_fee_full` (integer, cents) on `pred_team_stubs` and roster invites
- Half-time player (partial season) vs full-time
- Shown on invite: "Full season: $350 | Half season: $200"
- Captains fill this in when inviting or when creating stub team
- Fee info is informational only for now (no payment processing) — just transparency

### UI
- Sub request card shows fee badge: `💰 $15/game` or `🆓 Free`
- Roster invite shows: `📋 Full: $350 · Half: $200`
- Free agents can filter by "Free subs only"

### DB changes needed (on top of Phase 1 plan)
- Add `sub_fee INTEGER DEFAULT 0` to `pred_sub_requests`
- Add `roster_fee_full INTEGER DEFAULT 0` and `roster_fee_half INTEGER DEFAULT 0` to `pred_roster_invites` and `pred_team_stubs`

---

## Quick Interest (added 2026-03-18)

### One-click "I'm interested" on sub requests and free agent posts
- Sub request card: big **[🙋 I'm In]** button — single tap, no form
- Free agent browsing (captain view): **[👋 Reach Out]** next to each player — single tap sends a notification to that player
- Both actions can be undone (toggle back to "Not interested")
- No modal, no form — friction-free. Details (fee, game info) already visible on the card.

### Flow:
1. Sub sees request → taps [🙋 I'm In] → captain gets notification → captain confirms or passes
2. Captain sees free agent → taps [👋 Reach Out] → player gets notification + can view captain's team profile → player accepts/declines

### "I'm In" button states:
- Grey: not responded
- Green + checkmark: interested (tap again to withdraw)
- Faded: request filled by someone else


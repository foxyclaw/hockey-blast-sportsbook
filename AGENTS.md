
## Auth Rules

**No auth = read-only observation only.**

Any action that results in a state change MUST require authentication:
- Creating a league — require_auth
- Joining a league — require_auth
- Making a pick — require_auth
- Any POST/PATCH/DELETE — require_auth

Read-only GET endpoints (browse leagues, view games, see standings) may be public.

Frontend rule: before any state-changing action, check isAuthenticated. If not logged in, call loginWithRedirect() immediately — never show a misleading error when the real issue is missing auth.


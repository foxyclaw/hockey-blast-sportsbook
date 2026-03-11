# Hockey Blast Predictions — Frontend Research & Recommendation

_Written by FoxyClaw · 2026-03-11_

---

## TL;DR — My Pick

**Vue 3 + Vite + DaisyUI (via Tailwind CSS)**

Best balance of: fast to ship, looks great on mobile, Auth0 first-class support, solo-dev friendly. Not the trendiest choice, but the pragmatic one.

Runner-up if you want to bet on the future: **SvelteKit + Skeleton UI**

---

## Context: What the App Actually Needs

Before evaluating frameworks, here's what the frontend has to do:

- **Auth0 SSO** — login/logout with JWT, protect routes
- **Game Browser** — paginated list, filterable by org/division/date
- **Pick Widget** — pick a team, choose confidence, see projected points
- **Countdown Timers** — client-side, per game card, showing time until lock
- **Leaderboard** — standings table that refreshes periodically
- **Mobile-first** — most users will be checking from their phones between shifts
- **No dedicated frontend dev** — Pasha is building this solo

The backend is already **API-first JSON** (`/api/games`, `/api/picks`, etc.). Jinja2 templates would fight this architecture. This is a SPA.

---

## Option 1: HTMX + Jinja2

### What it is
Server-renders HTML via Flask/Jinja2 templates. HTMX adds "interactive" behavior with `hx-get`, `hx-post` attributes — no JavaScript build step.

### Auth0 integration
**Painful.** The app already uses JWT-based auth (Auth0 OIDC → token in cookie/session). HTMX assumes you're hitting Flask routes that return HTML fragments, not JSON. You'd need to add a parallel layer of HTML-returning Flask endpoints alongside the existing JSON API, or tear up the auth layer to use server-side sessions instead of JWT. The work already done (JWT validation, `@require_auth` decorator) assumes a SPA client that sends bearer tokens.

### Mobile responsiveness
HTMX doesn't give you anything. You'd use Bootstrap 5 or Bulma for components. Bootstrap looks fine but dated. Bulma is clean but you're still writing a lot of custom CSS.

### Real-time updates
HTMX has `hx-trigger="every 5s"` for polling. Countdown timers require custom JavaScript anyway (Alpine.js or vanilla). Not terrible, but you're bolting on JS that HTMX was supposed to replace.

### Development speed
Fast to get a first working page, slow to add complexity. Once you need client-side state (showing a projected points preview before submitting), you're writing Alpine.js or vanilla JS anyway.

### Bundle size / hosting
No build step, just Flask. Simplest possible hosting. But you lose hot module replacement and all modern frontend tooling.

### Verdict
**Skip it.** The app is already API-first. HTMX requires rebuilding the server response layer to serve HTML fragments. You'd be working against the architecture you already have. Good choice for a CRUD admin panel; wrong choice here.

---

## Option 2: React + Vite

### What it is
The industry default SPA. JSX, hooks, tons of ecosystem. Vite gives you sub-second HMR.

### Auth0 integration
⭐ **Best in class.** `@auth0/auth0-react` is maintained directly by Auth0. Wraps the whole app in a provider, gives you `useAuth0()` hook with `loginWithRedirect()`, `logout()`, `getAccessTokenSilently()`. First-class PKCE + refresh token rotation. Tons of documentation and examples for Flask backends specifically.

```jsx
const { loginWithRedirect, getAccessTokenSilently, user } = useAuth0();
const token = await getAccessTokenSilently();
// Pass token as Bearer in API calls
```

### Mobile responsiveness
Excellent options:
- **shadcn/ui** — genuinely beautiful, composable components, Tailwind-based. Requires some setup per component but looks premium.
- **Radix UI** — headless, you style everything with Tailwind
- **Mantine** — batteries-included, great mobile defaults, built-in dark mode
- **Ant Design** — enterprise-y, good mobile support, slightly heavy

Best-looking out of the box: **Mantine** or **shadcn/ui**. Mantine wins for "solo dev who wants things to look good immediately."

### Real-time updates
`setInterval` + `fetch` for polling game status. Countdown timers: `date-fns` or custom hook. Works perfectly. No WebSockets needed for this app — polling every 30s is fine for game status.

### Development speed
Slower startup than Vue/Svelte. You'll fight TypeScript config, need to understand hooks properly, manage component state carefully. But once you're past the learning curve, React has the most Stack Overflow answers, the most component examples, and the widest ecosystem.

### Bundle size / hosting
Largest bundle of the SPA options, but Vite tree-shakes well. A typical React+Vite app ships ~150-250KB gzipped. Fine for this use case.

Deploy as a static build to Netlify/Vercel/S3 or serve from Flask via `send_from_directory`. Flask setup:
```python
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_spa(path):
    return send_from_directory('frontend/dist', 'index.html')
```

### Verdict
Solid choice if you're comfortable with React. The Auth0 SDK is the best, shadcn/ui looks amazing. But "doesn't require a full-time frontend dev" is borderline with React — it has real cognitive overhead. Not recommending this as the primary pick.

---

## Option 3: Vue 3 + Vite ⭐ RECOMMENDED

### What it is
Progressive framework with Composition API. Single-file components (`.vue` files) keep HTML, CSS, and logic together in a readable format. Less opinionated than React, gentler learning curve.

### Auth0 integration
⭐ **First-class.** `@auth0/auth0-vue` is officially maintained by Auth0. Works identically to the React SDK:

```js
import { createAuth0 } from '@auth0/auth0-vue'

app.use(createAuth0({
  domain: 'dev-tqe4zxubkkg82828.us.auth0.com',
  clientId: 'YOUR_CLIENT_ID',
  authorizationParams: {
    redirect_uri: window.location.origin,
    audience: 'https://hockey-blast-predictions/api'
  }
}))
```

```vue
<script setup>
import { useAuth0 } from '@auth0/auth0-vue'
const { loginWithRedirect, logout, user, getAccessTokenSilently } = useAuth0()
</script>
```

### Mobile responsiveness — why DaisyUI wins here

**DaisyUI** (built on Tailwind CSS) is the secret weapon for solo devs:

- 50+ pre-built components: cards, badges, buttons, modals, tables, tabs, drawers
- 30+ built-in themes (including hockey-appropriate dark themes)
- Looks genuinely good out of the box — not Bootstrap-generic, not Material-flat
- Mobile-first by default
- Zero JavaScript in DaisyUI itself (pure CSS) — add Vue reactivity on top
- Install in 2 minutes:

```bash
npm install -D daisyui tailwindcss
```

What the game card would look like:
```vue
<div class="card bg-base-100 shadow-xl">
  <div class="card-body">
    <div class="badge badge-warning">Locks in {{ timeLeft }}</div>
    <div class="flex justify-between items-center gap-4">
      <button class="btn btn-primary flex-1" @click="pick(homeTeam)">
        {{ homeTeam.name }}
        <span class="badge badge-outline">{{ homeTeam.avgSkill }}</span>
      </button>
      <span class="font-bold text-xl">vs</span>
      <button class="btn btn-secondary flex-1" @click="pick(awayTeam)">
        {{ awayTeam.name }}
        <span class="badge badge-outline">{{ awayTeam.avgSkill }}</span>
      </button>
    </div>
  </div>
</div>
```

That's it. That's a styled, mobile-responsive game card.

Other Vue component library options:
- **Quasar** — Material Design, excellent mobile, built-in PWA support, most "batteries included" of any Vue option. Great if you want a native app feel.
- **PrimeVue** — 90+ components, themeable, looks professional
- **Vuetify 3** — Material Design, massive ecosystem, solid but heavy
- **Naive UI** — TypeScript-first, clean design

**My pairing: Vue 3 + Tailwind CSS + DaisyUI.** Skip the heavy component framework. DaisyUI covers everything you need.

### Real-time updates
Vue's reactivity system is excellent for this. Countdown timer example:

```vue
<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const props = defineProps(['lockDeadline'])
const timeLeft = ref('')

let interval
onMounted(() => {
  interval = setInterval(() => {
    const diff = new Date(props.lockDeadline) - new Date()
    if (diff <= 0) { timeLeft.value = 'LOCKED'; return }
    const h = Math.floor(diff / 3600000)
    const m = Math.floor((diff % 3600000) / 60000)
    const s = Math.floor((diff % 60000) / 1000)
    timeLeft.value = `${h}h ${m}m ${s}s`
  }, 1000)
})
onUnmounted(() => clearInterval(interval))
</script>
```

For leaderboard updates: poll `/api/leagues/:id/standings` every 60 seconds with `setInterval`. No WebSockets needed.

### Development speed
Vue 3 Composition API is the most readable of the SPA options for someone who isn't a dedicated frontend dev:
- No "thinking in React" required (hooks rules, stale closures, effect dependencies)
- Single-file components keep everything together
- `v-if`, `v-for`, `v-model` are intuitive directives
- Vite HMR is instant
- Vue DevTools are excellent

Routing: Vue Router 4 (official, dead simple).
State: Pinia (official, much simpler than Redux/Zustand).

### Bundle size / hosting
Vue 3 + Vite ships ~60-100KB gzipped for a typical app. Smaller than React. Serve as a static build on Netlify/Vercel, or from Flask.

### Verdict
**This is the pick.** Vue 3 gives you SPA power without React's cognitive overhead. DaisyUI + Tailwind makes mobile UI fast to build and good-looking without a designer. The Auth0 SDK is first-class. You can ship an MVP frontend in a weekend and iterate from there.

---

## Option 4: Svelte / SvelteKit

### What it is
Compiler-based framework. No virtual DOM — Svelte compiles to vanilla JS. Smallest bundle size. SvelteKit is the full-stack meta-framework (like Next.js for Svelte).

### Auth0 integration
**Usable but manual.** Auth0 doesn't have an official Svelte SDK. You'd use `@auth0/auth0-spa-js` directly:

```js
import { createAuth0Client } from '@auth0/auth0-spa-js'

const auth0 = await createAuth0Client({
  domain: 'dev-tqe4zxubkkg82828.us.auth0.com',
  clientId: 'YOUR_CLIENT_ID'
})
```

Wrap it in a Svelte store. Works, but you're writing the integration yourself — no `useAuth0()` hook, no built-in route guards. Community packages exist (`svelte-auth0`, etc.) but aren't maintained by Auth0.

This is the main friction point. For this app with Auth0 already wired, the lack of an official SDK adds real setup cost.

### Mobile responsiveness
- **Skeleton UI** — built for Svelte, looks modern and sharp, Tailwind-based. Excellent.
- **DaisyUI** — works with Svelte too (it's just CSS + Tailwind)
- **shadcn-svelte** — port of shadcn/ui, growing fast

Skeleton UI is genuinely beautiful and would make this app look polished quickly.

### Real-time updates
Svelte's reactivity is the most elegant of all the options. Stores + `$:` reactive declarations make countdown timers and polling trivial.

### Development speed
Svelte syntax is the simplest to learn. Less boilerplate than React or Vue. If you've never used a frontend framework, Svelte has the lowest barrier.

### Bundle size / hosting
Smallest of the SPAs — often under 30KB gzipped. SvelteKit can do SSR if you ever want it, but not needed here. Deploy as a static SPA with `adapter-static`.

### Verdict
**Strong runner-up.** The only reason it's not the top pick is the Auth0 integration requiring manual setup. If you're comfortable wiring Auth0 yourself, Svelte + Skeleton UI would be a joy to work with and produce a beautiful result. File this under "do this for v2 or if you want to learn something fun."

---

## Comparison Matrix

| | HTMX + Jinja2 | React + Vite | **Vue 3 + Vite** | Svelte + Vite |
|---|---|---|---|---|
| Auth0 integration | ❌ Fights the architecture | ⭐ Best SDK | ⭐ Official SDK | ⚠️ Manual |
| Mobile UI out of the box | ⚠️ Bootstrap-generic | ✅ Mantine/shadcn | ✅ **DaisyUI** | ✅ Skeleton UI |
| Real-time countdowns | ⚠️ Needs Alpine.js | ✅ Easy | ✅ Easy | ⭐ Most elegant |
| Dev speed (solo) | ⚠️ Fights the API | ⚠️ High learning curve | ✅ **Sweet spot** | ✅ Easiest syntax |
| Bundle size | ✅ Tiny | ⚠️ ~200KB | ✅ ~80KB | ⭐ ~30KB |
| Hosting simplicity | ⭐ Just Flask | ✅ Static build | ✅ Static build | ✅ Static build |
| Community / examples | ✅ Flask-native | ⭐ Largest | ✅ Large | ⚠️ Smaller |
| Recommendation | ❌ Skip | ⚠️ If React-native | ⭐ **DO THIS** | ✅ Runner-up |

---

## CSS / Component Framework Pairings

| Framework | Best Pairing | Why |
|---|---|---|
| HTMX + Jinja2 | Bootstrap 5 or Bulma | No build step, simple CDN |
| React | **shadcn/ui + Tailwind** | Looks incredible, composable, not a component library (it's code you own) |
| React | Mantine | Most batteries-included, best mobile defaults out of the box |
| **Vue 3** | **DaisyUI + Tailwind** | 30+ themes, 50+ components, zero JS overhead, great mobile |
| Vue 3 | Quasar | Full framework + component lib in one, Material Design, PWA-ready |
| Vue 3 | PrimeVue | 90+ components, more enterprise-y |
| Svelte | **Skeleton UI** | Purpose-built for Svelte, modern design system |
| Svelte | DaisyUI | Also works great with Svelte (pure CSS) |

---

## Recommended Stack: The Full Picture

```
hockey-blast-predictions/
└── frontend/
    ├── src/
    │   ├── main.js           # Auth0 + Vue Router + Pinia setup
    │   ├── App.vue           # Root component
    │   ├── router/index.js   # Routes: /, /games, /leagues/:id, /join/:code
    │   ├── stores/
    │   │   ├── auth.js       # Pinia store wrapping Auth0
    │   │   └── picks.js      # Pick state management
    │   ├── components/
    │   │   ├── GameCard.vue      # The main pick widget
    │   │   ├── Countdown.vue     # Reusable timer component
    │   │   ├── PickConfidence.vue
    │   │   ├── Leaderboard.vue
    │   │   └── PointsPreview.vue # "If correct: 66 pts"
    │   ├── views/
    │   │   ├── Dashboard.vue
    │   │   ├── GameBrowser.vue
    │   │   ├── LeagueDetail.vue
    │   │   └── JoinLeague.vue
    │   └── api/
    │       └── client.js     # fetch wrapper that injects Auth0 token
    ├── index.html
    ├── vite.config.js        # proxy /api/* → Flask in dev
    └── package.json
```

**Packages to install:**
```bash
npm create vue@latest frontend  # Vue 3 + Vite + TypeScript (optional) + Vue Router + Pinia
cd frontend
npm install @auth0/auth0-vue tailwindcss daisyui
npm install -D @tailwindcss/vite
```

**Vite dev proxy** (so `/api/picks` hits Flask during development):
```js
// vite.config.js
export default {
  server: {
    proxy: {
      '/api': 'http://localhost:5000'
    }
  }
}
```

**DaisyUI theme** suggestion for a hockey app: `night` (dark blue) or `dracula` — both look sharp and scream "sport app." Set in `tailwind.config.js`:
```js
daisyui: {
  themes: ["night"]
}
```

---

## Deployment

Build the frontend:
```bash
cd frontend && npm run build
# Output: frontend/dist/
```

Serve from Flask (simplest — everything in one deployment):
```python
# In Flask app factory:
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_spa(path):
    if path.startswith('api/'):
        return {'error': 'Not found'}, 404
    return send_from_directory('../frontend/dist', 'index.html')
```

Or deploy frontend to Netlify/Vercel (free tier, global CDN) and point API calls at your Flask server. Either works.

---

## Final Answer

Build it with **Vue 3 + Vite + DaisyUI**. Here's the one-sentence pitch:

> You get a modern SPA with first-class Auth0 support, 30+ free themes that look legitimately good on mobile, reactive countdown timers with almost no code, and a framework gentle enough that you won't need a frontend specialist to maintain it.

The HTMX/Jinja2 path sounds appealing ("stay in Flask!") but fights the API architecture you already built. React works but adds real cognitive overhead for a solo dev. Svelte is fun but the Auth0 integration requires manual work. Vue 3 + DaisyUI is the pragmatic choice that hits every requirement without drama.

Pick the `night` DaisyUI theme and it'll look like a proper sports app before you've written a single custom CSS rule.

---

_Questions? Open `/api/open-questions` → see DESIGN.md §10._

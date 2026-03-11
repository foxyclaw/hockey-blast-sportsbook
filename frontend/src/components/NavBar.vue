<template>
  <div class="navbar bg-base-300 shadow-lg sticky top-0 z-50 border-b border-base-content/10">
    <div class="navbar-start">
      <RouterLink to="/" class="btn btn-ghost text-xl font-bold tracking-tight">
        🏒 <span class="text-primary">HB</span><span class="text-base-content/80">Picks</span>
      </RouterLink>
    </div>

    <div class="navbar-center hidden sm:flex">
      <ul class="menu menu-horizontal px-1 gap-1">
        <li>
          <RouterLink to="/" class="rounded-lg text-sm font-medium" active-class="bg-primary/20 text-primary">
            Games
          </RouterLink>
        </li>
        <li v-if="isAuthenticated">
          <RouterLink to="/picks" class="rounded-lg text-sm font-medium" active-class="bg-primary/20 text-primary">
            My Picks
          </RouterLink>
        </li>
        <li v-if="isAuthenticated">
          <RouterLink to="/leagues" class="rounded-lg text-sm font-medium" active-class="bg-primary/20 text-primary">
            Leagues
          </RouterLink>
        </li>
      </ul>
    </div>

    <div class="navbar-end gap-2">
      <!-- Balance badge -->
      <div v-if="isAuthenticated && !isLoading" class="badge badge-outline badge-primary font-mono text-xs hidden sm:flex">
        💰 {{ balance.toLocaleString() }} pts
      </div>

      <!-- Auth button -->
      <div v-if="isLoading">
        <span class="loading loading-spinner loading-sm text-primary"></span>
      </div>
      <div v-else-if="isAuthenticated" class="dropdown dropdown-end">
        <div tabindex="0" role="button" class="btn btn-ghost btn-circle avatar">
          <div class="w-9 rounded-full ring ring-primary ring-offset-base-100 ring-offset-1">
            <img v-if="user?.picture" :src="user.picture" :alt="user.name" />
            <div v-else class="bg-primary text-primary-content w-9 h-9 flex items-center justify-center rounded-full text-sm font-bold">
              {{ user?.name?.[0] ?? '?' }}
            </div>
          </div>
        </div>
        <ul tabindex="0" class="mt-3 z-[1] p-2 shadow menu menu-sm dropdown-content bg-base-200 rounded-box w-52">
          <li class="menu-title px-3 py-1">
            <span class="text-xs opacity-60">{{ user?.email }}</span>
          </li>
          <li><RouterLink to="/picks">My Picks</RouterLink></li>
          <li><RouterLink to="/leagues">Leagues</RouterLink></li>
          <li><RouterLink to="/identity">Hockey Identity</RouterLink></li>
          <li><hr class="my-1 opacity-20" /></li>
          <li>
            <button @click="logout({ logoutParams: { returnTo: window.location.origin } })" class="text-error">
              Sign Out
            </button>
          </li>
        </ul>
      </div>
      <button v-else @click="loginWithRedirect()" class="btn btn-primary btn-sm">
        Sign In
      </button>

      <!-- Mobile hamburger -->
      <div class="dropdown dropdown-end sm:hidden">
        <label tabindex="0" class="btn btn-ghost btn-sm">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </label>
        <ul tabindex="0" class="menu menu-sm dropdown-content mt-3 z-[1] p-2 shadow bg-base-200 rounded-box w-52">
          <li><RouterLink to="/">Games</RouterLink></li>
          <li v-if="isAuthenticated"><RouterLink to="/picks">My Picks</RouterLink></li>
          <li v-if="isAuthenticated"><RouterLink to="/leagues">Leagues</RouterLink></li>
        </ul>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useAuth0 } from '@auth0/auth0-vue'
import { useUserStore } from '@/stores/user'

const { isAuthenticated, isLoading, user, loginWithRedirect, logout } = useAuth0()
const userStore = useUserStore()

const balance = computed(() => userStore.balance)
</script>

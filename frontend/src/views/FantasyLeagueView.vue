<template>
  <div class="max-w-5xl mx-auto px-4 py-6">
    <!-- Loading -->
    <div v-if="loading" class="flex justify-center py-12">
      <span class="loading loading-spinner loading-lg text-primary"></span>
    </div>

    <template v-else-if="league">
      <!-- Header -->
      <div class="mb-6">
        <div class="flex items-start justify-between flex-wrap gap-3">
          <div>
            <div class="text-xs text-base-content/40 mb-1">
              <RouterLink to="/fantasy" class="link link-hover text-blue-400">Fantasy</RouterLink> /
            </div>
            <div class="flex items-center gap-2">
              <h1 class="text-2xl font-extrabold tracking-tight">{{ league.name }}</h1>
              <span v-if="league.is_private" class="badge badge-neutral badge-sm">🔒 Private</span>
            </div>
            <p class="text-sm text-base-content/50 mt-1 flex flex-wrap gap-x-3">
              <span v-if="league.org_name">🏢 {{ league.org_name }}</span>
              <span v-if="league.hb_league_name">🏒 {{ league.hb_league_name }}</span>
              <span>📊 {{ league.level_name }}</span>
              <span v-if="league.hb_season_name">📅 {{ league.hb_season_name }}</span>
              <span v-else-if="league.season_label">📅 {{ league.season_label }}</span>
            </p>
            <!-- Invite code callout — only visible to creator while league is forming/draft_open -->
            <div v-if="league.is_private && league.join_code && league.is_creator && ['forming','draft_open'].includes(league.status)"
                 class="mt-3 p-3 rounded-xl border border-primary/40 bg-primary/10 flex flex-col gap-1">
              <p class="text-xs font-semibold text-primary uppercase tracking-wide">📣 Share this invite link with your friends</p>
              <div class="flex items-center gap-3 mt-1">
                <span class="font-mono font-bold text-2xl tracking-widest text-base-content">{{ league.join_code }}</span>
                <button class="btn btn-xs btn-primary" @click="copyInviteLink(league)">
                  {{ codeCopied ? '✅ Copied!' : '🔗 Copy Link' }}
                </button>
              </div>
              <span class="text-xs text-base-content/50 break-all mt-0.5">{{ inviteLink(league) }}</span>
            </div>
          </div>
          <div class="flex items-center gap-2 flex-wrap">
            <span class="badge" :class="statusBadgeClass(league.status)">
              {{ statusLabel(league.status) }}
            </span>
            <!-- Share button for active/completed leagues -->
            <button
              v-if="['active', 'completed'].includes(league.status)"
              class="btn btn-outline btn-xs"
              @click="copyLeagueLink"
              :title="linkCopied ? 'Link copied!' : 'Share league link'"
            >
              {{ linkCopied ? '✅ Copied!' : '🔗 Share' }}
            </button>
            <!-- Join button -->
            <button
              v-if="!league.is_member && ['forming', 'draft_open'].includes(league.status)"
              class="btn btn-primary btn-sm"
              @click="isAuthenticated ? showJoinModal = true : requireLogin()"
            >
              Join League
            </button>
            <!-- Open draft -->
            <button
              v-if="league.is_creator && league.status === 'forming' && (league.manager_count || 0) >= 2"
              class="btn btn-warning btn-sm"
              :disabled="openingDraft"
              @click="openDraft"
            >
              <span v-if="openingDraft" class="loading loading-spinner loading-xs"></span>
              Open Draft
            </button>
            
          </div>
        </div>

        <!-- Stats row -->
        <div class="flex gap-6 mt-3 text-sm text-base-content/60">
          <span>👥 {{ league.manager_count }} / {{ league.max_managers }} managers</span>
          <span>📋 {{ league.roster_skaters }} skaters + {{ league.roster_goalies }} goalie(s){{ league.roster_refs ? ' + ' + league.roster_refs + ' ref(s)' : '' }} per team</span>
          <template v-if="['active','completed'].includes(league.status)">
            <span v-if="league.season_starts_at">📅 Season {{ new Date(league.season_starts_at) <= new Date() ? 'started' : 'starts' }}: {{ formatDeadline(league.season_starts_at) }}</span>
          </template>
          <template v-else>
            <span v-if="league.draft_closes_at && league.draft_opens_at">⏱ Draft: {{ formatDeadline(league.draft_opens_at) }} – {{ formatDeadline(league.draft_closes_at) }}</span>
            <span v-else>⏱ {{ league.draft_pick_hours }}h per pick</span>
          </template>
        </div>
      </div>

      <!-- Tabs -->
      <div class="tabs tabs-boxed mb-6 w-fit">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          class="tab"
          :class="{ 'tab-active': activeTab === tab.id }"
          @click="activeTab = tab.id"
        >
          {{ tab.label }}
        </button>
      </div>

      <!-- ── Draft Tab ── -->
      <div v-if="activeTab === 'draft'">
        <div v-if="league.status === 'forming'" class="text-center py-10 text-base-content/40">
          <div class="text-4xl mb-2">⏳</div>
          <p class="font-medium">Draft opens {{ formatDeadline(league.draft_opens_at) }}</p>
          <p class="text-sm mt-1 max-w-xs mx-auto">
            The draft will start automatically once the league fills up, or at the scheduled time — whichever comes first.
          </p>
          <p v-if="league.is_member" class="mt-3 text-success text-sm">✅ You're in! You'll be notified when it's your turn to pick.</p>
          <p v-else class="mt-3">
            <button class="btn btn-primary btn-sm" @click="isAuthenticated ? showJoinModal = true : requireLogin()">Join League</button>
          </p>
        </div>

        <div v-else>
          <!-- Current pick info -->
          <div v-if="currentPick" class="alert mb-4" :class="currentPick.user_id === myUserId ? 'alert-success' : 'alert-info'">
            <div>
              <p class="font-semibold">
                <template v-if="currentPick.user_id === myUserId">
                  ⬆️ It's your pick! Round {{ currentPick.round }}, Pick {{ currentPick.overall_pick }}
                </template>
                <template v-else>
                  🕐 Waiting on {{ currentPick.manager?.team_name || 'a manager' }} — Pick #{{ currentPick.overall_pick }}
                </template>
              </p>
              <p v-if="currentPick.deadline" class="text-sm opacity-70 mt-0.5">
                Deadline: {{ formatDeadline(currentPick.deadline) }}
              </p>
            </div>
          </div>
          <div v-else-if="['active', 'completed'].includes(league.status) && draftQueue.length > 0" class="alert alert-success mb-4">
            <span>✅ Draft complete! Season is {{ league.status === 'active' ? 'active' : 'completed' }}.</span>
          </div>

          <!-- Player pool panel (shown during draft, full pool with drafted indicators) -->
          <div v-if="['draft_open', 'drafting'].includes(league.status)" class="mb-6">
            <div class="card bg-base-200 shadow">
              <div class="card-body p-4">
                <div class="flex items-center justify-between mb-3 flex-wrap gap-2">
                  <h3 class="font-semibold">
                    Draft Pool
                    <span v-if="currentPick && currentPick.user_id === myUserId && league.is_member" class="badge badge-success badge-sm ml-2 animate-pulse">Your Pick!</span>
                  </h3>
                  <input
                    v-model="playerFilter"
                    type="text"
                    placeholder="Search player..."
                    class="input input-bordered input-xs w-40"
                  />
                </div>

                <!-- Skater / Goalie sub-tabs -->
                <div class="tabs tabs-boxed tabs-xs mb-3 w-fit">
                  <button class="tab" :class="{ 'tab-active': poolTab === 'skaters' }" @click="poolTab = 'skaters'"
                    :disabled="currentPick?.is_goalie_pick || currentPick?.is_ref_pick">
                    Skaters
                  </button>
                  <button class="tab" :class="{ 'tab-active': poolTab === 'goalies' }" @click="poolTab = 'goalies'"
                    :disabled="currentPick && !currentPick?.is_goalie_pick && currentPick?.user_id === myUserId">
                    Goalies <span v-if="currentPick?.is_goalie_pick && currentPick?.user_id === myUserId" class="badge badge-xs badge-error ml-1">Pick now!</span>
                  </button>
                  <button v-if="league.roster_refs > 0" class="tab" :class="{ 'tab-active': poolTab === 'refs' }" @click="poolTab = 'refs'"
                    :disabled="currentPick && !currentPick?.is_ref_pick && currentPick?.user_id === myUserId">
                    🎮 Refs <span v-if="currentPick?.is_ref_pick && currentPick?.user_id === myUserId" class="badge badge-xs badge-error ml-1">Last Pick!</span>
                  </button>
                </div>

                <!-- Skaters table -->
                <div v-if="poolTab === 'skaters'" class="overflow-x-auto max-h-80 overflow-y-auto">
                  <table class="table table-xs w-full">
                    <thead class="sticky top-0 bg-base-200 z-10">
                      <tr>
                        <th class="w-16"></th>
                        <th class="cursor-pointer" @click="setSortKey('name')">Player <span v-if="sortKey === 'name'">{{ sortDir === 'asc' ? '▲' : '▼' }}</span></th>
                        <th class="cursor-pointer text-right" @click="setSortKey('games_played')">GP <span v-if="sortKey === 'games_played'">{{ sortDir === 'asc' ? '▲' : '▼' }}</span></th>
                        <th class="cursor-pointer text-right" @click="setSortKey('goals')">G <span v-if="sortKey === 'goals'">{{ sortDir === 'asc' ? '▲' : '▼' }}</span></th>
                        <th class="cursor-pointer text-right" @click="setSortKey('assists')">A <span v-if="sortKey === 'assists'">{{ sortDir === 'asc' ? '▲' : '▼' }}</span></th>
                        <th class="cursor-pointer text-right" @click="setSortKey('points')">Pts <span v-if="sortKey === 'points'">{{ sortDir === 'asc' ? '▲' : '▼' }}</span></th>
                        <th class="cursor-pointer text-right" @click="setSortKey('penalties')">Pen <span v-if="sortKey === 'penalties'">{{ sortDir === 'asc' ? '▲' : '▼' }}</span></th>
                        <th class="cursor-pointer text-right" @click="setSortKey('fantasy_points')">FP <span v-if="sortKey === 'fantasy_points'">{{ sortDir === 'asc' ? '▲' : '▼' }}</span></th>
                        <th class="cursor-pointer text-right" @click="setSortKey('fantasy_ppg')">FPPG <span v-if="sortKey === 'fantasy_ppg'">{{ sortDir === 'asc' ? '▲' : '▼' }}</span></th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="p in sortedSkaters"
                        :key="p.hb_human_id"
                        :class="p.drafted_by ? 'opacity-40' : 'hover'"
                      >
                        <td>
                          <span v-if="p.drafted_by" class="text-xs text-base-content/40">{{ p.drafted_by.team_name }}</span>
                          <template v-else-if="currentPick && currentPick.user_id === myUserId && league.is_member">
                            <button
                              class="btn btn-xs btn-primary"
                              :disabled="picking"
                              @click="pickPlayer(p)"
                            >
                              Draft
                            </button>
                          </template>
                          <template v-else>
                            <button class="btn btn-xs btn-disabled" title="Not your turn" disabled>Draft</button>
                          </template>
                        </td>
                        <td><a :href="`http://hockey-blast.com/human_stats/human_stats?human_id=${p.hb_human_id}`" target="_blank" class="link link-hover text-blue-400">{{ p.first_name }} {{ p.last_name }}</a></td>
                        <td class="text-right">{{ p.games_played }}</td>
                        <td class="text-right">{{ p.goals }}</td>
                        <td class="text-right">{{ p.assists }}</td>
                        <td class="text-right">{{ p.points }}</td>
                        <td class="text-right">{{ p.penalties }}</td>
                        <td class="text-right font-bold text-primary">{{ p.fantasy_points != null ? Number(p.fantasy_points).toFixed(1) : '—' }}</td>
                        <td class="text-right text-base-content/60">{{ p.fantasy_ppg != null ? Number(p.fantasy_ppg).toFixed(1) : '—' }}</td>
                      </tr>
                      <tr v-if="sortedSkaters.length === 0">
                        <td colspan="9" class="text-center text-base-content/40 py-4">No skaters found</td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                <!-- Goalies table -->
                <div v-if="poolTab === 'goalies'" class="overflow-x-auto max-h-80 overflow-y-auto">
                  <table class="table table-xs w-full">
                    <thead class="sticky top-0 bg-base-200 z-10">
                      <tr>
                        <th></th>
                        <th>Player</th>
                        <th class="text-right">GP</th>
                        <th class="text-right">GAA</th>
                        <th class="text-right">SV%</th>
                        <th class="text-right">FP</th>
                        <th class="text-right">FPPG</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="p in filteredGoalies"
                        :key="p.hb_human_id"
                        :class="p.drafted_by ? 'opacity-40' : 'hover'"
                      >
                        <td>
                          <span v-if="p.drafted_by" class="text-xs text-base-content/40">{{ p.drafted_by.team_name }}</span>
                          <template v-else-if="currentPick && currentPick.user_id === myUserId && league.is_member">
                            <button class="btn btn-xs btn-primary" :disabled="picking" @click="pickPlayer(p)">Draft</button>
                          </template>
                          <template v-else>
                            <button class="btn btn-xs btn-disabled" title="Not your turn" disabled>Draft</button>
                          </template>
                        </td>
                        <td><a :href="`http://hockey-blast.com/human_stats/human_stats?human_id=${p.hb_human_id}`" target="_blank" class="link link-hover text-blue-400">{{ p.first_name }} {{ p.last_name }}</a></td>
                        <td class="text-right">{{ p.goalie_games ?? p.games_played }}</td>
                        <td class="text-right">{{ p.goals_against_avg ?? '—' }}</td>
                        <td class="text-right">{{ p.save_percentage != null ? (p.save_percentage * 100).toFixed(1) + '%' : '—' }}</td>
                        <td class="text-right font-bold text-primary">{{ p.fantasy_points_goalie != null ? Number(p.fantasy_points_goalie ?? p.fantasy_points).toFixed(1) : '—' }}</td>
                        <td class="text-right text-base-content/60">{{ p.goalie_games > 0 ? ((p.fantasy_points_goalie ?? p.fantasy_points) / p.goalie_games).toFixed(1) : '—' }}</td>
                      </tr>
                      <tr v-if="filteredGoalies.length === 0">
                        <td colspan="7" class="text-center text-base-content/40 py-4">No goalies found</td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                <!-- Refs table -->
                <div v-if="poolTab === 'refs'" class="overflow-x-auto max-h-80 overflow-y-auto">
                  <table class="table table-xs w-full">
                    <thead class="sticky top-0 bg-base-200 z-10">
                      <tr>
                        <th></th>
                        <th>Referee</th>
                        <th class="text-right">Games</th>
                        <th class="text-right">Penalties</th>
                        <th class="text-right">GMs</th>
                        <th class="text-right">FP</th>
                        <th class="text-right">FPPG</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="p in filteredRefs"
                        :key="p.hb_human_id"
                        :class="p.drafted_by ? 'opacity-40' : 'hover'"
                      >
                        <td>
                          <span v-if="p.drafted_by" class="text-xs text-base-content/40">{{ p.drafted_by.team_name }}</span>
                          <template v-else-if="currentPick && currentPick.user_id === myUserId && league.is_member && currentPick.is_ref_pick">
                            <button class="btn btn-xs btn-primary" :disabled="picking" @click="pickPlayer(p)">Draft</button>
                          </template>
                          <template v-else>
                            <button class="btn btn-xs btn-disabled" disabled>Draft</button>
                          </template>
                        </td>
                        <td><a :href="`http://hockey-blast.com/human_stats/human_stats?human_id=${p.hb_human_id}`" target="_blank" class="link link-hover text-blue-400">{{ p.first_name }} {{ p.last_name }}</a></td>
                        <td class="text-right">{{ p.games_reffed }}</td>
                        <td class="text-right">{{ p.penalties_given }}</td>
                        <td class="text-right">{{ p.gm_given }}</td>
                        <td class="text-right font-bold text-primary">{{ p.fantasy_points_ref != null ? Number(p.fantasy_points_ref ?? p.fantasy_points).toFixed(1) : '—' }}</td>
                        <td class="text-right text-base-content/60">{{ p.games_reffed > 0 ? ((p.fantasy_points_ref ?? p.fantasy_points) / p.games_reffed).toFixed(1) : '—' }}</td>
                      </tr>
                      <tr v-if="filteredRefs.length === 0">
                        <td colspan="7" class="text-center text-base-content/40 py-4">No referees found</td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                <div v-if="pickError" class="text-error text-xs mt-2">{{ pickError }}</div>
                <div class="text-xs text-base-content/30 mt-2">FP = Fantasy Points &nbsp;·&nbsp; FPPG = Fantasy Points Per Game</div>
              </div>
            </div>
          </div>

          <!-- Draft progress summary (only shown during draft) -->
          <div v-if="['draft_open', 'drafting'].includes(league.status)" class="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
            <div class="bg-base-200 rounded-lg p-3">
              <div class="text-2xl font-bold text-success">{{ draftQueue.filter(p => p.picked_at).length }}</div>
              <div class="text-xs text-base-content/50 mt-0.5">Picks Made</div>
            </div>
            <div class="bg-base-200 rounded-lg p-3">
              <div class="text-2xl font-bold text-warning">{{ draftQueue.filter(p => !p.picked_at && !p.is_skipped).length }}</div>
              <div class="text-xs text-base-content/50 mt-0.5">Picks Remaining</div>
            </div>
            <div class="bg-base-200 rounded-lg p-3">
              <div class="text-2xl font-bold">{{ currentPick ? currentPick.round : '—' }}</div>
              <div class="text-xs text-base-content/50 mt-0.5">Current Round</div>
            </div>
            <div class="bg-base-200 rounded-lg p-3">
              <div class="text-2xl font-bold text-primary">{{ ['active','completed'].includes(league.status) && !currentPick ? 0 : (league.max_managers && league.roster_skaters ? (league.roster_skaters + league.roster_goalies) - (currentPick ? currentPick.round - 1 : 0) : '—') }}</div>
              <div class="text-xs text-base-content/50 mt-0.5">Rounds Left</div>
            </div>
          </div>
        </div>
      </div>

      <!-- ── Rosters Tab ── -->
      <div v-if="activeTab === 'rosters'">
        <div v-if="!league.managers?.length" class="text-center py-10 text-base-content/40">No managers yet.</div>
        <div v-else class="space-y-4">
          <div
            v-for="mgr in league.managers"
            :key="mgr.user_id"
            class="card bg-base-200 shadow-sm"
          >
            <div class="card-body p-4">
              <h3 class="font-semibold">{{ mgr.team_name }}</h3>
              <p class="text-xs text-base-content/40 mb-2">{{ mgr.display_name }}</p>
              <RosterList :league-id="league.id" :user-id="mgr.user_id" />
            </div>
          </div>
        </div>
      </div>

      <!-- ── Standings Tab ── -->
      <div v-if="activeTab === 'standings'">
        <div v-if="standingsLoading" class="flex justify-center py-8">
          <span class="loading loading-spinner text-primary"></span>
        </div>
        <div v-else-if="!standings.length" class="text-center py-10 text-base-content/40">
          No standings yet. Season starts after the draft.
        </div>
        <div v-else class="overflow-x-auto">
          <table class="table w-full">
            <thead>
              <tr>
                <th>#</th>
                <th>Team</th>
                <th>Manager</th>
                <th class="text-right">Week Pts</th>
                <th class="text-right font-bold">Total Pts</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in standings"
                :key="row.user_id"
                :class="[
                  { 'bg-primary/10 font-semibold': row.user_id === myUserId },
                  league.hb_division_id ? 'cursor-pointer hover:bg-base-300' : ''
                ]"
                @click="league.hb_division_id ? (activeTab = 'games', loadGames(row.user_id)) : null"
                :title="league.hb_division_id ? `View ${row.team_name}'s games` : ''"
              >
                <td>{{ row.rank || '—' }}</td>
                <td>{{ row.team_name }}
                  <span v-if="league.hb_division_id" class="text-xs opacity-40 ml-1">🏒</span>
                </td>
                <td class="text-base-content/60 text-sm">{{ row.display_name }}</td>
                <td class="text-right">{{ row.week_points != null ? Number(row.week_points).toFixed(1) : '—' }}</td>
                <td class="text-right font-bold">{{ row.total_points != null ? Number(row.total_points).toFixed(1) : '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>


      <!-- ── Games Tab ── -->
      <div v-if="activeTab === 'games'">
        <!-- Whose roster are we viewing? -->
        <div v-if="viewUserId" class="flex items-center justify-between mb-3">
          <div class="text-sm font-medium">
            {{ standings.find(r => r.user_id === viewUserId)?.team_name || 'Unknown' }}
            <span class="opacity-50 text-xs font-normal ml-1">
              ({{ standings.find(r => r.user_id === viewUserId)?.display_name }})
            </span>
          </div>
          <button class="btn btn-xs btn-ghost" @click="loadGames(null)">← My roster</button>
        </div>
        <div v-if="gamesLoading" class="flex justify-center py-10">
          <span class="loading loading-spinner loading-md"></span>
        </div>
        <div v-else-if="!games.length" class="text-center text-base-content/50 py-10">
          No games found for this season.
        </div>
        <div v-else class="space-y-2">
          <div v-for="game in games" :key="game.id" class="card card-compact bg-base-200 shadow-sm">
            <div class="card-body p-3">
              <!-- Meta row -->
              <div class="flex items-center justify-between gap-2 flex-wrap">
                <div class="text-xs text-base-content/50 flex items-center gap-2">
                  <span>{{ game.date }}</span>
                  <span v-if="game.time">{{ game.time }}</span>
                  <span v-if="game.location" class="hidden sm:inline">· {{ game.location }}</span>
                </div>
                <div class="flex items-center gap-1">
                  <span v-if="game.game_type" class="badge badge-xs badge-outline">{{ game.game_type }}</span>
                  <span
                    v-if="game.status === 'OPEN'"
                    class="inline-flex items-center gap-1 badge badge-xs badge-success animate-pulse"
                  >
                    <span class="w-1.5 h-1.5 rounded-full bg-white inline-block"></span>
                    LIVE
                  </span>
                  <span v-else class="badge badge-xs" :class="{
                    'badge-success': game.status && game.status.startsWith('Final'),
                    'badge-warning': game.status === 'Scheduled',
                    'badge-info': game.status && game.status.toLowerCase().includes('live'),
                  }">{{ game.status }}</span>
                </div>
              </div>
              <!-- Score row -->
              <div class="flex items-center justify-between gap-2 mt-1">
                <div class="flex-1 text-right font-bold text-base leading-tight truncate">{{ game.visitor_team_name }}</div>
                <div class="text-center w-20 shrink-0">
                  <span v-if="game.visitor_final_score != null" class="text-2xl font-black tracking-tight">{{ game.visitor_final_score }}–{{ game.home_final_score }}</span>
                  <span v-else class="text-base-content/30 text-sm font-medium">vs</span>
                </div>
                <div class="flex-1 text-left font-bold text-base leading-tight truncate">{{ game.home_team_name }}</div>
              </div>
              <!-- My rostered players -->
              <div v-if="game.my_players && game.my_players.length" class="mt-2 pt-2 border-t border-base-300">
                <!-- Scorers: players who got points -->
                <div class="flex flex-wrap gap-1 mb-1">
                  <div
                    v-for="p in game.my_players.filter(p => p.points !== 0 || p.penalties > 0)"
                    :key="p.hb_human_id"
                    class="flex items-center gap-1 rounded px-2 py-0.5 text-xs bg-base-300"
                  >
                    <span class="font-medium">{{ p.display_name }}</span>
                    <span class="font-bold" :class="p.points < 0 ? 'text-error' : 'text-primary'">{{ Number(p.points).toFixed(1) }}</span>
                    <span v-if="p.goals" class="text-success">{{ p.goals }}G</span>
                    <span v-if="p.assists" class="text-info">{{ p.assists }}A</span>
                    <span v-if="p.is_goalie_win" class="text-warning">W</span>
                    <span v-if="p.is_shutout" class="text-accent">SO</span>
                    <span v-if="p.penalties" class="text-error">{{ p.penalties }}PEN</span>
                    <span v-if="p.ref_games" class="text-secondary">REF</span>
                    <span v-if="p.games_played && !p.goals && !p.assists && !p.is_goalie_win && !p.ref_games" class="text-base-content/50">GP</span>
                  </div>
                </div>
                <!-- Zeroes: just names, dimmed -->
                <div v-if="game.my_players.some(p => p.points === 0 && !p.penalties)" class="text-xs text-base-content/35 leading-relaxed">
                  {{ game.my_players.filter(p => p.points === 0 && !p.penalties).map(p => p.display_name).join(', ') }}
                </div>
              </div>
              <!-- Stats link -->
              <div class="text-right mt-1">
                <a :href="game.game_card_url" target="_blank" rel="noopener" class="link link-primary text-xs opacity-50 hover:opacity-100">📊 Stats</a>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ── My Team Tab ── -->
      <div v-if="activeTab === 'myteam'">
        <div v-if="!league.is_member" class="text-center py-10 text-base-content/40">
          <p>You're not in this league.</p>
          <button v-if="['forming', 'draft_open'].includes(league.status)" class="btn btn-primary btn-sm mt-3" @click="isAuthenticated ? showJoinModal = true : requireLogin()">
            Join League
          </button>
        </div>
        <div v-else>
          <h3 class="font-semibold mb-3">Your Roster</h3>
          <RosterList :league-id="league.id" :user-id="myUserId" show-points />
        </div>
      </div>
    </template>

    <div v-else class="text-center py-16 text-base-content/40">
      League not found.
    </div>

    <!-- Join Modal -->
    <div v-if="showJoinModal" class="modal modal-open">
      <div class="modal-box max-w-sm">
        <h3 class="font-bold text-lg mb-4">Join League</h3>
        <form @submit.prevent="joinLeague" class="space-y-4">
          <div class="form-control">
            <label class="label"><span class="label-text text-sm">Your Team Name</span></label>
            <input
              v-model="joinForm.team_name"
              type="text"
              placeholder="e.g. Ice Bandits"
              class="input input-bordered input-sm"
              required
            />
          </div>
          <div v-if="league?.is_private" class="form-control">
            <label class="label"><span class="label-text text-sm">Invite Code</span></label>
            <input
              v-model="joinForm.join_code"
              type="text"
              placeholder="e.g. X7K2M9"
              class="input input-bordered input-sm uppercase"
              maxlength="6"
              required
            />
          </div>
          <div v-if="joinError" class="alert alert-error text-sm py-2">{{ joinError }}</div>
          <div class="modal-action">
            <button type="button" class="btn btn-ghost btn-sm" @click="showJoinModal = false">Cancel</button>
            <button type="submit" class="btn btn-primary btn-sm" :disabled="joining">
              <span v-if="joining" class="loading loading-spinner loading-xs"></span>
              Join
            </button>
          </div>
        </form>
      </div>
      <div class="modal-backdrop" @click="showJoinModal = false"></div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, h } from 'vue'
import { useRoute } from 'vue-router'
import { useAuth0 } from '@auth0/auth0-vue'
import { useUserStore } from '@/stores/user'
import { useApiClient } from '@/api/client'

// ── Roster list component (render function — no compiler needed) ──────────
const RosterList = {
  name: 'RosterList',
  props: {
    leagueId: { type: Number, required: true },
    userId:   { type: Number, required: true },
  },
  setup(props) {
    const api = useApiClient()
    const roster   = ref([])
    const rLoading = ref(true)

    async function load() {
      rLoading.value = true
      try {
        const { data } = await api.get(`/api/fantasy/leagues/${props.leagueId}/roster/${props.userId}`)
        roster.value = data.roster || []
      } catch {
        roster.value = []
      } finally {
        rLoading.value = false
      }
    }

    onMounted(load)
    return () => {
      if (rLoading.value) {
        return h('div', { class: 'text-xs text-base-content/40 py-2' }, 'Loading…')
      }
      if (!roster.value.length) {
        return h('div', { class: 'text-xs text-base-content/40 italic py-2' }, 'No players drafted yet.')
      }

      // Table header
      const thead = h('thead', [
        h('tr', [
          h('th', { class: 'text-left text-xs font-medium opacity-60 pb-1 pr-4' }, 'Player'),
          h('th', { class: 'text-right text-xs font-medium opacity-60 pb-1 px-2' }, 'GP'),
          h('th', { class: 'text-right text-xs font-medium opacity-60 pb-1 px-2' }, 'G'),
          h('th', { class: 'text-right text-xs font-medium opacity-60 pb-1 px-2' }, 'A'),
          h('th', { class: 'text-right text-xs font-medium opacity-60 pb-1 px-2 text-error' }, 'PIM'),
          h('th', { class: 'text-right text-xs font-medium opacity-60 pb-1 pl-2' }, 'FP'),
        ])
      ])

      const rows = roster.value.map(p => {
        const icon = p.is_ref ? '🎮' : p.is_goalie ? '🥅' : '🏒'
        const liveChip = p.is_live
          ? h('span', { class: 'inline-flex items-center gap-1 ml-1' }, [
              h('span', { class: 'w-2 h-2 rounded-full bg-green-400 animate-pulse inline-block' }),
              p.live_game_id
                ? h('a', {
                    href: `https://hockey-blast.com/game_card?game_id=${p.live_game_id}`,
                    target: '_blank',
                    class: 'text-green-400 text-xs font-semibold hover:underline',
                  }, 'LIVE')
                : h('span', { class: 'text-green-400 text-xs font-semibold' }, 'LIVE'),
            ])
          : null
        const nameCell = h('td', { class: 'pr-4 py-1' }, [
          h('span', { class: 'text-sm' }, `${icon} ${p.player_name || '—'}`),
          liveChip,
        ])
        return h('tr', { key: p.hb_human_id, class: 'border-t border-base-300/30' }, [
          nameCell,
          h('td', { class: 'text-right text-xs px-2 py-1 opacity-70' }, p.gp ?? 0),
          h('td', { class: 'text-right text-xs px-2 py-1 opacity-70' }, p.goals ?? 0),
          h('td', { class: 'text-right text-xs px-2 py-1 opacity-70' }, p.assists ?? 0),
          h('td', { class: 'text-right text-xs px-2 py-1 ' + (p.penalties ? 'text-error' : 'opacity-70') }, p.penalties ?? 0),
          h('td', { class: 'text-right text-xs pl-2 py-1 font-semibold text-primary' },
            p.fantasy_points != null ? p.fantasy_points.toFixed(1) : '—'),
        ])
      })

      return h('div', { class: 'overflow-x-auto' }, [
        h('table', { class: 'w-full' }, [thead, h('tbody', rows)])
      ])
    }
  },
}

// ── Main component ────────────────────────────────────────────────────────
const route = useRoute()
const api = useApiClient()
const { isAuthenticated, isLoading: authLoading, loginWithRedirect } = useAuth0()
const userStore = useUserStore()

const league = ref(null)
const loading = ref(true)
const draftQueue = ref([])
const pool = ref({ skaters: [], goalies: [], refs: [] })
const standings = ref([])
const standingsLoading = ref(false)
const games = ref([])
const gamesLoading = ref(false)
const viewUserId = ref(null)  // whose roster to show in games tab (null = own)

const allTabs = [
  { id: 'standings', label: '🏆 Standings' },
  { id: 'games', label: '🏒 Games' },
  { id: 'myteam', label: '⭐ My Team' },
  { id: 'rosters', label: '👥 Rosters' },
  { id: 'draft', label: '📋 Draft' },
]
const tabs = computed(() => {
  if (!league.value) return allTabs
  const isLive = ['active', 'completed'].includes(league.value.status)
  const hasGames = !!league.value.hb_division_id
  return allTabs.filter(t => {
    if (t.id === 'draft' && isLive) return false
    if (t.id === 'games' && !hasGames) return false
    return true
  })
})
const activeTab = ref('draft')
// Once league loads, switch to standings if draft is done
watch(() => league.value?.status, (status) => {
  if (status && ['active', 'completed'].includes(status) && activeTab.value === 'draft') {
    activeTab.value = 'standings'
  }
}, { immediate: true })

const showJoinModal = ref(false)
const joining = ref(false)
const joinError = ref('')
const joinForm = ref({ team_name: '', join_code: '' })

const openingDraft = ref(false)
const linkCopied = ref(false)
async function copyLeagueLink() {
  try {
    // For private leagues that are still joinable, include the join code so
    // the recipient lands with it pre-filled. For active/completed leagues
    // (draft done, no new members), share a plain link — code is irrelevant.
    const l = league.value
    const joinable = l?.is_private && l?.join_code && ['forming', 'draft_open'].includes(l?.status)
    const url = joinable
      ? `${window.location.origin}/fantasy/${l.id}?join_code=${l.join_code}`
      : `${window.location.origin}/fantasy/${l?.id}`
    await navigator.clipboard.writeText(url)
    linkCopied.value = true
    setTimeout(() => { linkCopied.value = false }, 2500)
  } catch {
    // fallback: select URL bar
  }
}
const startingSeason = ref(false)

const playerFilter = ref('')
const positionFilter = ref('')
const picking = ref(false)
const codeCopied = ref(false)

function inviteLink(league) {
  return `${window.location.origin}/fantasy/${league.id}?join_code=${league.join_code}`
}

function copyInviteLink(league) {
  navigator.clipboard.writeText(inviteLink(league)).then(() => {
    codeCopied.value = true
    setTimeout(() => { codeCopied.value = false }, 2500)
  })
}
const pickError = ref('')
const poolTab = ref('skaters')
// Auto-switch pool tab based on current pick type
watch(() => currentPick.value, (pick) => {
  if (!pick) return
  if (pick.user_id === myUserId.value) {
    if (pick.is_goalie_pick) poolTab.value = 'goalies'
    else if (pick.is_ref_pick) poolTab.value = 'refs'
    else poolTab.value = 'skaters'
  }
}, { immediate: true })
const sortKey = ref('fantasy_points')
const sortDir = ref('desc')

function setSortKey(key) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortDir.value = 'desc'
  }
}

const myUserId = computed(() => userStore.predUser?.id)

// My drafted players from the draft queue (already picked)
const myDraftedRoster = computed(() => {
  if (!myUserId.value) return []
  return draftQueue.value.filter(p => p.user_id === myUserId.value && p.picked_at && !p.is_skipped)
})

const myDraftedSkaters = computed(() =>
  myDraftedRoster.value.filter(p => {
    const player = [...(pool.value.skaters || []), ...(pool.value.goalies || []), ...(pool.value.refs || [])]
      .find(pl => pl.hb_human_id === p.hb_human_id)
    return player && !player.is_goalie && !player.is_ref
  }).length
)

const myDraftedGoalies = computed(() =>
  myDraftedRoster.value.filter(p => {
    const player = [...(pool.value.skaters || []), ...(pool.value.goalies || [])]
      .find(pl => pl.hb_human_id === p.hb_human_id)
    return player && player.is_goalie
  }).length
)

const myDraftedRefs = computed(() =>
  myDraftedRoster.value.filter(p => {
    const player = (pool.value.refs || []).find(pl => pl.hb_human_id === p.hb_human_id)
    return !!player
  }).length
)

const filteredRefs = computed(() => {
  const drafted = new Set(draftQueue.value.filter(p => p.picked_at).map(p => p.hb_human_id))
  const managers = {}
  // Build manager name map from standings
  for (const s of standings.value) managers[s.user_id] = s
  return (pool.value.refs || []).map(p => {
    if (drafted.has(p.hb_human_id)) {
      const pick = draftQueue.value.find(q => q.hb_human_id === p.hb_human_id && q.picked_at)
      return { ...p, drafted_by: pick ? { team_name: managers[pick.user_id]?.team_name || 'Someone' } : { team_name: '?' } }
    }
    return { ...p, drafted_by: null }
  })
})

// True when it's my turn AND I must pick a goalie (last pick(s) need to fill goalie slot)
const mustPickGoalie = computed(() => {
  if (!league.value || !currentPick.value || currentPick.value.user_id !== myUserId.value) return false
  const totalPicks = (league.value.roster_skaters || 0) + (league.value.roster_goalies || 0)
  const picksLeft = totalPicks - myDraftedRoster.value.length
  const goaliesNeeded = (league.value.roster_goalies || 1) - myDraftedGoalies.value
  return picksLeft <= goaliesNeeded
})

// True when it's my turn AND I must NOT pick a goalie (goalie slots full)
const mustPickSkater = computed(() => {
  if (!league.value || !currentPick.value || currentPick.value.user_id !== myUserId.value) return false
  return myDraftedGoalies.value >= (league.value.roster_goalies || 1)
})

const currentPick = computed(() =>
  draftQueue.value.find(p => !p.picked_at && !p.is_skipped)
)

const filteredPool = computed(() => {
  const allPlayers = [
    ...(positionFilter.value === 'goalie' ? [] : pool.value.skaters),
    ...(positionFilter.value === 'skater' ? [] : pool.value.goalies),
  ]
  if (!playerFilter.value) return allPlayers
  const q = playerFilter.value.toLowerCase()
  return allPlayers.filter(p =>
    `${p.first_name} ${p.last_name}`.toLowerCase().includes(q)
  )
})

const sortedSkaters = computed(() => {
  const skaters = pool.value.skaters || []
  const q = playerFilter.value.toLowerCase()
  const filtered = q
    ? skaters.filter(p => `${p.first_name} ${p.last_name}`.toLowerCase().includes(q))
    : skaters

  return [...filtered].sort((a, b) => {
    // Always sink drafted players to the bottom
    const aDrafted = a.drafted_by ? 1 : 0
    const bDrafted = b.drafted_by ? 1 : 0
    if (aDrafted !== bDrafted) return aDrafted - bDrafted

    let aVal, bVal
    if (sortKey.value === 'name') {
      aVal = `${a.first_name} ${a.last_name}`
      bVal = `${b.first_name} ${b.last_name}`
      return sortDir.value === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal)
    }
    aVal = a[sortKey.value] ?? 0
    bVal = b[sortKey.value] ?? 0
    return sortDir.value === 'asc' ? aVal - bVal : bVal - aVal
  })
})

const filteredGoalies = computed(() => {
  const goalies = pool.value.goalies || []
  const q = playerFilter.value.toLowerCase()
  const filtered = q
    ? goalies.filter(p => `${p.first_name} ${p.last_name}`.toLowerCase().includes(q))
    : goalies
  return [...filtered].sort((a, b) => {
    const aDrafted = a.drafted_by ? 1 : 0
    const bDrafted = b.drafted_by ? 1 : 0
    if (aDrafted !== bDrafted) return aDrafted - bDrafted
    return (b.fantasy_points_goalie ?? b.fantasy_points ?? 0) - (a.fantasy_points_goalie ?? a.fantasy_points ?? 0)
  })
})

function statusLabel(s) {
  return { forming: 'Forming', draft_open: 'Draft Open', drafting: 'Drafting', active: 'Active', completed: 'Completed' }[s] || s
}

function statusBadgeClass(s) {
  return { forming: 'badge-info', draft_open: 'badge-warning', drafting: 'badge-warning', active: 'badge-success', completed: 'badge-neutral' }[s] || 'badge-ghost'
}

function formatDeadline(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString('en-US', { timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone, month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZoneName: 'short' })
}

function requireLogin() {
  localStorage.setItem('auth_return_to', route.fullPath)
  loginWithRedirect()
}

async function loadLeague() {
  loading.value = true
  try {
    const { data } = await api.get(`/api/fantasy/leagues/${route.params.id}`)
    league.value = data
  } catch {
    league.value = null
  } finally {
    loading.value = false
  }
}

async function loadDraftQueue() {
  try {
    const { data } = await api.get(`/api/fantasy/leagues/${route.params.id}/draft/queue`)
    draftQueue.value = data.queue || []
  } catch {
    draftQueue.value = []
  }
}

async function loadPool() {
  try {
    const { data } = await api.get(`/api/fantasy/leagues/${route.params.id}/pool`)
    pool.value = data
  } catch {
    pool.value = { skaters: [], goalies: [] }
  }
}

async function loadGames(userId = null) {
  gamesLoading.value = true
  viewUserId.value = userId
  try {
    const params = userId ? `?user_id=${userId}` : ''
    const { data } = await api.get(`/api/fantasy/leagues/${route.params.id}/games${params}`)
    games.value = data.games || []
  } catch {
    games.value = []
  } finally {
    gamesLoading.value = false
  }
}

async function loadStandings() {
  standingsLoading.value = true
  try {
    const { data } = await api.get(`/api/fantasy/leagues/${route.params.id}/standings`)
    standings.value = data.standings || []
  } catch {
    standings.value = []
  } finally {
    standingsLoading.value = false
  }
}

async function joinLeague() {
  joinError.value = ''
  joining.value = true
  try {
    const payload = { team_name: joinForm.value.team_name }
    if (league.value?.is_private && joinForm.value.join_code) {
      payload.join_code = joinForm.value.join_code.toUpperCase()
    }
    await api.post(`/api/fantasy/leagues/${route.params.id}/join`, payload)
    showJoinModal.value = false
    joinForm.value = { team_name: '', join_code: '' }
    await loadLeague()
  } catch (e) {
    joinError.value = e?.response?.data?.message || 'Failed to join'
  } finally {
    joining.value = false
  }
}

async function openDraft() {
  openingDraft.value = true
  try {
    await api.post(`/api/fantasy/leagues/${route.params.id}/open-draft`)
    await loadLeague()
    await loadDraftQueue()
    await loadPool()
  } catch (e) {
    alert(e?.response?.data?.message || 'Failed to open draft')
  } finally {
    openingDraft.value = false
  }
}

async function startSeason() {
  startingSeason.value = true
  try {
    await api.post(`/api/fantasy/leagues/${route.params.id}/start`)
    await loadLeague()
  } catch (e) {
    alert(e?.response?.data?.message || 'Failed to start season')
  } finally {
    startingSeason.value = false
  }
}

async function pickPlayer(player) {
  pickError.value = ''
  picking.value = true
  try {
    await api.post(`/api/fantasy/leagues/${route.params.id}/draft`, { hb_human_id: player.hb_human_id })
    await loadDraftQueue()
    await loadPool()
    await loadLeague()
  } catch (e) {
    pickError.value = e?.response?.data?.message || 'Failed to pick player'
  } finally {
    picking.value = false
  }
}

// Load standings when tab changes
// Reload league when auth state resolves — token wasn't available on first load
watch(authLoading, (loading) => {
  if (!loading) loadLeague()
})

// Auto-refresh draft state every 30s when draft is active
let _draftPollInterval = null
onUnmounted(() => { if (_draftPollInterval) clearInterval(_draftPollInterval) })

watch(() => league.value?.status, (status) => {
  if (_draftPollInterval) { clearInterval(_draftPollInterval); _draftPollInterval = null }
  if (['draft_open', 'drafting'].includes(status)) {
    _draftPollInterval = setInterval(async () => {
      await loadLeague()
      await Promise.all([loadDraftQueue(), loadPool()])
    }, 30000)
  }
}, { immediate: true })

watch(activeTab, (tab) => {
  if (tab === 'standings') loadStandings()
  if (tab === 'games') loadGames()
})

// Auto-switch pool tab based on pick type
watch(currentPick, (pick) => {
  if (!pick || pick.user_id !== myUserId.value) return
  if (pick.is_goalie_pick) poolTab.value = 'goalies'
  else if (pick.is_ref_pick) poolTab.value = 'refs'
  else poolTab.value = 'skaters'
}, { immediate: true })

onMounted(async () => {
  // If user is not logged in and arrived via an invite link, send them to login first
  // then return them to this exact URL (with join_code) after auth
  if (!isAuthenticated.value && route.query.join_code) {
    requireLogin()
    return
  }

  await loadLeague()
  // Honor ?tab=draft (or other tab) from notification link
  const tabParam = route.query.tab
  if (tabParam && tabs.value.some(t => t.id === tabParam)) {
    activeTab.value = tabParam
  }
  // Pre-fill join code only if league is still open for new members
  const urlCode = route.query.join_code
  const leagueStillJoinable = ['forming', 'draft_open'].includes(league.value?.status)
  if (urlCode && leagueStillJoinable && league.value?.is_private && !league.value?.is_member) {
    joinForm.value.join_code = String(urlCode).toUpperCase()
    showJoinModal.value = true
  }
  if (league.value && !['forming'].includes(league.value.status)) {
    await Promise.all([loadDraftQueue(), loadPool()])
  }
})
</script>

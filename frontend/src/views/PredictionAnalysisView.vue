<template>
  <div class="container mx-auto px-4 py-8 max-w-7xl">
    <div class="flex items-center gap-3 mb-6">
      <router-link to="/admin" class="btn btn-ghost btn-sm">← Admin</router-link>
      <h1 class="text-3xl font-bold">📊 Prediction Analysis</h1>
    </div>

    <!-- Controls -->
    <div class="card bg-base-200 shadow mb-6">
      <div class="card-body p-4">
        <div class="flex flex-wrap gap-4 items-end">
          <!-- Org dropdown -->
          <div class="form-control">
            <label class="label py-1"><span class="label-text text-xs">Organization</span></label>
            <select v-model="filters.orgId" class="select select-bordered select-sm w-40" @change="onFilterChange">
              <option v-for="org in orgs" :key="org.id ?? 'all'" :value="org.id">{{ org.name }}</option>
            </select>
          </div>

          <!-- Min confidence -->
          <div class="form-control">
            <label class="label py-1"><span class="label-text text-xs">Min confidence</span></label>
            <select v-model.number="filters.minConfidence" class="select select-bordered select-sm w-36" @change="onFilterChange">
              <option :value="1">1 — Any</option>
              <option :value="2">2 — Medium+</option>
              <option :value="3">3 — High only</option>
            </select>
          </div>

          <!-- Min skill gap -->
          <div class="form-control">
            <label class="label py-1"><span class="label-text text-xs">Min skill gap</span></label>
            <input
              v-model.number="filters.minSkillDiff"
              type="number"
              min="0"
              step="0.5"
              class="input input-bordered input-sm w-28"
              @input="onFilterChange"
            />
          </div>

          <button class="btn btn-sm btn-ghost mt-5" @click="load" :disabled="loading">
            <span v-if="loading" class="loading loading-spinner loading-xs"></span>
            🔄
          </button>
        </div>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex justify-center py-16">
      <span class="loading loading-spinner loading-lg text-primary"></span>
    </div>

    <template v-else-if="data">
      <!-- Summary cards -->
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <div class="stat bg-base-200 rounded-xl shadow">
          <div class="stat-title text-xs">Overall Success Rate</div>
          <div class="stat-value text-primary text-3xl">{{ data.overall.success_rate }}%</div>
          <div class="stat-desc">{{ data.overall.correct }} / {{ data.overall.total_graded }} picks</div>
        </div>
        <div class="stat bg-base-200 rounded-xl shadow">
          <div class="stat-title text-xs">Total Graded</div>
          <div class="stat-value text-2xl">{{ data.overall.total_graded }}</div>
          <div class="stat-desc">Avg skill gap: {{ data.overall.avg_skill_diff }}</div>
        </div>
        <div class="stat bg-base-200 rounded-xl shadow">
          <div class="stat-title text-xs">Upset Success Rate</div>
          <div class="stat-value text-warning text-3xl">{{ data.overall.upset_rate }}%</div>
          <div class="stat-desc">{{ data.overall.upset_correct }} / {{ data.overall.upset_picks }} upset picks</div>
        </div>
        <div class="stat bg-base-200 rounded-xl shadow">
          <div class="stat-title text-xs">Best Confidence Level</div>
          <div class="stat-value text-success text-3xl">
            <template v-if="data.overall.best_confidence">
              {{ confidenceLabel(data.overall.best_confidence) }}
            </template>
            <template v-else>—</template>
          </div>
          <div class="stat-desc">
            <template v-if="data.overall.best_confidence">
              {{ data.overall.best_confidence_rate }}% success rate
            </template>
            <template v-else>No graded picks yet</template>
          </div>
        </div>
      </div>

      <!-- Weekly chart (CSS bar chart) -->
      <div v-if="data.weeks.length" class="card bg-base-200 shadow mb-6">
        <div class="card-body p-4">
          <h2 class="font-semibold mb-3">Weekly Success Rate</h2>
          <div class="overflow-x-auto">
            <!-- Simple SVG line chart -->
            <svg
              v-if="chartPoints.length > 1"
              :width="chartWidth"
              height="140"
              class="block"
              style="min-width: 300px"
            >
              <!-- Grid lines -->
              <line v-for="y in [0,25,50,75,100]" :key="y"
                :x1="chartPad" :y1="chartY(y)"
                :x2="chartWidth - 10" :y2="chartY(y)"
                stroke="#334155" stroke-width="1"
              />
              <text v-for="y in [0,25,50,75,100]" :key="'l'+y"
                :x="chartPad - 4" :y="chartY(y) + 4"
                text-anchor="end" font-size="10" fill="#64748b"
              >{{ y }}%</text>

              <!-- Line -->
              <polyline
                :points="chartPoints.map(p => `${p.x},${p.y}`).join(' ')"
                fill="none"
                stroke="#0d9488"
                stroke-width="2.5"
                stroke-linejoin="round"
              />

              <!-- Dots + tooltips -->
              <g v-for="(p, i) in chartPoints" :key="i">
                <circle :cx="p.x" :cy="p.y" r="5" fill="#0d9488" />
                <title>{{ p.label }}</title>
              </g>

              <!-- X labels -->
              <text v-for="(p, i) in chartPointsLabeled" :key="'xl'+i"
                :x="p.x" :y="130"
                text-anchor="middle" font-size="9" fill="#64748b"
              >{{ p.weekLabel }}</text>
            </svg>

            <!-- Only 1 data point: show simple message -->
            <div v-else class="text-sm text-base-content/50 py-4 text-center">
              Only one week of data — chart needs at least 2 weeks.
            </div>
          </div>
        </div>
      </div>

      <!-- Weekly breakdown table -->
      <div class="card bg-base-200 shadow mb-6">
        <div class="card-body p-4">
          <h2 class="font-semibold mb-3">Weekly Breakdown</h2>
          <div v-if="!data.weeks.length" class="text-sm text-base-content/50 py-4 text-center">
            No graded picks match the current filters.
          </div>
          <div v-else class="overflow-x-auto">
            <table class="table table-sm w-full text-sm">
              <thead>
                <tr>
                  <th>Week</th>
                  <th class="text-right">Games</th>
                  <th class="text-right">Correct</th>
                  <th class="text-right">Rate</th>
                  <th class="text-right">Avg Skill Gap</th>
                  <th class="text-right">Upsets</th>
                  <th class="text-right">Upset Rate</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="wk in data.weeks" :key="wk.week_start" class="hover">
                  <td class="font-mono text-xs">{{ wk.week_start }}</td>
                  <td class="text-right">{{ wk.total_graded }}</td>
                  <td class="text-right">{{ wk.correct }}</td>
                  <td class="text-right">
                    <span :class="rateColor(wk.success_rate)">{{ wk.success_rate }}%</span>
                  </td>
                  <td class="text-right">{{ wk.avg_skill_diff }}</td>
                  <td class="text-right">{{ wk.upset_picks }}</td>
                  <td class="text-right">
                    <span v-if="wk.upset_picks > 0" :class="rateColor(wk.upset_rate)">{{ wk.upset_rate }}%</span>
                    <span v-else class="text-base-content/30">—</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- By confidence breakdown -->
      <div class="card bg-base-200 shadow mb-6">
        <div class="card-body p-4">
          <h2 class="font-semibold mb-3">By Confidence Level</h2>
          <div class="space-y-3">
            <div v-for="c in [1, 2, 3]" :key="c" class="flex items-center gap-3">
              <div class="w-24 text-sm font-medium shrink-0">
                <span :class="confBadge(c)" class="badge badge-sm mr-1">{{ c }}</span>
                {{ ['Low', 'Medium', 'High'][c - 1] }}
              </div>
              <div class="w-16 text-right text-xs text-base-content/60 shrink-0">
                {{ data.overall.by_confidence[c]?.total ?? 0 }} picks
              </div>
              <div class="w-16 text-right text-xs shrink-0">
                {{ data.overall.by_confidence[c]?.correct ?? 0 }} correct
              </div>
              <div class="w-14 text-right text-sm font-semibold shrink-0" :class="rateColor(data.overall.by_confidence[c]?.rate ?? 0)">
                {{ data.overall.by_confidence[c]?.rate ?? 0 }}%
              </div>
              <!-- Visual bar -->
              <div class="flex-1 bg-base-300 rounded h-4 overflow-hidden">
                <div
                  class="h-full rounded transition-all duration-500"
                  :class="confBarColor(c)"
                  :style="{ width: (data.overall.by_confidence[c]?.rate ?? 0) + '%' }"
                ></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <div v-else-if="!loading" class="text-center py-16 text-base-content/50">
      No data available.
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useApiClient } from '@/api/client'

const api = useApiClient()

const filters = ref({
  orgId: null,
  minConfidence: 1,
  minSkillDiff: 0,
})

const data = ref(null)
const loading = ref(false)
const orgs = ref([{ id: null, name: 'All Orgs' }])

let debounceTimer = null
function onFilterChange() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(load, 300)
}

async function load() {
  loading.value = true
  try {
    const params = new URLSearchParams()
    params.set('min_confidence', filters.value.minConfidence)
    params.set('min_skill_diff', filters.value.minSkillDiff)
    if (filters.value.orgId !== null) params.set('org_id', filters.value.orgId)

    const { data: resp } = await api.get(`/api/admin/prediction-analysis?${params}`)
    data.value = resp

    // Merge orgs from response
    if (resp.orgs?.length) {
      orgs.value = resp.orgs
    }
  } catch (e) {
    console.error('Failed to load prediction analysis', e)
  } finally {
    loading.value = false
  }
}

onMounted(load)

// ── Chart helpers ─────────────────────────────────────────────────────────────
const chartPad = 36
const chartWidth = computed(() => {
  if (!data.value?.weeks?.length) return 400
  return Math.max(400, data.value.weeks.length * 60 + chartPad + 20)
})

function chartY(rate) {
  // rate 0–100, SVG height 120, top pad 8, bottom pad 20
  const h = 120
  const top = 8
  return top + (1 - rate / 100) * h
}

const chartPoints = computed(() => {
  if (!data.value?.weeks?.length) return []
  const sorted = [...data.value.weeks].sort((a, b) => a.week_start.localeCompare(b.week_start))
  const n = sorted.length
  return sorted.map((wk, i) => ({
    x: chartPad + (n === 1 ? (chartWidth.value - chartPad - 10) / 2 : i * ((chartWidth.value - chartPad - 10) / (n - 1))),
    y: chartY(wk.success_rate),
    label: `${wk.week_start}: ${wk.correct}/${wk.total_graded} (${wk.success_rate}%)`,
    weekLabel: wk.week_start.slice(5), // MM-DD
  }))
})

// Only show X labels for a subset to avoid overlap
const chartPointsLabeled = computed(() => {
  const pts = chartPoints.value
  if (pts.length <= 8) return pts
  return pts.filter((_, i) => i % Math.ceil(pts.length / 8) === 0 || i === pts.length - 1)
})

// ── Style helpers ─────────────────────────────────────────────────────────────
function rateColor(rate) {
  if (rate >= 65) return 'text-success'
  if (rate >= 50) return 'text-warning'
  return 'text-error'
}

function confidenceLabel(c) {
  return { 1: '1 – Low', 2: '2 – Med', 3: '3 – High' }[c] ?? String(c)
}

function confBadge(c) {
  return { 1: 'badge-ghost', 2: 'badge-warning', 3: 'badge-success' }[c] ?? 'badge-ghost'
}

function confBarColor(c) {
  return { 1: 'bg-base-content/30', 2: 'bg-warning', 3: 'bg-success' }[c] ?? 'bg-primary'
}
</script>

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
      <div class="grid grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
        <div class="stat bg-base-200 rounded-xl shadow">
          <div class="stat-title text-xs">Overall Success Rate</div>
          <div class="stat-value text-primary text-3xl">{{ data.overall.rate }}%</div>
          <div class="stat-desc">{{ data.overall.correct }} / {{ data.overall.total }} games</div>
        </div>
        <div class="stat bg-base-200 rounded-xl shadow">
          <div class="stat-title text-xs">Total Graded</div>
          <div class="stat-value text-2xl">{{ data.overall.total }}</div>
          <div class="stat-desc">Games with final scores</div>
        </div>
        <div class="stat bg-base-200 rounded-xl shadow">
          <div class="stat-title text-xs">Best Skill Gap Bucket</div>
          <div class="stat-value text-success text-2xl">
            <template v-if="bestBucket">{{ bestBucket.label }}</template>
            <template v-else>—</template>
          </div>
          <div class="stat-desc">
            <template v-if="bestBucket">{{ bestBucket.rate }}% ({{ bestBucket.total }} games)</template>
            <template v-else>Not enough data</template>
          </div>
        </div>
      </div>

      <!-- Weekly chart (SVG line chart) -->
      <div v-if="data.weeks.length" class="card bg-base-200 shadow mb-6">
        <div class="card-body p-4">
          <h2 class="font-semibold mb-3">Weekly Success Rate</h2>
          <div class="overflow-x-auto">
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
            No graded games match the current filters.
          </div>
          <div v-else class="overflow-x-auto">
            <table class="table table-sm w-full text-sm">
              <thead>
                <tr>
                  <th>Week</th>
                  <th class="text-right">Games</th>
                  <th class="text-right">Correct</th>
                  <th class="text-right">Rate</th>
                  <th class="text-right">Avg Skill Diff</th>
                  <th class="text-right">Upsets</th>
                  <th class="text-right">Upset Rate</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="wk in data.weeks" :key="wk.week_start" class="hover">
                  <td class="font-mono text-xs">{{ wk.week_start }}</td>
                  <td class="text-right">{{ wk.total }}</td>
                  <td class="text-right">{{ wk.correct }}</td>
                  <td class="text-right">
                    <span :class="rateColor(wk.rate)">{{ wk.rate }}%</span>
                  </td>
                  <td class="text-right">{{ wk.avg_skill_diff }}</td>
                  <td class="text-right">{{ wk.upsets_total }}</td>
                  <td class="text-right">
                    <span v-if="wk.upsets_total > 0" :class="rateColor(upsetRate(wk))">
                      {{ upsetRate(wk) }}%
                    </span>
                    <span v-else class="text-base-content/30">—</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- By skill gap breakdown -->
      <div class="card bg-base-200 shadow mb-6">
        <div class="card-body p-4">
          <h2 class="font-semibold mb-3">By Skill Gap</h2>
          <div class="overflow-x-auto">
            <table class="table table-sm w-full text-sm">
              <thead>
                <tr>
                  <th>Skill Gap</th>
                  <th class="text-right">Games</th>
                  <th class="text-right">Correct</th>
                  <th class="text-right">Rate</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="bk in bucketOrder" :key="bk" class="hover">
                  <td class="font-mono text-sm font-medium">{{ bk }}</td>
                  <td class="text-right">{{ data.overall.by_skill_diff_bucket[bk]?.total ?? 0 }}</td>
                  <td class="text-right">{{ data.overall.by_skill_diff_bucket[bk]?.correct ?? 0 }}</td>
                  <td class="text-right">
                    <span :class="rateColor(data.overall.by_skill_diff_bucket[bk]?.rate ?? 0)">
                      {{ data.overall.by_skill_diff_bucket[bk]?.rate ?? 0 }}%
                    </span>
                  </td>
                  <td class="w-40">
                    <div class="bg-base-300 rounded h-4 overflow-hidden">
                      <div
                        class="h-full rounded transition-all duration-500 bg-primary"
                        :style="{ width: (data.overall.by_skill_diff_bucket[bk]?.rate ?? 0) + '%' }"
                      ></div>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
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

const bucketOrder = ['0-5', '5-10', '10-20', '20+']

const filters = ref({
  orgId: null,
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

// Best bucket: highest rate with at least 3 games
const bestBucket = computed(() => {
  if (!data.value?.overall?.by_skill_diff_bucket) return null
  const buckets = data.value.overall.by_skill_diff_bucket
  let best = null
  for (const bk of bucketOrder) {
    const b = buckets[bk]
    if (!b || b.total < 3) continue
    if (!best || b.rate > best.rate) {
      best = { label: bk, ...b }
    }
  }
  return best
})

function upsetRate(wk) {
  if (!wk.upsets_total) return 0
  return Math.round(wk.upsets_correct / wk.upsets_total * 1000) / 10
}

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
    y: chartY(wk.rate),
    label: `${wk.week_start}: ${wk.correct}/${wk.total} (${wk.rate}%)`,
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
</script>

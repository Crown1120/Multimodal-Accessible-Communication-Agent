<script setup lang="ts">
import { computed } from 'vue'

import BIcon from '@/components/BIcon.vue'

const props = defineProps<{
  payload: Record<string, unknown>
}>()

// ---- SVG 平面图参数 ----
const VB_W = 340
const VB_H = 196
const PAD = 24

interface Pt {
  x: number
  y: number
}
interface POI {
  name: string
  coord: [number, number]
  floor: number
}

const originName = computed<string>(() => (props.payload.origin as string) ?? '大厅入口')
const destName = computed<string>(() => (props.payload.destination as string) ?? '目的地')

const pois = computed<POI[]>(() => (props.payload.pois as POI[]) ?? [])
const pathCoords = computed<[number, number][]>(
  () => (props.payload.path as [number, number][]) ?? [],
)
const originCoord = computed<[number, number] | undefined>(
  () => (props.payload.origin_coord as [number, number] | undefined) ?? undefined,
)
const destCoord = computed<[number, number] | undefined>(
  () => (props.payload.dest_coord as [number, number] | undefined) ?? undefined,
)

// 将经纬度归一化到 SVG 视口（纬度朝上，y 翻转）
function normalize(pts: [number, number][]): ((x: number, y: number) => Pt) | null {
  if (pts.length === 0) return null
  let minX = Infinity
  let maxX = -Infinity
  let minY = Infinity
  let maxY = -Infinity
  for (const [x, y] of pts) {
    minX = Math.min(minX, x)
    maxX = Math.max(maxX, x)
    minY = Math.min(minY, y)
    maxY = Math.max(maxY, y)
  }
  if (maxX - minX < 1e-6) {
    maxX += 1e-6
    minX -= 1e-6
  }
  if (maxY - minY < 1e-6) {
    maxY += 1e-6
    minY -= 1e-6
  }
  const scale = Math.min((VB_W - PAD * 2) / (maxX - minX), (VB_H - PAD * 2) / (maxY - minY))
  const cx = (minX + maxX) / 2
  const cy = (minY + maxY) / 2
  return (x: number, y: number): Pt => ({
    x: VB_W / 2 + (x - cx) * scale,
    y: VB_H / 2 - (y - cy) * scale,
  })
}

// 收集所有需要绘制的点（路径 + 起点 + 终点 + 全部科室）
const allPts = computed<[number, number][]>(() => {
  const list: [number, number][] = []
  for (const p of pathCoords.value) list.push(p)
  if (originCoord.value) list.push(originCoord.value)
  if (destCoord.value) list.push(destCoord.value)
  for (const p of pois.value) list.push(p.coord)
  return list
})

const mapFn = computed(() => normalize(allPts.value))
const hasMap = computed(() => Boolean(mapFn.value))

const pathD = computed(() => {
  const m = mapFn.value
  if (!m || pathCoords.value.length < 2) return ''
  return pathCoords.value
    .map(([x, y], i) => {
      const p = m(x, y)
      return `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`
    })
    .join(' ')
})

const originPt = computed(() =>
  mapFn.value && originCoord.value ? mapFn.value(originCoord.value[0], originCoord.value[1]) : null,
)
const destPt = computed(() =>
  mapFn.value && destCoord.value ? mapFn.value(destCoord.value[0], destCoord.value[1]) : null,
)

// 电梯中转点（取路线折线中间点）
const elvPt = computed(() => {
  const m = mapFn.value
  if (!m || pathCoords.value.length < 3) return null
  const [x, y] = pathCoords.value[Math.floor(pathCoords.value.length / 2)]
  return m(x, y)
})

// 科室节点：终点已由「终」标记覆盖，不再重复画；标签左右交替放置避免重叠
const poiPts = computed(() => {
  const m = mapFn.value
  if (!m) return []
  return pois.value
    .filter((p) => p.name !== destName.value)
    .map((p, i) => {
      const pt = m(p.coord[0], p.coord[1])
      return { ...p, pt, side: i % 2 === 0 ? 1 : -1 }
    })
})

const steps = computed<string[]>(() => (props.payload.steps as string[]) ?? [])
const floor = computed<number | undefined>(() => props.payload.floor as number | undefined)
</script>

<template>
  <div class="map-route-widget">
    <div class="head">
      <span class="head-icon">
        <BIcon name="map" :size="15" />
      </span>
      <span class="head-title">路线规划</span>
      <span v-if="floor" class="head-sub">{{ floor }} 楼</span>
    </div>

    <div class="endpoints">
      <div class="endpoint">
        <span class="endpoint-tag from">起</span>
        <span class="endpoint-name">{{ originName }}</span>
      </div>
      <span class="arrow"><BIcon name="arrowRight" :size="14" /></span>
      <div class="endpoint">
        <span class="endpoint-tag to">终</span>
        <span class="endpoint-name">{{ destName }}</span>
      </div>
    </div>

    <!-- SVG 室内平面图 + 路线线 -->
    <div v-if="hasMap" class="map-wrap">
      <svg
        :viewBox="`0 0 ${VB_W} ${VB_H}`"
        class="floor-map"
        role="img"
        aria-label="室内平面路线示意图"
      >
        <defs>
          <linearGradient id="floorGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stop-color="#eef5ff" />
            <stop offset="1" stop-color="#dfeafa" />
          </linearGradient>
          <marker
            id="routeArrow"
            markerWidth="9"
            markerHeight="9"
            refX="7.5"
            refY="3.5"
            orient="auto"
            markerUnits="strokeWidth"
          >
            <path d="M0,0 L8,3.5 L0,7 z" fill="#2563eb" />
          </marker>
        </defs>

        <!-- 楼层地面 -->
        <rect x="0" y="0" :width="VB_W" :height="VB_H" class="floor-bg" rx="12" />
        <!-- 网格 -->
        <g class="grid">
          <line
            v-for="i in 6"
            :key="'v' + i"
            :x1="(VB_W / 7) * i"
            y1="0"
            :x2="(VB_W / 7) * i"
            :y2="VB_H"
          />
          <line
            v-for="j in 4"
            :key="'h' + j"
            x1="0"
            :y1="(VB_H / 5) * j"
            :x2="VB_W"
            :y2="(VB_H / 5) * j"
          />
        </g>
        <!-- 示意图角标 -->
        <text x="14" y="20" class="map-caption">平面示意图</text>

        <!-- 全部科室节点（终点除外，由「终」标记覆盖） -->
        <g v-for="(p, i) in poiPts" :key="'p' + i" class="poi">
          <circle :cx="p.pt.x" :cy="p.pt.y" r="4.2" class="poi-dot" />
          <text
            :x="p.pt.x + p.side * 7"
            :y="p.pt.y + 3"
            :text-anchor="p.side === 1 ? 'start' : 'end'"
            class="poi-label"
          >
            {{ p.name }}
          </text>
        </g>

        <!-- 电梯中转点 -->
        <g v-if="elvPt" class="elevator">
          <rect :x="elvPt.x - 9" :y="elvPt.y - 9" width="18" height="18" rx="4" />
          <text :x="elvPt.x" :y="elvPt.y + 3" class="elevator-text">梯</text>
        </g>

        <!-- 路线：光晕 + 主线（虚线流动）+ 终点箭头 -->
        <path v-if="pathD" :d="pathD" class="route-glow" />
        <path v-if="pathD" :d="pathD" class="route-line" marker-end="url(#routeArrow)" />

        <!-- 起点 -->
        <g v-if="originPt" class="marker from-marker">
          <circle :cx="originPt.x" :cy="originPt.y" r="10" class="halo pulse" />
          <circle :cx="originPt.x" :cy="originPt.y" r="6" />
          <text :x="originPt.x" :y="originPt.y + 2.6" class="marker-text">起</text>
        </g>
        <!-- 终点 -->
        <g v-if="destPt" class="marker to-marker">
          <circle :cx="destPt.x" :cy="destPt.y" r="11" class="halo pulse" />
          <circle :cx="destPt.x" :cy="destPt.y" r="6.5" />
          <text :x="destPt.x" :y="destPt.y + 2.6" class="marker-text">终</text>
        </g>

        <!-- 图例 -->
        <g class="legend" transform="translate(8, 178)">
          <circle cx="5" cy="3" r="3" class="lg from" />
          <text x="12" y="6" class="legend-text">起点</text>
          <circle cx="52" cy="3" r="3" class="lg to" />
          <text x="59" y="6" class="legend-text">终点</text>
          <line x1="102" y1="3" x2="122" y2="3" class="lg line" />
          <text x="126" y="6" class="legend-text">路线</text>
        </g>
      </svg>
    </div>

    <ol class="steps">
      <li v-for="(s, i) in steps" :key="i">
        <span class="step-num">{{ i + 1 }}</span>
        <span class="step-text">{{ s }}</span>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.map-route-widget {
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  box-shadow: var(--shadow-xs);
  overflow: hidden;
  position: relative;
}
.map-route-widget::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: var(--color-primary-gradient);
  z-index: 1;
}

.head {
  display: flex;
  align-items: center;
  gap: 7px;
  font-weight: 700;
  padding: 12px 12px 0;
  color: var(--color-text);
  font-size: 0.94em;
}
.head-icon {
  width: 26px;
  height: 26px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-primary-soft);
  color: var(--color-primary);
}
.head-sub {
  margin-left: auto;
  font-size: 0.78em;
  font-weight: 600;
  color: var(--color-text-muted);
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  padding: 2px 9px;
  border-radius: var(--radius-pill);
}

.endpoints {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px 8px;
}
.endpoint {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 9px;
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: 10px;
}
.endpoint-tag {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 0.66em;
  font-weight: 700;
  color: #fff;
  flex-shrink: 0;
}
.endpoint-tag.from {
  background: var(--color-accent);
}
.endpoint-tag.to {
  background: var(--color-primary);
}
.endpoint-name {
  font-size: 0.86em;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.arrow {
  color: var(--color-primary);
  flex-shrink: 0;
}

/* ---- 平面图 ---- */
.map-wrap {
  padding: 0 12px 6px;
}
.floor-map {
  display: block;
  width: 100%;
  height: auto;
  border-radius: 12px;
  border: 1px solid rgba(37, 99, 235, 0.14);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.8),
    0 3px 10px rgba(37, 99, 235, 0.08);
}
.floor-bg {
  fill: url(#floorGrad);
}
.grid line {
  stroke: rgba(37, 99, 235, 0.07);
  stroke-width: 1;
}
.map-caption {
  font-size: 9px;
  fill: rgba(59, 90, 130, 0.55);
  font-weight: 600;
  letter-spacing: 1px;
}

.poi-dot {
  fill: #fff;
  stroke: rgba(90, 125, 165, 0.55);
  stroke-width: 1.6;
}
.poi-label {
  font-size: 10px;
  fill: rgba(40, 70, 105, 0.92);
  font-weight: 600;
  paint-order: stroke;
  stroke: #eef4ff;
  stroke-width: 3px;
  stroke-linejoin: round;
  user-select: none;
}

/* 电梯 */
.elevator rect {
  fill: rgba(148, 163, 184, 0.35);
  stroke: rgba(100, 116, 139, 0.6);
  stroke-width: 1.2;
}
.elevator-text {
  font-size: 9px;
  font-weight: 800;
  fill: #475569;
  text-anchor: middle;
  dominant-baseline: middle;
  user-select: none;
}

/* 路线 */
.route-glow {
  fill: none;
  stroke: rgba(37, 99, 235, 0.22);
  stroke-width: 8;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.route-line {
  fill: none;
  stroke: #2563eb;
  stroke-width: 3;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-dasharray: 7 5;
  animation: routeDash 1.1s linear infinite;
}
@keyframes routeDash {
  to {
    stroke-dashoffset: -12;
  }
}

/* 起终点 */
.marker .halo {
  fill: rgba(80, 150, 255, 0.28);
}
.marker .halo.pulse {
  transform-box: fill-box;
  transform-origin: center;
  animation: markerPulse 1.6s ease-out infinite;
}
@keyframes markerPulse {
  0% {
    transform: scale(0.75);
    opacity: 0.95;
  }
  70% {
    transform: scale(1.45);
    opacity: 0;
  }
  100% {
    transform: scale(1.45);
    opacity: 0;
  }
}
.marker circle:not(.halo) {
  stroke: #fff;
  stroke-width: 1.8;
  filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.25));
}
.from-marker circle:not(.halo) {
  fill: #10b981;
}
.to-marker circle:not(.halo) {
  fill: #2563eb;
}
.marker-text {
  font-size: 8px;
  fill: #fff;
  font-weight: 800;
  text-anchor: middle;
  dominant-baseline: middle;
  user-select: none;
}

/* 图例 */
.legend {
  font-size: 8px;
}
.legend .lg {
  stroke-width: 1.6;
}
.lg.from {
  fill: #10b981;
}
.lg.to {
  fill: #2563eb;
}
.lg.line {
  stroke: #2563eb;
  stroke-dasharray: 3 2;
}
.legend-text {
  fill: rgba(60, 90, 125, 0.85);
  font-weight: 600;
}

.steps {
  margin: 0;
  padding: 8px 12px 12px;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
  border-top: 1px dashed var(--color-border);
}
.steps li {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 0.86em;
  line-height: 1.5;
}
.step-num {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--color-primary-soft);
  color: var(--color-primary);
  font-size: 0.7em;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 1px;
}
.step-text {
  flex: 1;
}
</style>

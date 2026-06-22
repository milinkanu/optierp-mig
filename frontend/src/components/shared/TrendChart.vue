<script setup lang="ts">
// Lightweight dependency-free line/area trend chart (SVG). The X scale is
// stretched to fill width (preserveAspectRatio="none"), so any text — the month
// labels AND the Y-axis tick labels — renders as HTML around the SVG, never
// inside it, so it can't be horizontally distorted. Horizontal gridlines DO live
// in the SVG (a horizontal line survives X-stretching) with a non-scaling stroke.

import { computed } from "vue";
import { formatCompact } from "@/utils/format";

const props = withDefaults(
  defineProps<{
    points: { label: string; value: number }[];
    height?: number;
    valueFormat?: "int" | "currency";
    currency?: string;
  }>(),
  { height: 220, valueFormat: "int", currency: "INR" },
);

const VB_W = 1000;
const PAD_TOP = 16;
const PAD_BOTTOM = 8;

// "Nice" rounded number (Heckbert) — turns a raw range/step into 1/2/5×10ⁿ.
function niceNum(range: number, round: boolean): number {
  const exp = Math.floor(Math.log10(range || 1));
  const base = 10 ** exp;
  const frac = range / base;
  const nf = round
    ? frac < 1.5 ? 1 : frac < 3 ? 2 : frac < 7 ? 5 : 10
    : frac <= 1 ? 1 : frac <= 2 ? 2 : frac <= 5 ? 5 : 10;
  return nf * base;
}

// Evenly spaced, nicely rounded Y ticks from 0 up to a max ≥ the data max. For
// counts (valueFormat !== "currency") the step is forced to a whole number so we
// never show fractional tick labels like 0.5 entries.
const ticks = computed<number[]>(() => {
  const dataMax = Math.max(1, ...props.points.map((p) => p.value));
  let step = niceNum(niceNum(dataMax, false) / 4, true);
  if (props.valueFormat !== "currency") step = Math.max(1, Math.round(step));
  const top = Math.ceil(dataMax / step) * step;
  const out: number[] = [];
  for (let v = 0; v <= top + step / 2; v += step) out.push(Number(v.toFixed(6)));
  return out;
});

const niceMax = computed(() => ticks.value[ticks.value.length - 1] || 1);

function yFor(value: number): number {
  const innerH = props.height - PAD_TOP - PAD_BOTTOM;
  return PAD_TOP + innerH - (value / niceMax.value) * innerH;
}

const coords = computed(() => {
  const n = props.points.length;
  const step = n > 1 ? VB_W / (n - 1) : 0;
  return props.points.map((p, i) => ({
    x: n > 1 ? i * step : VB_W / 2,
    y: yFor(p.value),
  }));
});

const linePath = computed(() =>
  coords.value.map((c, i) => `${i ? "L" : "M"}${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(" "),
);

const areaPath = computed(() => {
  if (!coords.value.length) return "";
  const baseY = props.height - PAD_BOTTOM;
  const pts = coords.value;
  return (
    `M${pts[0].x.toFixed(1)},${baseY} ` +
    pts.map((c) => `L${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(" ") +
    ` L${pts[pts.length - 1].x.toFixed(1)},${baseY} Z`
  );
});

function tickLabel(value: number): string {
  return formatCompact(value, props.valueFormat === "currency" ? props.currency : null);
}
</script>

<template>
  <div class="flex items-start">
    <!-- Y axis: HTML labels positioned to line up with the SVG gridlines -->
    <div class="relative w-14 shrink-0" :style="{ height: `${height}px` }">
      <span
        v-for="t in ticks"
        :key="t"
        class="absolute right-2 -translate-y-1/2 whitespace-nowrap text-[11px] text-gray-400"
        :style="{ top: `${yFor(t)}px` }"
      >
        {{ tickLabel(t) }}
      </span>
    </div>

    <!-- plot area -->
    <div class="min-w-0 flex-1">
      <svg
        :viewBox="`0 0 ${VB_W} ${height}`"
        :height="height"
        width="100%"
        preserveAspectRatio="none"
        class="block"
      >
        <!-- horizontal gridlines, one per tick -->
        <line
          v-for="t in ticks"
          :key="t"
          x1="0"
          :y1="yFor(t)"
          :x2="VB_W"
          :y2="yFor(t)"
          :stroke="t === 0 ? 'rgb(209 213 219)' : 'rgb(243 244 246)'"
          stroke-width="1"
          vector-effect="non-scaling-stroke"
        />
        <path :d="areaPath" fill="rgb(236 72 153 / 0.08)" />
        <path
          :d="linePath"
          fill="none"
          stroke="rgb(236 72 153)"
          stroke-width="2"
          vector-effect="non-scaling-stroke"
          stroke-linejoin="round"
        />
      </svg>
      <div class="mt-1 flex justify-between px-1 text-[11px] text-gray-400">
        <span v-for="(p, i) in points" :key="i">{{ p.label }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// Lightweight dependency-free line/area trend chart (SVG). Labels render as
// HTML beneath the SVG so non-uniform x-scaling never distorts text.

import { computed } from "vue";

const props = withDefaults(
  defineProps<{ points: { label: string; value: number }[]; height?: number }>(),
  { height: 220 },
);

const VB_W = 1000;
const PAD_TOP = 16;
const PAD_BOTTOM = 8;

const max = computed(() => Math.max(1, ...props.points.map((p) => p.value)));

const coords = computed(() => {
  const n = props.points.length;
  const innerH = props.height - PAD_TOP - PAD_BOTTOM;
  const step = n > 1 ? VB_W / (n - 1) : 0;
  return props.points.map((p, i) => ({
    x: n > 1 ? i * step : VB_W / 2,
    y: PAD_TOP + innerH - (p.value / max.value) * innerH,
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
</script>

<template>
  <div>
    <svg
      :viewBox="`0 0 ${VB_W} ${height}`"
      :height="height"
      width="100%"
      preserveAspectRatio="none"
      class="block"
    >
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
</template>

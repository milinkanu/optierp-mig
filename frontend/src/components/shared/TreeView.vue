<script setup lang="ts">
// Generic tree view for is_tree DocTypes — renders the nested structure from
// /registry/{doctype}/tree. Reparenting is done by editing a node's parent
// field in the form (the engine maintains the ltree path).

import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { api } from "@/api/client";

interface TreeNode {
  id: string;
  is_group?: boolean;
  children: TreeNode[];
  [key: string]: unknown;
}

const props = defineProps<{ doctype: string; titleField: string }>();
const router = useRouter();

const flatRows = ref<{ node: TreeNode; depth: number }[]>([]);
const loading = ref(false);

function flatten(nodes: TreeNode[], depth: number, acc: { node: TreeNode; depth: number }[]) {
  for (const node of nodes) {
    acc.push({ node, depth });
    if (node.children?.length) flatten(node.children, depth + 1, acc);
  }
  return acc;
}

async function load(): Promise<void> {
  loading.value = true;
  try {
    const data = (await api.get<TreeNode[]>(`/registry/${props.doctype}/tree`)).data;
    flatRows.value = flatten(data, 0, []);
  } finally {
    loading.value = false;
  }
}

onMounted(load);

function edit(node: TreeNode): void {
  void router.push(`/m/${props.doctype}/${node.id}`);
}
</script>

<template>
  <div class="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
    <p v-if="loading" class="px-4 py-8 text-center text-sm text-gray-400">Loading…</p>
    <p v-else-if="flatRows.length === 0" class="px-4 py-8 text-center text-sm text-gray-400">
      No records found
    </p>
    <ul v-else class="divide-y divide-gray-100">
      <li
        v-for="row in flatRows"
        :key="row.node.id"
        class="cursor-pointer px-4 py-2.5 text-sm text-gray-700 hover:bg-gray-50"
        @click="edit(row.node)"
      >
        <span :style="{ paddingLeft: row.depth * 20 + 'px' }">
          <span v-if="row.node.is_group" class="mr-1 text-gray-400" aria-hidden="true">▸</span>
          {{ row.node[titleField] }}
        </span>
      </li>
    </ul>
  </div>
</template>

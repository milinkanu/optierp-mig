<script setup lang="ts">
// "Data Entry" control for transaction line items. Manual entry is the grid
// itself; this adds the other two modes the user asked for:
//   • Import — from a CSV template or a Tally CSV export
//   • OCR    — upload an invoice/PO; extraction connects via API (future)
// Emits parsed rows; the parent maps them to catalog items.

import { ref } from "vue";

export interface ImportedRow {
  item_code: string;
  qty: number;
  rate?: number;
}

const emit = defineEmits<{ import: [rows: ImportedRow[]] }>();

const open = ref(false);
const mode = ref<"csv" | "tally" | "ocr">("csv");
const note = ref<string | null>(null);

function close(): void {
  open.value = false;
  note.value = null;
}

// Split one CSV line, honouring double-quoted fields (with "" escapes) so an
// embedded comma stays in a single cell.
function splitCsvLine(line: string): string[] {
  const out: string[] = [];
  let cur = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"') {
        if (line[i + 1] === '"') { cur += '"'; i += 1; }
        else inQuotes = false;
      } else cur += ch;
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === ",") {
      out.push(cur);
      cur = "";
    } else {
      cur += ch;
    }
  }
  out.push(cur);
  return out.map((c) => c.trim());
}

// Header row decides columns; expects item_code, with optional qty, rate.
function parseCsv(text: string): ImportedRow[] {
  const clean = text.replace(/^﻿/, ""); // strip UTF-8 BOM (Excel/Tally exports)
  const lines = clean.split(/\r?\n/).filter((l) => l.trim() !== "");
  if (lines.length < 2) return [];
  const header = splitCsvLine(lines[0]).map((h) => h.toLowerCase());
  const ci = header.indexOf("item_code");
  const qi = header.indexOf("qty");
  const ri = header.indexOf("rate");
  if (ci === -1) return [];
  const rows: ImportedRow[] = [];
  for (const line of lines.slice(1)) {
    const cells = splitCsvLine(line);
    const item_code = cells[ci];
    if (!item_code) continue;
    rows.push({
      item_code,
      qty: qi !== -1 && cells[qi] ? Number(cells[qi]) : 1,
      rate: ri !== -1 && cells[ri] ? Number(cells[ri]) : undefined,
    });
  }
  return rows;
}

async function onFile(e: Event): Promise<void> {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  const text = await file.text();
  const rows = parseCsv(text);
  input.value = ""; // reset so re-selecting the same file fires change again
  if (rows.length === 0) {
    note.value = "No valid rows found. The file needs an `item_code` column (with optional `qty`, `rate`).";
    return;
  }
  emit("import", rows);
  note.value = null;
  close();
}

function downloadTemplate(): void {
  const csv = "item_code,qty,rate\nITEM-001,1,100\n";
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = "items-template.csv";
  a.click();
  URL.revokeObjectURL(url);
}
</script>

<template>
  <div class="relative inline-block">
    <button type="button" class="btn-secondary gap-1" @click="open = !open">
      Import <span class="text-xs text-gray-400">▾</span>
    </button>

    <div v-if="open" class="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-4" @click.self="close">
      <div class="w-full max-w-lg rounded-lg bg-white shadow-xl">
        <div class="flex items-center justify-between border-b border-gray-200 px-5 py-3">
          <h3 class="text-sm font-semibold text-gray-900">Import items</h3>
          <button type="button" class="text-gray-400 hover:text-gray-700" @click="close">✕</button>
        </div>

        <!-- mode tabs -->
        <div class="flex gap-4 border-b border-gray-200 px-5">
          <button
            v-for="m in (['csv', 'tally', 'ocr'] as const)"
            :key="m"
            type="button"
            class="-mb-px border-b-2 py-2 text-sm font-medium capitalize"
            :class="mode === m ? 'border-primary text-primary' : 'border-transparent text-gray-500 hover:text-gray-700'"
            @click="mode = m; note = null"
          >
            {{ m === 'ocr' ? 'OCR' : m }}
          </button>
        </div>

        <div class="space-y-3 px-5 py-4 text-sm">
          <!-- CSV -->
          <template v-if="mode === 'csv'">
            <p class="text-gray-600">Upload a CSV with columns <code>item_code, qty, rate</code>.</p>
            <button type="button" class="text-primary hover:underline" @click="downloadTemplate">
              ↓ Download template
            </button>
            <input type="file" accept=".csv,text/csv" class="block w-full text-sm" @change="onFile" />
          </template>

          <!-- Tally -->
          <template v-else-if="mode === 'tally'">
            <p class="text-gray-600">
              In Tally: <em>Gateway of Tally → Display → Export</em> to <strong>CSV</strong>, then upload it here
              (same <code>item_code, qty, rate</code> columns).
            </p>
            <input type="file" accept=".csv,text/csv" class="block w-full text-sm" @change="onFile" />
            <p class="text-xs text-gray-400">Direct Tally XML import connects via API (coming soon).</p>
          </template>

          <!-- OCR -->
          <template v-else>
            <p class="text-gray-600">Upload a scanned invoice or PO; line items are extracted automatically.</p>
            <input type="file" accept="image/*,application/pdf" class="block w-full text-sm" disabled />
            <button type="button" class="btn-primary" disabled>Extract</button>
            <p class="text-xs text-gray-400">OCR extraction connects via API (coming soon).</p>
          </template>

          <p v-if="note" class="text-sm text-red-600">{{ note }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

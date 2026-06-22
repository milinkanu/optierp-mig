<script setup lang="ts">
// Emails a document as a PDF attachment via POST /print/{doctype}/{id}/email.
// Recipient is optional — left blank, the backend uses the party's saved email.
import { ref } from "vue";
import { api } from "@/api/client";
import type { ErrorEnvelope } from "@/types/core";

const props = defineProps<{ doctype: string; docId: string; docName?: string; label?: string }>();

interface EmailSendResult {
  status: string;
  to: string[];
  email_log_id: string;
  error: string | null;
}

const open = ref(false);
const to = ref("");
const subject = ref("");
const body = ref("");
const sending = ref(false);
const result = ref<{ ok: boolean; msg: string } | null>(null);

function openDialog(): void {
  to.value = "";
  subject.value = "";
  body.value = "";
  result.value = null;
  open.value = true;
}

async function send(): Promise<void> {
  sending.value = true;
  result.value = null;
  try {
    const payload: { to?: string[]; subject?: string; body?: string } = {};
    const recipients = to.value.split(",").map((s) => s.trim()).filter(Boolean);
    if (recipients.length) payload.to = recipients;
    if (subject.value.trim()) payload.subject = subject.value.trim();
    if (body.value.trim()) payload.body = body.value;
    const path = `/print/${encodeURIComponent(props.doctype)}/${props.docId}/email`;
    const resp = await api.post<EmailSendResult>(path, payload);
    if (resp.data.status === "Sent") {
      result.value = { ok: true, msg: `Sent to ${resp.data.to.join(", ")}` };
    } else {
      result.value = { ok: false, msg: resp.data.error || "Delivery failed." };
    }
  } catch (e) {
    result.value = { ok: false, msg: (e as ErrorEnvelope).detail || "Failed to send." };
  } finally {
    sending.value = false;
  }
}
</script>

<template>
  <button type="button" class="btn-secondary" @click="openDialog">{{ label || "Send by Email" }}</button>
  <div
    v-if="open"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
    @click.self="open = false"
  >
    <div class="w-full max-w-md overflow-hidden rounded-lg bg-white shadow-xl">
      <div class="flex items-center justify-between border-b border-gray-200 px-5 py-3">
        <h3 class="text-sm font-semibold text-gray-900">Email {{ docName || doctype }}</h3>
        <button type="button" class="btn-secondary" @click="open = false">Close</button>
      </div>
      <div class="space-y-3 px-5 py-4">
        <label class="block text-sm">
          <span class="text-gray-600">To</span>
          <input
            v-model="to"
            type="text"
            class="form-input mt-1 w-full"
            placeholder="Leave blank to use the party's saved email"
          />
        </label>
        <label class="block text-sm">
          <span class="text-gray-600">Subject</span>
          <input v-model="subject" type="text" class="form-input mt-1 w-full" placeholder="Auto-generated if blank" />
        </label>
        <label class="block text-sm">
          <span class="text-gray-600">Message</span>
          <textarea
            v-model="body"
            rows="4"
            class="form-input mt-1 w-full"
            placeholder="Auto-generated if blank"
          ></textarea>
        </label>
        <p v-if="result" class="text-sm" :class="result.ok ? 'text-green-600' : 'text-red-600'">
          {{ result.msg }}
        </p>
      </div>
      <div class="flex justify-end gap-2 border-t border-gray-200 px-5 py-3">
        <button type="button" class="btn-secondary" @click="open = false">Cancel</button>
        <button type="button" class="btn-primary" :disabled="sending" @click="send">
          {{ sending ? "Sending…" : "Send" }}
        </button>
      </div>
    </div>
  </div>
</template>

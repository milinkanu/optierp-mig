<script setup lang="ts">
// Company print/branding settings: logo, contact, addresses, theme, extras, bank,
// and authorised signatory. The business fills this in once; every printed
// document then carries it. Logo/signature are stored as base64 data URIs.
import { onMounted, reactive, ref } from "vue";
import { usePrintSettingsStore } from "@/stores/printSettings";
import type { CompanyAddressIn, PrintTheme } from "@/types/printing";
import type { ErrorEnvelope } from "@/types/core";

const store = usePrintSettingsStore();
const error = ref<ErrorEnvelope | null>(null);
const uploadError = ref("");
const saving = ref(false);
const saved = ref(false);

const THEMES: Array<{ key: PrintTheme; label: string; hint: string; accent: string }> = [
  { key: "classic", label: "Classic", hint: "Formal serif, ruled tables", accent: "#1e3a8a" },
  { key: "modern", label: "Modern", hint: "Colour-band header, clean", accent: "#0d9488" },
  { key: "compact", label: "Compact", hint: "Dense, fits more lines", accent: "#374151" },
];

const MAX_IMAGE = 1_500_000; // ~1.5 MB before base64 overhead

const newAddress = reactive<CompanyAddressIn>({
  address_title: "",
  address_type: "Registered Office",
  address_line1: "",
  address_line2: null,
  city: null,
  state: null,
  pincode: null,
  country: null,
});

onMounted(async () => {
  try {
    await store.fetch();
  } catch (e) {
    error.value = e as ErrorEnvelope;
  }
});

function readAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

async function onImage(e: Event, field: "logo_data_uri" | "signature_data_uri"): Promise<void> {
  uploadError.value = "";
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  if (file.size > MAX_IMAGE) {
    uploadError.value = "Image is too large (max 1.5 MB). Please upload a smaller file.";
    input.value = "";
    return;
  }
  store.profile[field] = await readAsDataUrl(file);
  input.value = "";
}

async function save(): Promise<void> {
  saving.value = true;
  saved.value = false;
  error.value = null;
  try {
    await store.save();
    saved.value = true;
    setTimeout(() => (saved.value = false), 2500);
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    saving.value = false;
  }
}

async function addAddress(): Promise<void> {
  error.value = null;
  try {
    await store.addAddress({ ...newAddress });
    Object.assign(newAddress, {
      address_title: "", address_type: "Registered Office", address_line1: "",
      address_line2: null, city: null, state: null, pincode: null, country: null,
    });
  } catch (e) {
    error.value = e as ErrorEnvelope;
  }
}

async function removeAddress(id: string): Promise<void> {
  error.value = null;
  try {
    await store.deleteAddress(id);
  } catch (e) {
    error.value = e as ErrorEnvelope;
  }
}
</script>

<template>
  <div class="max-w-3xl space-y-6 pb-16">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-xl font-semibold text-gray-900">Document Branding &amp; Print</h1>
        <p class="text-sm text-gray-500">Shown on every PDF/printed document.</p>
      </div>
      <div class="flex items-center gap-3">
        <span v-if="saved" class="text-sm text-green-600">Saved ✓</span>
        <button class="btn-primary" :disabled="saving" @click="save">
          {{ saving ? "Saving…" : "Save" }}
        </button>
      </div>
    </div>
    <p v-if="error" class="text-sm text-red-600">{{ error.detail }}</p>

    <!-- Logo -->
    <section class="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
      <h2 class="text-sm font-semibold text-gray-900">Company Logo</h2>
      <div class="mt-3 flex items-center gap-5">
        <div class="flex h-20 w-40 items-center justify-center rounded border border-dashed border-gray-300 bg-gray-50">
          <img v-if="store.profile.logo_data_uri" :src="store.profile.logo_data_uri" alt="Logo" class="max-h-16 max-w-36 object-contain" />
          <span v-else class="text-xs text-gray-400">No logo</span>
        </div>
        <div class="space-y-2">
          <input type="file" accept="image/*" class="block text-sm" @change="(e) => onImage(e, 'logo_data_uri')" />
          <button
            v-if="store.profile.logo_data_uri"
            type="button"
            class="text-xs text-red-600 hover:underline"
            @click="store.profile.logo_data_uri = null"
          >
            Remove logo
          </button>
        </div>
      </div>
      <p v-if="uploadError" class="mt-2 text-sm text-red-600">{{ uploadError }}</p>
    </section>

    <!-- Contact -->
    <section class="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
      <h2 class="text-sm font-semibold text-gray-900">Contact</h2>
      <div class="mt-3 grid grid-cols-1 gap-4 md:grid-cols-3">
        <div>
          <label class="form-label">Email</label>
          <input v-model="store.profile.email" type="email" class="form-input" placeholder="billing@company.com" />
        </div>
        <div>
          <label class="form-label">Phone</label>
          <input v-model="store.profile.phone" class="form-input" placeholder="+91 98765 43210" />
        </div>
        <div>
          <label class="form-label">Website</label>
          <input v-model="store.profile.website" class="form-input" placeholder="www.company.com" />
        </div>
      </div>
    </section>

    <!-- Addresses -->
    <section class="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
      <h2 class="text-sm font-semibold text-gray-900">Company Addresses</h2>
      <p class="mt-1 text-sm text-gray-500">The first address prints by default. Type can be Registered Office, Billing, Dispatch, etc.</p>

      <ul v-if="store.addresses.length" class="mt-3 divide-y divide-gray-100">
        <li v-for="a in store.addresses" :key="a.id" class="flex items-start justify-between py-2">
          <div class="text-sm">
            <span class="font-medium text-gray-900">{{ a.address_title }}</span>
            <span class="ml-2 rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600">{{ a.address_type }}</span>
            <div class="text-gray-600">
              {{ a.address_line1 }}<template v-if="a.address_line2">, {{ a.address_line2 }}</template>
              <template v-if="a.city">, {{ a.city }}</template><template v-if="a.state">, {{ a.state }}</template>
              <template v-if="a.pincode"> - {{ a.pincode }}</template><template v-if="a.country">, {{ a.country }}</template>
            </div>
          </div>
          <button type="button" class="text-xs text-red-600 hover:underline" @click="removeAddress(a.id)">Delete</button>
        </li>
      </ul>
      <p v-else class="mt-3 text-sm text-gray-400">No company addresses yet.</p>

      <div class="mt-4 grid grid-cols-1 gap-3 border-t border-gray-100 pt-4 md:grid-cols-3">
        <input v-model="newAddress.address_title" class="form-input" placeholder="Title (e.g. Head Office)" />
        <select v-model="newAddress.address_type" class="form-input">
          <option>Registered Office</option>
          <option>Billing</option>
          <option>Dispatch</option>
          <option>Shipping</option>
        </select>
        <input v-model="newAddress.address_line1" class="form-input" placeholder="Address line 1" />
        <input v-model="newAddress.address_line2" class="form-input" placeholder="Address line 2" />
        <input v-model="newAddress.city" class="form-input" placeholder="City" />
        <input v-model="newAddress.state" class="form-input" placeholder="State" />
        <input v-model="newAddress.pincode" class="form-input" placeholder="Pincode" />
        <input v-model="newAddress.country" class="form-input" placeholder="Country" />
        <button
          type="button"
          class="btn-secondary"
          :disabled="!newAddress.address_title || !newAddress.address_line1"
          @click="addAddress"
        >
          Add address
        </button>
      </div>
    </section>

    <!-- Theme -->
    <section class="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
      <h2 class="text-sm font-semibold text-gray-900">Theme</h2>
      <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-3">
        <button
          v-for="t in THEMES"
          :key="t.key"
          type="button"
          class="rounded-lg border p-4 text-left transition"
          :class="store.profile.theme === t.key ? 'border-2 border-primary ring-1 ring-primary' : 'border-gray-200 hover:border-gray-300'"
          @click="store.profile.theme = t.key"
        >
          <div class="h-2 w-12 rounded" :style="{ background: t.accent }"></div>
          <div class="mt-2 text-sm font-semibold text-gray-900">{{ t.label }}</div>
          <div class="text-xs text-gray-500">{{ t.hint }}</div>
        </button>
      </div>
    </section>

    <!-- Extras -->
    <section class="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
      <h2 class="text-sm font-semibold text-gray-900">Document Extras</h2>
      <div class="mt-3 grid grid-cols-1 gap-2 md:grid-cols-2">
        <label class="flex items-center gap-2 text-sm text-gray-700">
          <input v-model="store.profile.toggles.amount_in_words" type="checkbox" class="rounded border-gray-300" />
          Amount in words
        </label>
        <label class="flex items-center gap-2 text-sm text-gray-700">
          <input v-model="store.profile.toggles.bank_details" type="checkbox" class="rounded border-gray-300" />
          Bank details for payment
        </label>
        <label class="flex items-center gap-2 text-sm text-gray-700">
          <input v-model="store.profile.toggles.signatory" type="checkbox" class="rounded border-gray-300" />
          Authorised signatory
        </label>
        <label class="flex items-center gap-2 text-sm text-gray-700">
          <input v-model="store.profile.toggles.tax_copy_labels" type="checkbox" class="rounded border-gray-300" />
          Tax copy labels (Original/Duplicate)
        </label>
      </div>
    </section>

    <!-- Bank -->
    <section v-show="store.profile.toggles.bank_details" class="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
      <h2 class="text-sm font-semibold text-gray-900">Bank Details</h2>
      <div class="mt-3 grid grid-cols-1 gap-4 md:grid-cols-2">
        <div><label class="form-label">Bank Name</label><input v-model="store.profile.bank.bank_name" class="form-input" /></div>
        <div><label class="form-label">Branch</label><input v-model="store.profile.bank.branch" class="form-input" /></div>
        <div><label class="form-label">Account No.</label><input v-model="store.profile.bank.account_no" class="form-input" /></div>
        <div><label class="form-label">IFSC</label><input v-model="store.profile.bank.ifsc" class="form-input" /></div>
        <div><label class="form-label">SWIFT (optional)</label><input v-model="store.profile.bank.swift" class="form-input" /></div>
      </div>
    </section>

    <!-- Signatory -->
    <section v-show="store.profile.toggles.signatory" class="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
      <h2 class="text-sm font-semibold text-gray-900">Authorised Signatory</h2>
      <div class="mt-3 grid grid-cols-1 gap-4 md:grid-cols-2">
        <div><label class="form-label">Name</label><input v-model="store.profile.signatory_name" class="form-input" /></div>
        <div><label class="form-label">Designation</label><input v-model="store.profile.signatory_designation" class="form-input" placeholder="Director / Accountant" /></div>
      </div>
      <div class="mt-4 flex items-center gap-5">
        <div class="flex h-16 w-40 items-center justify-center rounded border border-dashed border-gray-300 bg-gray-50">
          <img v-if="store.profile.signature_data_uri" :src="store.profile.signature_data_uri" alt="Signature" class="max-h-12 max-w-36 object-contain" />
          <span v-else class="text-xs text-gray-400">No signature</span>
        </div>
        <div class="space-y-2">
          <input type="file" accept="image/*" class="block text-sm" @change="(e) => onImage(e, 'signature_data_uri')" />
          <button
            v-if="store.profile.signature_data_uri"
            type="button"
            class="text-xs text-red-600 hover:underline"
            @click="store.profile.signature_data_uri = null"
          >
            Remove signature
          </button>
        </div>
      </div>
    </section>
  </div>
</template>

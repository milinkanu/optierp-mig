<script setup lang="ts">
// Address & Contact tab for transaction forms: Billing + Shipping address and
// Contact Person pickers, filtered to the selected party's records (Address /
// Contact carry a direct customer_id/supplier_id link). Renders the chosen
// address/contact below each picker. v-model carries the three FK ids.

import { computed, onMounted, ref, watch } from "vue";
import { api } from "@/api/client";

interface AddressRec {
  id: string;
  customer_id: string | null;
  supplier_id: string | null;
  address_title: string;
  address_type?: string | null;
  address_line1?: string | null;
  address_line2?: string | null;
  city?: string | null;
  state?: string | null;
  pincode?: string | null;
  country?: string | null;
}
interface ContactRec {
  id: string;
  customer_id: string | null;
  supplier_id: string | null;
  first_name: string;
  last_name?: string | null;
  email_id?: string | null;
  mobile_no?: string | null;
  phone?: string | null;
  designation?: string | null;
}

export interface AddressContactModel {
  billing_address_id: string | null;
  shipping_address_id: string | null;
  contact_person_id: string | null;
}

const props = withDefaults(
  defineProps<{
    modelValue: AddressContactModel;
    partyId: string;
    partyKind?: "customer" | "supplier";
  }>(),
  { partyKind: "customer" },
);
const emit = defineEmits<{ "update:modelValue": [value: AddressContactModel] }>();

const addresses = ref<AddressRec[]>([]);
const contacts = ref<ContactRec[]>([]);
const loaded = ref(false);

const linkKey = computed(() => `${props.partyKind}_id` as "customer_id" | "supplier_id");
const partyAddresses = computed(() =>
  props.partyId ? addresses.value.filter((a) => a[linkKey.value] === props.partyId) : [],
);
const partyContacts = computed(() =>
  props.partyId ? contacts.value.filter((c) => c[linkKey.value] === props.partyId) : [],
);

const billing = computed(() => partyAddresses.value.find((a) => a.id === props.modelValue.billing_address_id));
const shipping = computed(() => partyAddresses.value.find((a) => a.id === props.modelValue.shipping_address_id));
const contact = computed(() => partyContacts.value.find((c) => c.id === props.modelValue.contact_person_id));

function set(key: keyof AddressContactModel, value: string): void {
  emit("update:modelValue", { ...props.modelValue, [key]: value || null });
}

function addressOption(a: AddressRec): string {
  return a.address_type ? `${a.address_title} (${a.address_type})` : a.address_title;
}
function formatAddress(a: AddressRec): string {
  const cityLine = [a.city, a.state, a.pincode].filter(Boolean).join(" ");
  return [a.address_line1, a.address_line2, cityLine, a.country].filter(Boolean).join(", ");
}
function contactName(c: ContactRec): string {
  return [c.first_name, c.last_name].filter(Boolean).join(" ");
}
function formatContact(c: ContactRec): string {
  return [c.designation, c.mobile_no || c.phone, c.email_id].filter(Boolean).join(" · ");
}

async function load(): Promise<void> {
  try {
    const [a, c] = await Promise.all([
      api.get<{ items: AddressRec[] }>("/registry/address", { params: { page_size: 200 } }),
      api.get<{ items: ContactRec[] }>("/registry/contact", { params: { page_size: 200 } }),
    ]);
    addresses.value = a.data.items;
    contacts.value = c.data.items;
  } catch {
    // best-effort; leaves the pickers empty
  } finally {
    loaded.value = true;
  }
}

onMounted(load);

// Clear stale selections when the party changes (an address belongs to one party).
watch(
  () => props.partyId,
  () => {
    if (props.modelValue.billing_address_id || props.modelValue.shipping_address_id || props.modelValue.contact_person_id) {
      emit("update:modelValue", { billing_address_id: null, shipping_address_id: null, contact_person_id: null });
    }
  },
);
</script>

<template>
  <div class="space-y-6">
    <p v-if="!partyId" class="text-sm text-gray-400">Select a {{ partyKind }} first to choose addresses and a contact.</p>

    <div v-else class="grid grid-cols-1 gap-x-8 gap-y-6 md:grid-cols-2">
      <!-- Billing address -->
      <div>
        <label class="form-label">Billing Address</label>
        <select
          class="form-input"
          :value="modelValue.billing_address_id ?? ''"
          @change="set('billing_address_id', ($event.target as HTMLSelectElement).value)"
        >
          <option value="">Select address…</option>
          <option v-for="a in partyAddresses" :key="a.id" :value="a.id">{{ addressOption(a) }}</option>
        </select>
        <p v-if="billing" class="mt-1 whitespace-pre-line text-xs text-gray-500">{{ formatAddress(billing) }}</p>
      </div>

      <!-- Shipping address -->
      <div>
        <label class="form-label">Shipping Address</label>
        <select
          class="form-input"
          :value="modelValue.shipping_address_id ?? ''"
          @change="set('shipping_address_id', ($event.target as HTMLSelectElement).value)"
        >
          <option value="">Select address…</option>
          <option v-for="a in partyAddresses" :key="a.id" :value="a.id">{{ addressOption(a) }}</option>
        </select>
        <p v-if="shipping" class="mt-1 whitespace-pre-line text-xs text-gray-500">{{ formatAddress(shipping) }}</p>
      </div>

      <!-- Contact person -->
      <div>
        <label class="form-label">Contact Person</label>
        <select
          class="form-input"
          :value="modelValue.contact_person_id ?? ''"
          @change="set('contact_person_id', ($event.target as HTMLSelectElement).value)"
        >
          <option value="">Select contact…</option>
          <option v-for="c in partyContacts" :key="c.id" :value="c.id">{{ contactName(c) }}</option>
        </select>
        <p v-if="contact" class="mt-1 text-xs text-gray-500">{{ formatContact(contact) }}</p>
      </div>

      <div v-if="loaded && partyAddresses.length === 0 && partyContacts.length === 0" class="md:col-span-2">
        <p class="text-sm text-gray-400">
          No addresses or contacts on file for this {{ partyKind }}. Add them under
          <span class="font-medium">Setup → Address / Contact</span>.
        </p>
      </div>
    </div>
  </div>
</template>

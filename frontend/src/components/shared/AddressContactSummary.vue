<script setup lang="ts">
// Read-only Address & Contact summary for a saved document's detail view.
// Resolves the linked Address/Contact ids to formatted text. Single root so it
// drops into a detail grid (pass a col-span class); renders nothing if empty.

import { ref, watchEffect } from "vue";
import { api } from "@/api/client";

const props = defineProps<{
  billingAddressId?: string | null;
  shippingAddressId?: string | null;
  contactPersonId?: string | null;
}>();

interface AddressRec {
  address_line1?: string | null;
  address_line2?: string | null;
  city?: string | null;
  state?: string | null;
  pincode?: string | null;
  country?: string | null;
}
interface ContactRec {
  first_name: string;
  last_name?: string | null;
  email_id?: string | null;
  mobile_no?: string | null;
  phone?: string | null;
  designation?: string | null;
}

const billing = ref<AddressRec | null>(null);
const shipping = ref<AddressRec | null>(null);
const contact = ref<ContactRec | null>(null);

async function fetchAddress(id?: string | null): Promise<AddressRec | null> {
  if (!id) return null;
  try {
    return (await api.get<AddressRec>(`/registry/address/${id}`)).data;
  } catch {
    return null;
  }
}
async function fetchContact(id?: string | null): Promise<ContactRec | null> {
  if (!id) return null;
  try {
    return (await api.get<ContactRec>(`/registry/contact/${id}`)).data;
  } catch {
    return null;
  }
}

watchEffect(async () => {
  billing.value = await fetchAddress(props.billingAddressId);
  shipping.value = await fetchAddress(props.shippingAddressId);
  contact.value = await fetchContact(props.contactPersonId);
});

function formatAddress(a: AddressRec): string {
  const cityLine = [a.city, a.state, a.pincode].filter(Boolean).join(" ");
  return [a.address_line1, a.address_line2, cityLine, a.country].filter(Boolean).join(", ");
}
function formatContact(c: ContactRec): string {
  const name = [c.first_name, c.last_name].filter(Boolean).join(" ");
  return [name, c.designation, c.mobile_no || c.phone, c.email_id].filter(Boolean).join(" · ");
}
</script>

<template>
  <div v-if="billing || shipping || contact">
    <div class="text-xs font-semibold uppercase tracking-wide text-gray-400">Address &amp; Contact</div>
    <div class="mt-0.5 grid grid-cols-1 gap-x-8 gap-y-1 text-sm text-gray-700 md:grid-cols-3">
      <div v-if="billing"><span class="text-gray-400">Billing:</span> {{ formatAddress(billing) }}</div>
      <div v-if="shipping"><span class="text-gray-400">Shipping:</span> {{ formatAddress(shipping) }}</div>
      <div v-if="contact"><span class="text-gray-400">Contact:</span> {{ formatContact(contact) }}</div>
    </div>
  </div>
</template>

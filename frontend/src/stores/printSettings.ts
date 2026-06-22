// Print/branding settings store: the company print profile + its own addresses.

import { defineStore } from "pinia";
import { api } from "@/api/client";
import type { CompanyAddress, CompanyAddressIn, PrintProfile } from "@/types/printing";

function emptyProfile(): PrintProfile {
  return {
    logo_data_uri: null,
    email: null,
    phone: null,
    website: null,
    bank: { bank_name: null, account_no: null, ifsc: null, branch: null, swift: null },
    signature_data_uri: null,
    signatory_name: null,
    signatory_designation: null,
    theme: "classic",
    doctype_theme: {},
    doctype_address: {},
    toggles: { amount_in_words: true, bank_details: true, signatory: true, tax_copy_labels: true },
  };
}

interface PrintSettingsState {
  profile: PrintProfile;
  addresses: CompanyAddress[];
  loaded: boolean;
}

export const usePrintSettingsStore = defineStore("printSettings", {
  state: (): PrintSettingsState => ({
    profile: emptyProfile(),
    addresses: [],
    loaded: false,
  }),
  actions: {
    async fetch(): Promise<void> {
      const [profile, addresses] = await Promise.all([
        api.get<PrintProfile>("/print-settings"),
        api.get<CompanyAddress[]>("/print-settings/addresses"),
      ]);
      this.profile = profile.data;
      this.addresses = addresses.data;
      this.loaded = true;
    },
    async save(): Promise<void> {
      this.profile = (await api.put<PrintProfile>("/print-settings", this.profile)).data;
    },
    async addAddress(payload: CompanyAddressIn): Promise<void> {
      await api.post<CompanyAddress>("/print-settings/addresses", payload);
      this.addresses = (await api.get<CompanyAddress[]>("/print-settings/addresses")).data;
    },
    async deleteAddress(id: string): Promise<void> {
      await api.delete(`/print-settings/addresses/${id}`);
      this.addresses = this.addresses.filter((a) => a.id !== id);
    },
  },
});

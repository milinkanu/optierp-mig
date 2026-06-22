// Types for the company print/branding profile and company addresses (Section 4.5).

export interface BankDetails {
  bank_name: string | null;
  account_no: string | null;
  ifsc: string | null;
  branch: string | null;
  swift: string | null;
}

export interface PrintToggles {
  amount_in_words: boolean;
  bank_details: boolean;
  signatory: boolean;
  tax_copy_labels: boolean;
}

export type PrintTheme = "classic" | "modern" | "compact";

export interface PrintProfile {
  logo_data_uri: string | null;
  email: string | null;
  phone: string | null;
  website: string | null;
  bank: BankDetails;
  signature_data_uri: string | null;
  signatory_name: string | null;
  signatory_designation: string | null;
  theme: PrintTheme;
  doctype_theme: Record<string, string>;
  doctype_address: Record<string, string>;
  toggles: PrintToggles;
}

export interface CompanyAddress {
  id: string;
  address_title: string;
  address_type: string;
  address_line1: string;
  address_line2: string | null;
  city: string | null;
  state: string | null;
  pincode: string | null;
  country: string | null;
}

export type CompanyAddressIn = Omit<CompanyAddress, "id">;

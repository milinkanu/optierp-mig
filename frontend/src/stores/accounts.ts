// Module 02 — Accounts Pinia store: parties, account tree, document actions.

import { defineStore } from "pinia";
import { api } from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import type { AccountNode, ListResponse } from "@/types/core";
import type { CostCenter, Customer, Supplier, TaxTemplate } from "@/types/accounts";

interface AccountsState {
  accounts: AccountNode[];
  customers: Customer[];
  suppliers: Supplier[];
  taxTemplates: TaxTemplate[];
  costCenters: CostCenter[];
}

export const useAccountsStore = defineStore("accounts", {
  state: (): AccountsState => ({
    accounts: [],
    customers: [],
    suppliers: [],
    taxTemplates: [],
    costCenters: [],
  }),
  getters: {
    leafAccounts: (state) => state.accounts.filter((a) => !a.is_group),
    accountOptions(): Array<{ value: string; label: string }> {
      return this.leafAccounts.map((a: AccountNode) => ({
        value: a.id,
        label: `${a.account_name} (${a.root_type})`,
      }));
    },
    // Accounts filtered by type for the invoice Debit-To / Credit-To pickers.
    receivableAccountOptions(): Array<{ value: string; label: string }> {
      return this.leafAccounts
        .filter((a: AccountNode) => a.account_type === "Receivable")
        .map((a: AccountNode) => ({ value: a.id, label: a.account_name }));
    },
    payableAccountOptions(): Array<{ value: string; label: string }> {
      return this.leafAccounts
        .filter((a: AccountNode) => a.account_type === "Payable")
        .map((a: AccountNode) => ({ value: a.id, label: a.account_name }));
    },
    // Postable (leaf) cost centers for the per-line Cost Center picker.
    costCenterOptions(): Array<{ value: string; label: string }> {
      return this.costCenters
        .filter((c: CostCenter) => !c.is_group)
        .map((c: CostCenter) => ({ value: c.id, label: c.cost_center_name }));
    },
  },
  actions: {
    async fetchAccounts(): Promise<void> {
      const auth = useAuthStore();
      if (!auth.companyId) return;
      const resp = await api.get<AccountNode[]>(`/companies/${auth.companyId}/chart-of-accounts`);
      this.accounts = resp.data;
    },
    async fetchCustomers(): Promise<void> {
      const resp = await api.get<ListResponse<Customer>>("/customers", {
        params: { page_size: 200 },
      });
      this.customers = resp.data.items;
    },
    async fetchSuppliers(): Promise<void> {
      const resp = await api.get<ListResponse<Supplier>>("/suppliers", {
        params: { page_size: 200 },
      });
      this.suppliers = resp.data.items;
    },
    // /tax-templates returns a BARE array (not a ListResponse). Filter by kind
    // (sales/purchase) so the picker only offers templates for this document.
    async fetchTaxTemplates(kind: "sales" | "purchase"): Promise<void> {
      const resp = await api.get<TaxTemplate[]>("/tax-templates", { params: { kind } });
      this.taxTemplates = resp.data;
    },
    async fetchCostCenters(): Promise<void> {
      const resp = await api.get<ListResponse<CostCenter>>("/registry/cost-center", {
        params: { page_size: 200 },
      });
      this.costCenters = resp.data.items;
    },
    async createCustomer(name: string): Promise<Customer> {
      const resp = await api.post<Customer>("/customers", { customer_name: name });
      await this.fetchCustomers();
      return resp.data;
    },
    async createSupplier(name: string): Promise<Supplier> {
      const resp = await api.post<Supplier>("/suppliers", { supplier_name: name });
      await this.fetchSuppliers();
      return resp.data;
    },
    async docAction<T>(endpoint: string, id: string, action: "submit" | "cancel"): Promise<T> {
      const resp = await api.post<T>(`${endpoint}/${id}/${action}`);
      return resp.data;
    },
  },
});

// Module 02 — Accounts Pinia store: parties, account tree, document actions.

import { defineStore } from "pinia";
import { api } from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import type { AccountNode, ListResponse } from "@/types/core";
import type { Customer, Supplier } from "@/types/accounts";

interface AccountsState {
  accounts: AccountNode[];
  customers: Customer[];
  suppliers: Supplier[];
}

export const useAccountsStore = defineStore("accounts", {
  state: (): AccountsState => ({
    accounts: [],
    customers: [],
    suppliers: [],
  }),
  getters: {
    leafAccounts: (state) => state.accounts.filter((a) => !a.is_group),
    accountOptions(): Array<{ value: string; label: string }> {
      return this.leafAccounts.map((a: AccountNode) => ({
        value: a.id,
        label: `${a.account_name} (${a.root_type})`,
      }));
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

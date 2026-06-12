// Core module store: companies, users, roles, currencies, masters.

import { defineStore } from "pinia";
import { api } from "@/api/client";
import type {
  Company,
  CompanyListItem,
  Currency,
  ListResponse,
  Role,
  UserListItem,
} from "@/types/core";

interface CoreState {
  companies: CompanyListItem[];
  companiesTotal: number;
  users: UserListItem[];
  usersTotal: number;
  roles: Role[];
  currencies: Currency[];
  coaTemplates: string[];
}

export const useCoreStore = defineStore("core", {
  state: (): CoreState => ({
    companies: [],
    companiesTotal: 0,
    users: [],
    usersTotal: 0,
    roles: [],
    currencies: [],
    coaTemplates: [],
  }),
  actions: {
    async fetchCompanies(page = 1, pageSize = 20): Promise<void> {
      const resp = await api.get<ListResponse<CompanyListItem>>("/companies", {
        params: { page, page_size: pageSize },
      });
      this.companies = resp.data.items;
      this.companiesTotal = resp.data.total;
    },
    async fetchCompany(id: string): Promise<Company> {
      return (await api.get<Company>(`/companies/${id}`)).data;
    },
    async createCompany(payload: Record<string, unknown>): Promise<Company> {
      const company = (await api.post<Company>("/companies", payload)).data;
      await this.fetchCompanies();
      return company;
    },
    async fetchUsers(page = 1, pageSize = 20, search = ""): Promise<void> {
      const resp = await api.get<ListResponse<UserListItem>>("/users", {
        params: { page, page_size: pageSize, search: search || undefined },
      });
      this.users = resp.data.items;
      this.usersTotal = resp.data.total;
    },
    async fetchRoles(): Promise<void> {
      this.roles = (await api.get<Role[]>("/roles")).data;
    },
    async fetchCurrencies(): Promise<void> {
      this.currencies = (await api.get<Currency[]>("/currencies")).data;
    },
    async fetchCoaTemplates(): Promise<void> {
      this.coaTemplates = (await api.get<string[]>("/companies/meta/coa-templates")).data;
    },
  },
});

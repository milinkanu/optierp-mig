// Auth store: session lifecycle around the JWT access token (in memory)
// and the httpOnly refresh cookie (managed by the browser).

import { defineStore } from "pinia";
import { api, setAccessToken } from "@/api/client";
import type { TokenResponse, User } from "@/types/core";

interface AuthState {
  userId: string | null;
  email: string | null;
  fullName: string | null;
  companyId: string | null;
  roles: string[];
  profile: User | null;
  initialized: boolean;
}

export const useAuthStore = defineStore("auth", {
  state: (): AuthState => ({
    userId: null,
    email: null,
    fullName: null,
    companyId: null,
    roles: [],
    profile: null,
    initialized: false,
  }),
  getters: {
    isAuthenticated: (state) => state.userId !== null,
    isSystemManager: (state) => state.roles.includes("System Manager"),
  },
  actions: {
    applyToken(token: TokenResponse) {
      setAccessToken(token.access_token);
      this.userId = token.user_id;
      this.email = token.email;
      this.fullName = token.full_name;
      this.companyId = token.company_id;
      this.roles = token.roles;
    },
    async login(email: string, password: string): Promise<void> {
      const resp = await api.post<TokenResponse>("/auth/login", { email, password });
      this.applyToken(resp.data);
    },
    async restoreSession(): Promise<void> {
      // Called once at startup: the refresh cookie silently restores the session.
      try {
        const resp = await api.post<TokenResponse>("/auth/refresh");
        this.applyToken(resp.data);
      } catch {
        // not logged in — stay anonymous
      } finally {
        this.initialized = true;
      }
    },
    async fetchProfile(): Promise<void> {
      const resp = await api.get<User>("/auth/me");
      this.profile = resp.data;
    },
    async switchCompany(companyId: string): Promise<void> {
      const resp = await api.post<TokenResponse>("/auth/switch-company", { company_id: companyId });
      this.applyToken(resp.data);
    },
    async logout(): Promise<void> {
      try {
        await api.post("/auth/logout");
      } finally {
        setAccessToken(null);
        this.$reset();
        this.initialized = true;
      }
    },
  },
});

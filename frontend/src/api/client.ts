// Typed API client: bearer token injection + one-shot refresh on 401 +
// uniform error envelope normalisation.

import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";
import type { ErrorEnvelope, TokenResponse } from "@/types/core";

export const api = axios.create({
  baseURL: "/api/v1",
  withCredentials: true, // refresh token cookie
});

let accessToken: string | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  if (accessToken && config.headers) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

let refreshPromise: Promise<string> | null = null;

async function refreshAccessToken(): Promise<string> {
  refreshPromise ??= axios
    .post<TokenResponse>("/api/v1/auth/refresh", null, { withCredentials: true })
    .then((resp) => {
      setAccessToken(resp.data.access_token);
      return resp.data.access_token;
    })
    .finally(() => {
      refreshPromise = null;
    });
  return refreshPromise;
}

api.interceptors.response.use(
  (resp) => resp,
  async (error: AxiosError<ErrorEnvelope>) => {
    const original = error.config as (InternalAxiosRequestConfig & { _retried?: boolean }) | undefined;
    const isAuthCall = original?.url?.includes("/auth/");
    if (error.response?.status === 401 && original && !original._retried && !isAuthCall) {
      try {
        original._retried = true;
        await refreshAccessToken();
        return api.request(original);
      } catch {
        // fall through: session expired — surface the original error
        window.dispatchEvent(new CustomEvent("auth:expired"));
      }
    }
    const envelope: ErrorEnvelope = error.response?.data?.detail
      ? error.response.data
      : { detail: error.message, code: "ERR_NETWORK", field: null };
    return Promise.reject(envelope);
  },
);

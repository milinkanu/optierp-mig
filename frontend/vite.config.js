import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
export default defineConfig({
    plugins: [vue()],
    resolve: {
        alias: {
            "@": fileURLToPath(new URL("./src", import.meta.url)),
        },
    },
    server: {
        port: 5173,
        proxy: {
            // Backend runs on :8000 in local dev (uvicorn) and docker-compose
            "/api": { target: "http://localhost:8000", changeOrigin: true },
        },
    },
});

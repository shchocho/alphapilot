import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vitest/config";

const src = (path: string) => fileURLToPath(new URL(`./src/${path}`, import.meta.url));

// 공개 데모(GitHub Pages) 빌드에서는 로그인·계정·키 입력 부품을 같은 이름의 빈 부품(*.demo.tsx)으로 바꿔 묶는다.
// 화면에서만 숨기면 문구와 입력칸 코드가 묶음에 남아 피싱 오탐의 재료가 된다(CLAUDE.md 배포 안전 기준).
// 이 목록의 파일은 반드시 "@/..." 경로로 import한다. 상대 경로로 부르면 바뀌지 않는다.
const DEMO_STUBS = ["app/authForms", "features/settings/AccountPanel", "features/settings/SecurityPanel", "features/settings/BrokerKeyForm"];

// 개발 서버는 /api 요청을 백엔드(127.0.0.1:8000)로 넘긴다. 운영에서는 백엔드가 빌드 결과물을 직접 서빙한다.
export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: [
      ...(mode === "demo" ? DEMO_STUBS.map((path) => ({ find: `@/${path}`, replacement: src(`${path}.demo.tsx`) })) : []),
      { find: "@", replacement: src("").replace(/[\/]$/, "") },
    ],
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: false } },
  },
  build: { outDir: "dist", sourcemap: false, chunkSizeWarningLimit: 900 },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
}));

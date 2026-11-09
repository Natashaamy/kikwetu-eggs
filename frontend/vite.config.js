import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ command, mode }) => {
  if (command === "build") {
    const env = loadEnv(mode, process.cwd(), "VITE_");
    const value = (process.env.VITE_API_URL ?? env.VITE_API_URL ?? "").trim();
    let url;
    try {
      url = new URL(value);
    } catch {
      throw new Error("Production builds require VITE_API_URL to be an HTTPS backend origin.");
    }
    if (url.protocol !== "https:" || url.username || url.password ||
        url.pathname !== "/" || url.search || url.hash ||
        /^(localhost|127\.|0\.0\.0\.0|\[::1\]$)/i.test(url.hostname)) {
      throw new Error("VITE_API_URL must be a public HTTPS backend origin without credentials or /api.");
    }
    const exposed = { ...env, ...Object.fromEntries(
      Object.entries(process.env).filter(([key]) => key.startsWith("VITE_"))
    ) };
    if (Object.keys(exposed).some((key) => /SECRET|PASSWORD|PASSKEY|DATABASE|CONSUMER_KEY|TOKEN|PRIVATE_KEY/i.test(key))) {
      throw new Error("Server secrets must not be configured as VITE_ variables.");
    }
  }
  return { plugins: [react()] };
});

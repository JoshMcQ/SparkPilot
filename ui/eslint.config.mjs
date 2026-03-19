import { defineConfig } from "eslint/config";
import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

export default defineConfig([
  {
    ignores: ["playwright-report/**", "test-results/**", ".next/**"],
  },
  {
    extends: [...nextCoreWebVitals, ...nextTypescript],
  },
]);

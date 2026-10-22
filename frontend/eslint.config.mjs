import { defineConfig } from "eslint/config";
import next from "eslint-config-next";

export default defineConfig([
  ...next,
  {
    ignores: [".next/**", "node_modules/**", "next-env.d.ts"],
  },
  {
    // 资产图片由后端接口直出，不需要 next/image 的优化管线
    rules: { "@next/next/no-img-element": "off" },
  },
]);

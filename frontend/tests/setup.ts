import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// 每个用例后清理 DOM，避免上一个渲染残留导致 "Found multiple elements"
afterEach(() => {
  cleanup();
});

import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const tokensCss = readFileSync(join(root, "../src/theme/tokens.css"), "utf8");

describe("theme button CSS", () => {
  it("keeps primary button hover colors tokenized for dark mode contrast", () => {
    const hoverRule = tokensCss.match(/\.btn-primary:hover\s*\{[^}]+\}/)?.[0] || "";

    expect(hoverRule).toContain("background: var(--ink-soft)");
    expect(hoverRule).toContain("color: var(--paper)");
    expect(hoverRule).not.toMatch(/#[0-9a-fA-F]{3,8}/);
  });
});

import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const srcRoot = join(root, "../src");
const allowedLiteralColorFiles = new Set([
  "theme/tokens.css",
  "widgets/theme-tokens.ts",
  "components/LivePollSlide.vue",
  "components/LiveQuestionSlide.vue",
  "components/LiveRandomAudienceSlide.vue",
]);

function collectSourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    const stat = statSync(path);
    if (stat.isDirectory()) return collectSourceFiles(path);
    return /\.(vue|ts|css)$/.test(entry) ? [path] : [];
  });
}

describe("theme color audit", () => {
  it("keeps ordinary app UI free of hex color literals", () => {
    const offenders = collectSourceFiles(srcRoot)
      .filter((path) => !allowedLiteralColorFiles.has(relative(srcRoot, path)))
      .flatMap((path) => {
        const rel = relative(srcRoot, path);
        return readFileSync(path, "utf8")
          .split("\n")
          .flatMap((line, index) => (/#(?:[0-9a-fA-F]{3,8})\b/.test(line) ? [`${rel}:${index + 1}`] : []));
      });

    expect(offenders).toEqual([]);
  });
});

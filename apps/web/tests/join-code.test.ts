import { describe, expect, it } from "vitest";
import { normalizeJoinCode } from "@/utils/joinCode";

describe("normalizeJoinCode", () => {
  it("uppercases plain session codes", () => {
    expect(normalizeJoinCode(" sld-2k4f-92 ")).toBe("SLD-2K4F-92");
  });

  it("extracts session codes from join links", () => {
    expect(normalizeJoinCode("http://slides.example/j/SLD-BRWW-F3")).toBe("SLD-BRWW-F3");
    expect(normalizeJoinCode("https://slides.example/j/sld-2k4f-92?from=mail")).toBe("SLD-2K4F-92");
  });
});

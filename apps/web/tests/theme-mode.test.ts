import { afterEach, describe, expect, it, vi } from "vitest";
import { useThemeMode, THEME_MODE_STORAGE_KEY } from "../src/theme/useThemeMode";

afterEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("dark", "light");
});

describe("useThemeMode", () => {
  it("applies dark class and persists explicit dark mode", () => {
    const theme = useThemeMode();
    theme.setMode("dark");

    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(document.documentElement.classList.contains("light")).toBe(false);
    expect(localStorage.getItem(THEME_MODE_STORAGE_KEY)).toBe("dark");
  });

  it("applies light class and removes dark when mode changes", () => {
    const theme = useThemeMode();
    theme.setMode("dark");
    theme.setMode("light");

    expect(document.documentElement.classList.contains("light")).toBe(true);
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("emits a theme change event for iframe/token consumers", () => {
    const listener = vi.fn();
    window.addEventListener("slaides:theme-changed", listener);
    const theme = useThemeMode();

    theme.setMode("dark");

    expect(listener).toHaveBeenCalledWith(expect.objectContaining({
      type: "slaides:theme-changed",
    }));
    window.removeEventListener("slaides:theme-changed", listener);
  });
});

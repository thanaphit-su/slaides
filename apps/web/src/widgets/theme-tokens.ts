/**
 * Shared theme-token plumbing for widget iframes.
 *
 * Widgets author CSS against shadcn-style semantic names (`--card`,
 * `--border`, `--font-serif`, …) but the host document exposes the SLAIDES
 * "Editorial Press" palette (`--paper`, `--ink`, `--rule`, …). CSS variables
 * do not cross frame boundaries, so the host has to resolve the values once
 * and re-emit them inside the iframe `:root`.
 *
 * Both the canvas `WidgetFrame` and the sidebar `WidgetThumbnail` need the
 * exact same mapping — otherwise widgets render with different colors,
 * fonts, and borders in the preview vs. the live slide (which was the bug
 * that prompted the extraction).
 */

export function readHostTokens(): Record<string, string> {
  if (typeof document === "undefined") return {};
  const cs = getComputedStyle(document.documentElement);
  const read = (name: string) => cs.getPropertyValue(name).trim();
  // Map shadcn-style semantic tokens to the SLAIDES "Editorial Press" palette.
  return {
    "--background": read("--paper") || "#ffffff",
    "--foreground": read("--ink") || "#0b0d10",
    "--card": read("--paper") || "#ffffff",
    "--card-foreground": read("--ink") || "#0b0d10",
    "--popover": read("--paper") || "#ffffff",
    "--popover-foreground": read("--ink") || "#0b0d10",
    "--primary": read("--ink") || "#0b0d10",
    "--primary-foreground": read("--paper") || "#ffffff",
    "--secondary": read("--paper-2") || "#f7f6f2",
    "--secondary-foreground": read("--ink") || "#0b0d10",
    "--muted": read("--paper-2") || "#f7f6f2",
    "--muted-foreground": read("--ink-soft") || "#4b525b",
    "--accent": read("--accent") || "#1f3a8a",
    "--accent-foreground": read("--paper") || "#ffffff",
    "--accent-soft": read("--accent-soft") || "rgba(31,58,138,0.08)",
    "--destructive": read("--err") || "#be1d4a",
    "--destructive-foreground": read("--paper") || "#ffffff",
    "--border": read("--rule") || "#e3e1dc",
    "--border-strong": read("--rule-strong") || "#cfccc4",
    "--input": read("--rule") || "#e3e1dc",
    "--ring": read("--accent") || "#1f3a8a",
    "--radius": "0.5rem",
    "--radius-sm": "0.375rem",
    "--radius-lg": "0.75rem",
    "--font-sans": read("--sans") || "'Inter', system-ui, sans-serif",
    "--font-serif": read("--serif") || "'Newsreader', Georgia, serif",
    "--font-mono": read("--mono") || "'IBM Plex Mono', monospace",
  };
}

export interface BuildThemeStyleOptions {
  /** Stretch html/body to 100% height (canvas widgets); false leaves natural
   * intrinsic height (thumbnail previews). */
  fill?: boolean;
}

/** Build the `:root { … }` token block + the body reset + link/selection
 * defaults that widget CSS expects to find. The returned string goes inside
 * a `<style>` element in the iframe srcdoc, ahead of the widget's own CSS. */
export function buildThemeStyleBlock(
  tokens: Record<string, string>,
  opts: BuildThemeStyleOptions = {},
): string {
  const tokenLines = Object.entries(tokens)
    .map(([k, v]) => `${k}: ${v};`)
    .join("\n  ");
  const baseHeight = opts.fill
    ? "html,body{margin:0;padding:0;height:100%;}"
    : "html,body{margin:0;padding:0;}";
  return `
:root {
  ${tokenLines}
}
${baseHeight}
body {
  background: var(--background);
  color: var(--foreground);
  font-family: var(--font-sans);
  font-size: 14px;
  line-height: 1.55;
  -webkit-font-smoothing: antialiased;
}
button, input, textarea, select { font: inherit; color: inherit; }
a { color: var(--accent); text-decoration: underline; text-underline-offset: 3px; }
::selection { background: var(--accent-soft); color: var(--foreground); }
`;
}

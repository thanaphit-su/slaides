// Node 26 ships an experimental `localStorage` that requires the
// `--localstorage-file` CLI flag; without the flag it's a "warning, undefined"
// stub that shadows what happy-dom would otherwise provide on globalThis.
// Bind a tiny in-memory Storage so tests can call `localStorage.clear()` etc.
// the same way they would in a real browser.

class MemoryStorage implements Storage {
  private data = new Map<string, string>();
  get length(): number {
    return this.data.size;
  }
  clear(): void {
    this.data.clear();
  }
  getItem(key: string): string | null {
    return this.data.has(key) ? (this.data.get(key) as string) : null;
  }
  setItem(key: string, value: string): void {
    this.data.set(key, String(value));
  }
  removeItem(key: string): void {
    this.data.delete(key);
  }
  key(index: number): string | null {
    const keys = Array.from(this.data.keys());
    return keys[index] ?? null;
  }
}

function ensureStorage(name: "localStorage" | "sessionStorage"): void {
  const g = globalThis as unknown as Record<string, unknown>;
  const existing = g[name];
  // Replace if missing or unusable (Node's stub has no .clear method).
  const usable =
    existing !== undefined &&
    existing !== null &&
    typeof (existing as Storage).clear === "function";
  if (!usable) {
    Object.defineProperty(globalThis, name, {
      value: new MemoryStorage(),
      writable: true,
      configurable: true,
    });
  }
}

ensureStorage("localStorage");
ensureStorage("sessionStorage");

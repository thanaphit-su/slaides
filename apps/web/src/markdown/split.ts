export interface SplitChunk {
  markdown: string;
}

export function splitOnH1(markdown: string): SplitChunk[] {
  if (!markdown) return [{ markdown: "" }];
  const re = /^# .*$/gm;
  const matches: { index: number }[] = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(markdown)) !== null) matches.push({ index: m.index });
  if (matches.length === 0) return [{ markdown }];
  const chunks: SplitChunk[] = [];
  if (matches[0].index > 0) {
    const prefix = markdown.slice(0, matches[0].index).replace(/\s+$/g, "");
    if (prefix) chunks.push({ markdown: prefix });
  }
  for (let i = 0; i < matches.length; i++) {
    const start = matches[i].index;
    const end = i + 1 < matches.length ? matches[i + 1].index : markdown.length;
    chunks.push({ markdown: markdown.slice(start, end).replace(/\n+$/g, "") });
  }
  return chunks;
}

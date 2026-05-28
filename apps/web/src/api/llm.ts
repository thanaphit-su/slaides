import { api, ApiError } from "./client";
import type { LlmPurpose } from "./types";

interface CompleteBody {
  purpose: LlmPurpose;
  prompt: string;
  context?: Record<string, unknown>;
  model_override?: string;
  images?: Array<{ data_url: string; name?: string | null; mime_type?: string | null }>;
}

type CompleteOptions = {
  onToken?: (delta: string) => void;
  onWarnings?: (warnings: string[]) => void;
  signal?: AbortSignal;
  token?: string | null;
};

function parseSseChunk(buffer: string): { events: Array<{ event: string; data: string }>; rest: string } {
  const events: Array<{ event: string; data: string }> = [];
  const parts = buffer.split("\n\n");
  const rest = parts.pop() || "";
  for (const part of parts) {
    let event = "message";
    const data: string[] = [];
    for (const line of part.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      if (line.startsWith("data:")) data.push(line.slice(5).trim());
    }
    events.push({ event, data: data.join("\n") });
  }
  return { events, rest };
}

export const llmApi = {
  async completeText(body: CompleteBody, opts: CompleteOptions = {}): Promise<string> {
    const res = await api<Response>("/llm/complete", {
      method: "POST",
      body,
      headers: opts.token ? { Authorization: `Bearer ${opts.token}` } : undefined,
      raw: true,
      signal: opts.signal,
    });
    if (!res.body) return "";
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let output = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parsed = parseSseChunk(buffer);
      buffer = parsed.rest;
      for (const item of parsed.events) {
        const payload = item.data ? JSON.parse(item.data) : {};
        if (item.event === "token") {
          const delta = String(payload.delta || "");
          output += delta;
          opts.onToken?.(delta);
        }
        if (item.event === "done") {
          if (Array.isArray(payload.warnings) && payload.warnings.length) {
            opts.onWarnings?.(payload.warnings.map((w: unknown) => String(w)));
          }
          return String(payload.text ?? output);
        }
        if (item.event === "error") {
          throw new ApiError(502, String(payload.detail || "LLM request failed"), payload);
        }
      }
    }
    return output;
  },
};

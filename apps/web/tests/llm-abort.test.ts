import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { llmApi } from "../src/api/llm";

const originalFetch = globalThis.fetch;

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  globalThis.fetch = originalFetch;
});

describe("llmApi.completeText abort signal", () => {
  it("forwards the abort signal to fetch and throws when pre-aborted", async () => {
    const controller = new AbortController();
    controller.abort();

    const fetchMock = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      // fetch should reject when handed an already-aborted signal.
      if (init?.signal?.aborted) {
        throw new DOMException("The user aborted a request.", "AbortError");
      }
      return new Response("", { status: 200 });
    });
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    await expect(
      llmApi.completeText(
        { purpose: "interpret", prompt: "hi" },
        { signal: controller.signal },
      ),
    ).rejects.toBeInstanceOf(DOMException);

    expect(fetchMock).toHaveBeenCalledOnce();
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.signal).toBe(controller.signal);
  });

  it("aborts an in-flight stream when the signal fires mid-response", async () => {
    const controller = new AbortController();

    const stream = new ReadableStream<Uint8Array>({
      start(streamController) {
        const encoder = new TextEncoder();
        streamController.enqueue(encoder.encode("event: token\ndata: {\"delta\":\"hello\"}\n\n"));
        // Keep the stream open; the abort happens before the next chunk arrives.
        controller.signal.addEventListener("abort", () => {
          streamController.error(new DOMException("aborted", "AbortError"));
        });
      },
    });

    const fetchMock = vi.fn(async () => new Response(stream, { status: 200 }));
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const promise = llmApi.completeText(
      { purpose: "interpret", prompt: "hi" },
      { signal: controller.signal },
    );

    // Let the first chunk land, then cancel.
    await new Promise((resolve) => setTimeout(resolve, 0));
    controller.abort();

    await expect(promise).rejects.toBeInstanceOf(DOMException);
  });
});

import { afterEach, describe, expect, it, vi } from "vitest";
import { widgetsApi } from "../src/api/widgets";

describe("widgetsApi AI thread methods", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("creates, reads, and appends AI thread records with the expected routes", async () => {
    const fetchMock = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) => {
      return new Response(
        JSON.stringify({
          id: "thread-1",
          widget_id: "widget-1",
          title: "Build poll",
          compact_summary: {},
          messages: [],
        }),
        { status: 201 },
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    await widgetsApi.createAiThread("widget-1", {
      title: "Build poll",
      compact_summary: { intent: "poll" },
    });
    await widgetsApi.getAiThread("widget-1");
    await widgetsApi.appendAiMessage("widget-1", "thread-1", {
      role: "assistant",
      message_type: "plan",
      content: { steps: ["draft"] },
      revision_id: "rev-1",
    });

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/v1/widgets/widget-1/ai-thread");
    expect(fetchMock.mock.calls[0][1]?.method).toBe("POST");
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({
      title: "Build poll",
      compact_summary: { intent: "poll" },
    });
    expect(String(fetchMock.mock.calls[1][0])).toBe("/api/v1/widgets/widget-1/ai-thread");
    expect(fetchMock.mock.calls[1][1]?.method).toBe("GET");
    expect(String(fetchMock.mock.calls[2][0])).toBe(
      "/api/v1/widgets/widget-1/ai-thread/thread-1/messages",
    );
    expect(fetchMock.mock.calls[2][1]?.method).toBe("POST");
    expect(JSON.parse(String(fetchMock.mock.calls[2][1]?.body))).toEqual({
      role: "assistant",
      message_type: "plan",
      content: { steps: ["draft"] },
      revision_id: "rev-1",
    });
  });
});

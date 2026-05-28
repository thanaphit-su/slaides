import { afterEach, describe, expect, it, vi } from "vitest";
import { widgetsApi } from "../src/api/widgets";

describe("widgetsApi revision methods", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("lists revisions and rolls back through the expected routes", async () => {
    const fetchMock = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) => {
      return new Response(
        JSON.stringify([
          {
            id: "rev-1",
            widget_id: "widget-1",
            version_number: 1,
            html: "<p>v1</p>",
            js: null,
            css: null,
            props_schema: {},
            example_props: {},
            behavior: { kind: "quiet" },
            ai_spec: {},
            created_reason: "create",
          },
        ]),
        { status: 200 },
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    await widgetsApi.listRevisions("widget-1");
    await widgetsApi.rollbackRevision("widget-1", "rev-1");

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/v1/widgets/widget-1/revisions");
    expect(fetchMock.mock.calls[0][1]?.method).toBe("GET");
    expect(String(fetchMock.mock.calls[1][0])).toBe(
      "/api/v1/widgets/widget-1/revisions/rev-1/rollback",
    );
    expect(fetchMock.mock.calls[1][1]?.method).toBe("POST");
  });
});

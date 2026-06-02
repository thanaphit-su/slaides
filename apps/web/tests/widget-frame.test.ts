import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { isReactive, nextTick, reactive } from "vue";
import WidgetFrame from "../src/widgets/WidgetFrame.vue";
import type { Widget } from "../src/api/types";

function fakeWidget(): Widget {
  return {
    id: "w-1",
    name: "Test",
    kind: "poll",
    description: null,
    html: "<div id='root'></div>",
    js: "window.slaides && window.slaides.on && window.slaides.on('props', function(){});",
    css: "#root { color: var(--foreground); }",
    props_schema: {},
    tags: [],
    version: "v0.1",
  } as unknown as Widget;
}

describe("WidgetFrame reactivity", () => {
  it("does not reload the iframe when bootProps mutate", async () => {
    const bootProps = reactive<Record<string, unknown>>({ question: "Initial?", options: ["A", "B"] });
    const wrapper = mount(WidgetFrame, {
      props: { widget: fakeWidget(), placementId: "p-1", bootProps, role: "instructor" },
    });

    const iframe = wrapper.find("iframe").element as HTMLIFrameElement;
    const initialSrc = iframe.getAttribute("srcdoc") || "";
    expect(initialSrc).toContain("Initial?");

    bootProps.question = "Edited?";
    bootProps.options = ["A", "B", "C"];
    await nextTick();

    const afterSrc = iframe.getAttribute("srcdoc") || "";
    // srcdoc must remain unchanged so the iframe is not reloaded.
    expect(afterSrc).toBe(initialSrc);
    // And the snapshot remains the initial values, not the mutated ones.
    expect(afterSrc).toContain("Initial?");
    expect(afterSrc).not.toContain("Edited?");
  });

  it("posts live prop updates as cloneable plain objects", async () => {
    const bootProps = reactive<Record<string, unknown>>({
      question: "Initial?",
      nested: { label: "A" },
    });
    const wrapper = mount(WidgetFrame, {
      props: { widget: fakeWidget(), placementId: "p-1", bootProps, role: "instructor" },
    });
    const iframe = wrapper.find("iframe").element as HTMLIFrameElement;
    const postMessage = vi.fn();
    Object.defineProperty(iframe, "contentWindow", {
      configurable: true,
      value: { postMessage },
    });

    bootProps.question = "Edited?";
    bootProps.nested = { label: "B" };
    await nextTick();

    expect(postMessage).toHaveBeenCalledWith(
      {
        slaides: true,
        type: "props.update",
        payload: { props: { question: "Edited?", nested: { label: "B" } } },
      },
      "*",
    );
    const payload = postMessage.mock.calls[0]?.[0]?.payload as { props?: Record<string, unknown> };
    expect(isReactive(payload)).toBe(false);
    expect(isReactive(payload.props)).toBe(false);
    expect(isReactive(payload.props?.nested)).toBe(false);
  });

  it("reloads the iframe when the widget identity changes", async () => {
    const bootProps = { x: 1 };
    const wrapper = mount(WidgetFrame, {
      props: { widget: fakeWidget(), placementId: "p-1", bootProps, role: "instructor" },
    });
    const iframe = wrapper.find("iframe").element as HTMLIFrameElement;
    const initialSrc = iframe.getAttribute("srcdoc") || "";

    const replaced: Widget = { ...fakeWidget(), html: "<div id='different'></div>" };
    await wrapper.setProps({ widget: replaced });

    const afterSrc = iframe.getAttribute("srcdoc") || "";
    expect(afterSrc).not.toBe(initialSrc);
    expect(afterSrc).toContain("different");
  });

  it("iframe sandbox grants allow-forms so submit handlers can preventDefault without the browser warning", () => {
    const wrapper = mount(WidgetFrame, {
      props: { widget: fakeWidget(), placementId: "p-1", bootProps: {}, role: "audience" },
    });
    const sandbox = wrapper.find("iframe").attributes("sandbox") || "";
    expect(sandbox.split(/\s+/)).toContain("allow-scripts");
    expect(sandbox.split(/\s+/)).toContain("allow-forms");
  });

  it("bakes participant.display_name into the iframe srcdoc when the prop is provided", () => {
    const wrapper = mount(WidgetFrame, {
      props: {
        widget: fakeWidget(),
        placementId: "p-1",
        bootProps: {},
        role: "audience",
        participant: { display_name: "Alice", anon: false },
      },
    });
    const srcdoc = wrapper.find("iframe").attributes("srcdoc") || "";
    expect(srcdoc).toContain('"display_name":"Alice"');
    expect(srcdoc).toContain('"anon":false');
  });

  it("defaults participant.display_name to null when the prop is omitted (presenter/preview)", () => {
    const wrapper = mount(WidgetFrame, {
      props: { widget: fakeWidget(), placementId: "p-1", bootProps: {}, role: "preview" },
    });
    const srcdoc = wrapper.find("iframe").attributes("srcdoc") || "";
    expect(srcdoc).toContain('"display_name":null');
  });

  it("does NOT bake the inspector script when not in preview context", () => {
    delete (window as unknown as { __slaides_preview?: boolean }).__slaides_preview;
    const wrapper = mount(WidgetFrame, {
      props: { widget: fakeWidget(), placementId: "p-1", bootProps: {}, role: "audience" },
    });
    const srcdoc = wrapper.find("iframe").attributes("srcdoc") || "";
    // Inspector is gated on window.__slaides_preview, which production audience
    // pages never set. The "preview.pick" string only appears in the inspector.
    expect(srcdoc).not.toContain("preview.pick");
  });

  it("bakes the widget selection bridge for non-thumbnail frames", () => {
    const wrapper = mount(WidgetFrame, {
      props: { widget: fakeWidget(), placementId: "p-1", bootProps: {}, role: "audience" },
    });
    const srcdoc = wrapper.find("iframe").attributes("srcdoc") || "";
    expect(srcdoc).toContain("widget.selection");
    expect(srcdoc).toContain("selectionchange");
    expect(srcdoc).toContain("contextmenu");
  });

  it("does not bake the widget selection bridge for thumbnails", () => {
    const wrapper = mount(WidgetFrame, {
      props: { widget: fakeWidget(), placementId: "p-1", bootProps: {}, role: "thumbnail" },
    });
    const srcdoc = wrapper.find("iframe").attributes("srcdoc") || "";
    expect(srcdoc).not.toContain("widget.selection");
  });

  it("emits iframe text selection using viewport coordinates", () => {
    const wrapper = mount(WidgetFrame, {
      props: { widget: fakeWidget(), placementId: "p-1", bootProps: {}, role: "audience" },
    });
    const iframe = wrapper.find("iframe").element as HTMLIFrameElement;
    const fakeWin = {};
    Object.defineProperty(iframe, "contentWindow", { configurable: true, value: fakeWin });
    iframe.getBoundingClientRect = vi.fn(() => ({
      left: 100,
      top: 200,
      width: 320,
      height: 180,
      right: 420,
      bottom: 380,
      x: 100,
      y: 200,
      toJSON: () => ({}),
    }));

    const ev = new MessageEvent("message", {
      data: {
        slaides: true,
        type: "widget.selection",
        payload: {
          text: " selected widget text ",
          rect: { left: 20, top: 30, width: 80, height: 16 },
          contextMenu: true,
        },
      },
    });
    Object.defineProperty(ev, "source", { configurable: true, value: fakeWin });
    window.dispatchEvent(ev);

    expect(wrapper.emitted("selection")?.[0]).toEqual([
      { x: 160, y: 230, text: "selected widget text", contextMenu: true },
    ]);
  });

  it("allows https: in the iframe CSP img-src so URL-driven widgets (Carousel) can load images", () => {
    const wrapper = mount(WidgetFrame, {
      props: { widget: fakeWidget(), placementId: "p-1", bootProps: {}, role: "audience" },
    });
    const srcdoc = wrapper.find("iframe").attributes("srcdoc") || "";
    // The CSP meta tag must permit https: image fetches alongside data:.
    // Without this, the Carousel starter widget renders empty.
    expect(srcdoc).toMatch(/img-src\s+data:\s+https:/);
  });

  it("replays persisted per-viewer state into boot.state on (re)mount", () => {
    // Simulate a prior submission saved by the host before the iframe was
    // remounted (audience navigated away from the slide and back).
    sessionStorage.setItem(
      "slaides:wstate:w-1:p-1:audience",
      JSON.stringify({ answer: "my saved answer" }),
    );
    try {
      const wrapper = mount(WidgetFrame, {
        props: { widget: fakeWidget(), placementId: "p-1", bootProps: {}, role: "audience" },
      });
      const srcdoc = wrapper.find("iframe").attributes("srcdoc") || "";
      // boot.state is baked into __slaides_boot so getState() returns it
      // synchronously at widget script-eval time.
      expect(srcdoc).toContain('"state":{"answer":"my saved answer"}');
    } finally {
      sessionStorage.removeItem("slaides:wstate:w-1:p-1:audience");
    }
  });

  it("persists a state.set message from the iframe to host sessionStorage", () => {
    const key = "slaides:wstate:w-1:p-1:audience";
    sessionStorage.removeItem(key);
    try {
      const wrapper = mount(WidgetFrame, {
        props: { widget: fakeWidget(), placementId: "p-1", bootProps: {}, role: "audience" },
      });
      const iframe = wrapper.find("iframe").element as HTMLIFrameElement;
      const fakeWin = {};
      // The host identifies the sender by contentWindow identity (null-origin
      // sandbox makes origin checks meaningless).
      Object.defineProperty(iframe, "contentWindow", { configurable: true, value: fakeWin });

      const ev = new MessageEvent("message", {
        data: { slaides: true, type: "state.set", payload: { key: "answer", value: "hello" } },
      });
      Object.defineProperty(ev, "source", { configurable: true, value: fakeWin });
      window.dispatchEvent(ev);

      expect(JSON.parse(sessionStorage.getItem(key) || "{}")).toEqual({ answer: "hello" });
    } finally {
      sessionStorage.removeItem(key);
    }
  });

  it("scopes per-viewer state by participant ref so co-located audiences don't collide", () => {
    // The multi-audience preview harness mounts every audience iframe in one
    // same-origin page → one shared sessionStorage. A role-only key made them
    // clobber each other so a non-submitter saw the last writer's answer.
    const keyAlice = "slaides:wstate:w-1:p-1:alice";
    const keyBob = "slaides:wstate:w-1:p-1:bob";
    sessionStorage.setItem(keyAlice, JSON.stringify({ answer: "Hi" }));
    sessionStorage.setItem(keyBob, JSON.stringify({ answer: "Hello" }));
    try {
      // Bob's iframe replays Bob's own answer, not a shared latest.
      const bob = mount(WidgetFrame, {
        props: {
          widget: fakeWidget(),
          placementId: "p-1",
          bootProps: {},
          role: "audience",
          participant: { ref: "bob" },
        },
      });
      expect(bob.find("iframe").attributes("srcdoc") || "").toContain('"state":{"answer":"Hello"}');

      // Carol never submitted → her own (empty) slot, NOT Bob's "Hello".
      const carol = mount(WidgetFrame, {
        props: {
          widget: fakeWidget(),
          placementId: "p-1",
          bootProps: {},
          role: "audience",
          participant: { ref: "carol" },
        },
      });
      expect(carol.find("iframe").attributes("srcdoc") || "").toContain('"state":{}');
    } finally {
      sessionStorage.removeItem(keyAlice);
      sessionStorage.removeItem(keyBob);
    }
  });

  it("persists a state.set message under the participant-scoped key", () => {
    const scoped = "slaides:wstate:w-1:p-1:alice";
    const roleOnly = "slaides:wstate:w-1:p-1:audience";
    sessionStorage.removeItem(scoped);
    sessionStorage.removeItem(roleOnly);
    try {
      const wrapper = mount(WidgetFrame, {
        props: {
          widget: fakeWidget(),
          placementId: "p-1",
          bootProps: {},
          role: "audience",
          participant: { ref: "alice" },
        },
      });
      const iframe = wrapper.find("iframe").element as HTMLIFrameElement;
      const fakeWin = {};
      Object.defineProperty(iframe, "contentWindow", { configurable: true, value: fakeWin });
      const ev = new MessageEvent("message", {
        data: { slaides: true, type: "state.set", payload: { key: "answer", value: "Hi" } },
      });
      Object.defineProperty(ev, "source", { configurable: true, value: fakeWin });
      window.dispatchEvent(ev);

      expect(JSON.parse(sessionStorage.getItem(scoped) || "{}")).toEqual({ answer: "Hi" });
      // The old role-only key must NOT be written — that was the collision.
      expect(sessionStorage.getItem(roleOnly)).toBeNull();
    } finally {
      sessionStorage.removeItem(scoped);
      sessionStorage.removeItem(roleOnly);
    }
  });

  it("does not persist viewer state without a placementId (editor preview is ephemeral)", () => {
    const wrapper = mount(WidgetFrame, {
      props: { widget: fakeWidget(), placementId: "", bootProps: {}, role: "preview" },
    });
    const srcdoc = wrapper.find("iframe").attributes("srcdoc") || "";
    // No placement → boot.state is an empty object, nothing keyed in storage.
    expect(srcdoc).toContain('"state":{}');
  });

  it("bakes the inspector script when window.__slaides_preview is true", () => {
    (window as unknown as { __slaides_preview?: boolean }).__slaides_preview = true;
    try {
      const wrapper = mount(WidgetFrame, {
        props: { widget: fakeWidget(), placementId: "p-1", bootProps: {}, role: "audience" },
      });
      const srcdoc = wrapper.find("iframe").attributes("srcdoc") || "";
      expect(srcdoc).toContain("preview.pick");
      expect(srcdoc).toContain("preview.inspect");
    } finally {
      delete (window as unknown as { __slaides_preview?: boolean }).__slaides_preview;
    }
  });
});

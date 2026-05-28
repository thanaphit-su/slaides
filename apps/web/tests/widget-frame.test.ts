import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import { nextTick, reactive } from "vue";
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

  it("allows https: in the iframe CSP img-src so URL-driven widgets (Carousel) can load images", () => {
    const wrapper = mount(WidgetFrame, {
      props: { widget: fakeWidget(), placementId: "p-1", bootProps: {}, role: "audience" },
    });
    const srcdoc = wrapper.find("iframe").attributes("srcdoc") || "";
    // The CSP meta tag must permit https: image fetches alongside data:.
    // Without this, the Carousel starter widget renders empty.
    expect(srcdoc).toMatch(/img-src\s+data:\s+https:/);
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

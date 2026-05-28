import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import WidgetThumbnail from "../src/components/WidgetThumbnail.vue";
import type { Widget } from "../src/api/types";

function fakeWidget(overrides: Partial<Widget> = {}): Widget {
  return {
    id: "w-1",
    deck_id: "deck-A",
    derived_from_id: null,
    name: "Quick Poll",
    kind: "poll",
    description: "A live audience poll.",
    html: "<section class='poll'>Vote!</section>",
    js: "window.alert('this should not run');",
    css: ".poll { color: blue; }",
    props_schema: {},
    tags: [],
    version: "v0.1",
    behavior: { kind: "loud", aggregator: "tally" },
    ...overrides,
  } as Widget;
}

describe("WidgetThumbnail", () => {
  it("renders through WidgetFrame with example props as boot props", () => {
    const wrapper = mount(WidgetThumbnail, {
      props: {
        widget: fakeWidget({
          html: "<section class='poll'><span id='title'></span></section>",
          js: "document.getElementById('title').textContent = window.slaides.props.title;",
          example_props: { title: "Preview title" },
        }),
        currentDeckId: "deck-A",
      },
    });
    const iframe = wrapper.find("iframe");
    const src = iframe.attributes("srcdoc") || "";
    expect(src).toContain("<section class='poll'><span id='title'></span></section>");
    expect(src).toContain(".poll { color: blue; }");
    expect(src).toContain("Preview title");
    expect(src).toContain("window.slaides.props.title");
    expect(iframe.attributes("sandbox")).toBe("allow-scripts allow-forms");
  });

  it("injects the host theme tokens so widget CSS resolves the same as in the canvas", () => {
    const wrapper = mount(WidgetThumbnail, {
      props: { widget: fakeWidget(), currentDeckId: "deck-A" },
    });
    const src = wrapper.find("iframe").attributes("srcdoc") || "";
    // Load-bearing tokens — starter widgets reference all of these.
    for (const token of [
      "--card:",
      "--card-foreground:",
      "--border:",
      "--background:",
      "--foreground:",
      "--accent:",
      "--accent-soft:",
      "--muted-foreground:",
      "--font-sans:",
      "--font-serif:",
      "--font-mono:",
      "--radius:",
    ]) {
      expect(src).toContain(token);
    }
  });

  it("is draggable and emits dragstart with the widget id + deck id payload", () => {
    const wrapper = mount(WidgetThumbnail, {
      props: { widget: fakeWidget(), currentDeckId: "deck-A" },
    });
    const card = wrapper.find('[data-testid="widget-thumbnail"]');
    expect(card.attributes("draggable")).toBe("true");

    let payload: string | null = null;
    const dataTransfer = {
      effectAllowed: "",
      setData: (mime: string, value: string) => {
        if (mime === "application/x-slaides-widget") payload = value;
      },
    };
    card.element.dispatchEvent(
      Object.assign(new Event("dragstart", { bubbles: true }), { dataTransfer }),
    );
    expect(payload).not.toBeNull();
    expect(JSON.parse(payload!)).toEqual({ widget_id: "w-1", deck_id: "deck-A" });
  });

  it("shows the cross-deck badge when the widget belongs to another deck", () => {
    const wrapper = mount(WidgetThumbnail, {
      props: { widget: fakeWidget({ deck_id: "deck-OTHER" }), currentDeckId: "deck-A" },
    });
    expect(wrapper.find(".widget-thumbnail-crossdeck").exists()).toBe(true);
  });

  it("does NOT show the cross-deck badge when widget is from current deck", () => {
    const wrapper = mount(WidgetThumbnail, {
      props: { widget: fakeWidget({ deck_id: "deck-A" }), currentDeckId: "deck-A" },
    });
    expect(wrapper.find(".widget-thumbnail-crossdeck").exists()).toBe(false);
  });
});

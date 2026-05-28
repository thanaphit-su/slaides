import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import SlideCanvas from "../src/components/SlideCanvas.vue";
import type { SlideWidgetEmbed, Widget } from "../src/api/types";

describe("SlideCanvas widget revision rendering", () => {
  it("renders the current widget body after AI Adjust instead of the attached revision", async () => {
    const placement: SlideWidgetEmbed = {
      placement_id: "pid",
      widget_id: "widget-1",
      revision_id: "rev-1",
      revision: {
        id: "rev-1",
        widget_id: "widget-1",
        version_number: 1,
        html: "<p>old revision</p>",
        js: null,
        css: null,
        props_schema: {},
        example_props: {},
        behavior: { kind: "quiet" },
        ai_spec: {},
        created_reason: "create",
      },
      kind: "custom",
      name: "Widget",
      props: {},
    };
    const current: Widget = {
      id: "widget-1",
      deck_id: "deck-1",
      derived_from_id: null,
      name: "Widget",
      kind: "custom",
      description: null,
      html: "<p>current revision</p>",
      js: null,
      css: null,
      props_schema: {},
      tags: [],
      version: "v0.1",
      behavior: { kind: "quiet" },
      current_revision_id: "rev-2",
      example_props: {},
      ai_spec: {},
    };

    const wrapper = mount(SlideCanvas, {
      props: {
        markdown: "{{widget:pid}}",
        slideId: "slide-1",
        widgets: [placement],
        widgetRev: 1,
        getWidget: () => current,
      },
    });

    const srcdoc = wrapper.find("iframe").attributes("srcdoc") || "";
    expect(srcdoc).toContain("<p>current revision</p>");
    expect(srcdoc).not.toContain("<p>old revision</p>");
  });
});

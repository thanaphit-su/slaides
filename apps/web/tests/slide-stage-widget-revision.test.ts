import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import SlideStage from "../src/components/SlideStage.vue";
import { useWidgetsStore } from "../src/stores/widgets";
import type { Slide, Widget } from "../src/api/types";

describe("SlideStage widget revision rendering", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("renders current widget source for active live deck slides", () => {
    const store = useWidgetsStore();
    const current: Widget = {
      id: "widget-1",
      deck_id: "deck-1",
      derived_from_id: null,
      name: "Widget",
      kind: "custom",
      description: null,
      html: "<p>current live style</p>",
      js: null,
      css: ".card{border-color:var(--primary)}",
      props_schema: {},
      tags: [],
      version: "v0.1",
      behavior: { kind: "quiet" },
      current_revision_id: "rev-2",
      example_props: {},
      ai_spec: {},
    };
    store.cache[current.id] = current;

    const slide: Slide = {
      id: "slide-1",
      deck_id: "deck-1",
      section_id: null,
      position: 0,
      kicker: null,
      markdown: "{{widget:pid}}",
      updated_at: new Date().toISOString(),
      widgets: [
        {
          placement_id: "pid",
          widget_id: "widget-1",
          revision_id: "rev-1",
          revision: {
            id: "rev-1",
            widget_id: "widget-1",
            version_number: 1,
            html: "<p>old live style</p>",
            js: null,
            css: ".card{border-color:var(--muted)}",
            props_schema: {},
            example_props: {},
            behavior: { kind: "quiet" },
            ai_spec: {},
            created_reason: "create",
          },
          kind: "custom",
          name: "Widget",
          props: {},
        },
      ],
    };

    const wrapper = mount(SlideStage, {
      props: { slide, role: "instructor" },
    });

    const srcdoc = wrapper.find("iframe").attributes("srcdoc") || "";
    expect(srcdoc).toContain("<p>current live style</p>");
    expect(srcdoc).toContain(".card{border-color:var(--primary)}");
    expect(srcdoc).not.toContain("<p>old live style</p>");
    expect(srcdoc).not.toContain(".card{border-color:var(--muted)}");
  });
});

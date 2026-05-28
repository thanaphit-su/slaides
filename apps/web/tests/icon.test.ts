import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import Icon from "../src/components/Icon.vue";

describe("Icon", () => {
  it("renders mapped icons through Lucide", () => {
    const wrapper = mount(Icon, { props: { name: "upload", size: 14 } });
    const svg = wrapper.get("svg");

    expect(svg.classes()).toContain("lucide");
    expect(svg.attributes("width")).toBe("14");
  });

  it("supports existing alias names used by call sites", () => {
    const wrapper = mount(Icon, { props: { name: "chevron_up", size: 12 } });
    const svg = wrapper.get("svg");

    expect(svg.classes()).toContain("lucide");
    expect(svg.classes()).toContain("lucide-chevron-up");
  });
});

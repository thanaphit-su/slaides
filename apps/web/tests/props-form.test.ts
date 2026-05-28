import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import PropsForm from "../src/components/PropsForm.vue";

describe("PropsForm", () => {
  it("shows a placeholder when the widget exposes no props", () => {
    const wrapper = mount(PropsForm, { props: { schema: {}, modelValue: {} } });
    expect(wrapper.text()).toContain("This widget exposes no editable properties");
  });

  it("renders a string input that emits update:modelValue on change", async () => {
    const wrapper = mount(PropsForm, {
      props: {
        schema: { properties: { question: { type: "string", default: "Pick one" } } },
        modelValue: { question: "Pick one" },
      },
    });
    const input = wrapper.find("input[type='text']");
    expect((input.element as HTMLInputElement).value).toBe("Pick one");

    await input.setValue("Capital of France?");
    const emitted = wrapper.emitted("update:modelValue");
    expect(emitted).toBeTruthy();
    expect(emitted![emitted!.length - 1][0]).toEqual({ question: "Capital of France?" });
  });

  it("renders a select for enum and rejects values outside the list", async () => {
    const wrapper = mount(PropsForm, {
      props: {
        schema: { properties: { mode: { type: "string", enum: ["a", "b", "c"] } } },
        modelValue: { mode: "a" },
      },
    });
    const select = wrapper.find("select");
    const options = select.findAll("option").map((o) => o.attributes("value"));
    // First option is the empty "Choose…" placeholder; the rest mirror the enum.
    expect(options.slice(1)).toEqual(["a", "b", "c"]);
  });

  it("supports adding, removing, and reordering array items", async () => {
    const wrapper = mount(PropsForm, {
      props: {
        schema: {
          properties: {
            choices: {
              type: "array",
              items: {
                type: "object",
                properties: {
                  id: { type: "string" },
                  label: { type: "string" },
                },
              },
            },
          },
        },
        modelValue: { choices: [{ id: "a", label: "A" }, { id: "b", label: "B" }] },
      },
    });

    const addBtn = wrapper.findAll("button").find((b) => b.text().includes("Add"))!;
    await addBtn.trigger("click");
    let last = wrapper.emitted("update:modelValue")!.at(-1)![0] as Record<string, any>;
    expect((last.choices as unknown[])).toHaveLength(3);

    // Simulate parent committing the new value back so the next interaction
    // sees it (parent owns state by contract).
    await wrapper.setProps({ modelValue: last });

    // Move first row down.
    const moveDown = wrapper
      .findAll("button")
      .find((b) => b.attributes("title")?.includes("down"))!;
    await moveDown.trigger("click");
    last = wrapper.emitted("update:modelValue")!.at(-1)![0] as Record<string, any>;
    expect((last.choices as { id: string }[])[0].id).toBe("b");
    expect((last.choices as { id: string }[])[1].id).toBe("a");

    await wrapper.setProps({ modelValue: last });

    // Remove the first row.
    const removeBtn = wrapper
      .findAll("button")
      .filter((b) => b.attributes("title")?.startsWith("Remove"))[0];
    await removeBtn.trigger("click");
    last = wrapper.emitted("update:modelValue")!.at(-1)![0] as Record<string, any>;
    expect((last.choices as unknown[])).toHaveLength(2);
  });

  it("resolves enum.from from a sibling array", async () => {
    const wrapper = mount(PropsForm, {
      props: {
        schema: {
          properties: {
            choices: {
              type: "array",
              items: {
                type: "object",
                properties: { id: { type: "string" } },
              },
            },
            correct_answer: { type: "string", "enum.from": "choices.id" },
          },
        },
        modelValue: {
          choices: [{ id: "alpha" }, { id: "beta" }],
          correct_answer: "alpha",
        },
      },
    });

    await nextTick();
    const select = wrapper.find("select");
    const options = select.findAll("option").map((o) => o.attributes("value"));
    // The select gets the enum.from options pulled from the live sibling array.
    expect(options.slice(1)).toEqual(["alpha", "beta"]);
  });

  it("renders boolean as a checkbox toggle", async () => {
    const wrapper = mount(PropsForm, {
      props: {
        schema: { properties: { allow_other: { type: "boolean", default: false } } },
        modelValue: { allow_other: false },
      },
    });
    const checkbox = wrapper.find("input[type='checkbox']");
    expect((checkbox.element as HTMLInputElement).checked).toBe(false);
    await checkbox.setValue(true);
    const last = wrapper.emitted("update:modelValue")!.at(-1)![0] as { allow_other: boolean };
    expect(last.allow_other).toBe(true);
  });
});

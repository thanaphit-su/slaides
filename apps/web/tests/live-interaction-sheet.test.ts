import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import LiveInteractionSheet from "../src/components/LiveInteractionSheet.vue";

describe("LiveInteractionSheet (poll)", () => {
  it("disables Launch until a question and at least 2 non-empty choices are provided", async () => {
    const wrapper = mount(LiveInteractionSheet, { props: { kind: "poll" } });

    const launch = () => wrapper.findAll("button").find((b) => b.text() === "Launch")!;
    expect(launch().attributes("disabled")).toBeDefined();

    await wrapper.find("input.input").setValue("Best season?");
    // Still disabled because choices are empty.
    expect(launch().attributes("disabled")).toBeDefined();

    const inputs = wrapper.findAll("input.input");
    // inputs[0] is the question. The next two are the default empty choice rows.
    await inputs[1].setValue("Spring");
    await inputs[2].setValue("Fall");
    expect(launch().attributes("disabled")).toBeUndefined();
  });

  it("Yes/No template prefills the choice list", async () => {
    const wrapper = mount(LiveInteractionSheet, { props: { kind: "poll" } });
    const tplButton = wrapper.findAll("button").find((b) => b.text() === "Yes / No")!;
    await tplButton.trigger("click");
    const choiceInputs = wrapper.findAll("input.input").slice(1);
    expect((choiceInputs[0].element as HTMLInputElement).value).toBe("Yes");
    expect((choiceInputs[1].element as HTMLInputElement).value).toBe("No");
  });

  it("emits a launch event with a normalized poll spec", async () => {
    const wrapper = mount(LiveInteractionSheet, { props: { kind: "poll" } });
    await wrapper.find("input.input").setValue("Pick one");
    const inputs = wrapper.findAll("input.input");
    await inputs[1].setValue("Apple");
    await inputs[2].setValue("Pear");
    const launchBtn = wrapper.findAll("button").find((b) => b.text() === "Launch")!;
    await launchBtn.trigger("click");

    const events = wrapper.emitted("launch");
    expect(events).toBeTruthy();
    const payload = (events as unknown[][])[0][0] as {
      kind: string;
      spec: { type: string; question: string; choices: { id: string; label: string }[] };
    };
    expect(payload.kind).toBe("poll");
    expect(payload.spec.type).toBe("poll");
    expect(payload.spec.question).toBe("Pick one");
    expect(payload.spec.choices.map((c) => c.label)).toEqual(["Apple", "Pear"]);
  });
});

describe("LiveInteractionSheet (question)", () => {
  it("requires a prompt before Launch is enabled and emits the question spec", async () => {
    const wrapper = mount(LiveInteractionSheet, { props: { kind: "question" } });
    const launch = () => wrapper.findAll("button").find((b) => b.text() === "Launch")!;
    expect(launch().attributes("disabled")).toBeDefined();

    await wrapper.find("textarea").setValue("What's unclear?");
    expect(launch().attributes("disabled")).toBeUndefined();
    await launch().trigger("click");

    const events = wrapper.emitted("launch");
    expect(events).toBeTruthy();
    const payload = (events as unknown[][])[0][0] as {
      kind: string;
      spec: { type: string; prompt: string };
    };
    expect(payload.kind).toBe("question");
    expect(payload.spec.type).toBe("question");
    expect(payload.spec.prompt).toBe("What's unclear?");
  });
});

describe("LiveInteractionSheet (random audience)", () => {
  it("emits a launch event with the requested audience count", async () => {
    const wrapper = mount(LiveInteractionSheet, { props: { kind: "random" } });
    const input = wrapper.find("input.input");
    await input.setValue("3");
    const launch = wrapper.findAll("button").find((b) => b.text() === "Launch")!;
    expect(launch.attributes("disabled")).toBeUndefined();
    await launch.trigger("click");

    const events = wrapper.emitted("launch");
    expect(events).toBeTruthy();
    const payload = (events as unknown[][])[0][0] as {
      kind: string;
      spec: { type: string; count: number };
    };
    expect(payload.kind).toBe("random");
    expect(payload.spec).toEqual({ type: "random", count: 3 });
  });
});

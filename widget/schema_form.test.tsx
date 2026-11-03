import { act, fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import widget, { messages, type Model } from "./schema_form";

/** anywidget's model, held in memory: what Python would see after save_changes. */
function fakeModel(state: Record<string, unknown>) {
  const listeners = new Map<string, Set<() => void>>();
  const saved: Record<string, unknown>[] = [];
  const model: Model = {
    get: (name) => state[name],
    set: (name, value) => {
      state[name] = value;
    },
    save_changes: () => saved.push({ ...state }),
    on: (event, callback) => {
      if (!listeners.has(event)) listeners.set(event, new Set());
      listeners.get(event)?.add(callback);
    },
    off: (event, callback) => listeners.get(event)?.delete(callback),
  };
  const emit = (event: string) => listeners.get(event)?.forEach((callback) => callback());
  return { model, saved, emit, listeners };
}

const schema = {
  type: "object",
  required: ["site"],
  properties: { site: { type: "string", title: "Site", minLength: 2 } },
};
const uischema = { type: "VerticalLayout", elements: [{ type: "Control", scope: "#/properties/site" }] };
const settle = () => act(() => new Promise((resolve) => setTimeout(resolve, 30)));

describe("SchemaFormWidget's front end", () => {
  it("draws the form and sends its data and errors back", async () => {
    const { model, saved, emit, listeners } = fakeModel({ schema, uischema, value: { site: "x" }, errors: [] });
    const el = document.createElement("div");
    document.body.append(el);
    let cleanup: () => void = () => {};
    act(() => {
      cleanup = widget.render({ model, el });
    });
    await settle();
    expect((screen.getByLabelText("Site") as HTMLInputElement).value).toBe("x");
    expect(saved.at(-1)?.errors).toEqual([{ path: "/site", message: expect.stringContaining("2") }]);
    expect(el.querySelector("style")?.textContent).toContain("rounded-control");

    fireEvent.change(screen.getByLabelText("Site"), { target: { value: "Tartu" } });
    await settle();
    expect(saved.at(-1)).toMatchObject({ value: { site: "Tartu" }, errors: [] });

    model.set("value", { site: "Pärnu" });
    act(() => emit("change:value"));
    await settle();
    expect((screen.getByLabelText("Site") as HTMLInputElement).value).toBe("Pärnu");

    act(() => cleanup());
    expect([...listeners.values()].every((l) => l.size === 0)).toBe(true);
    el.remove();
  });

  it("starts from empty data and registers Tailwind's properties once", async () => {
    const { model, saved } = fakeModel({ schema, uischema });
    for (let i = 0; i < 2; i++) {
      const el = document.createElement("div");
      document.body.append(el);
      act(() => {
        widget.render({ model, el });
      });
    }
    await settle();
    expect(saved.at(-1)?.value).toEqual({});
    const registered = document.querySelectorAll("#sustenaut-schema-form-properties");
    expect(registered).toHaveLength(1);
    expect(registered[0].textContent).toMatch(/^@property --tw-/);
  });

  it("reports errors without a path or message as empty strings", () => {
    expect(messages(undefined)).toEqual([]);
    expect(messages([{}])).toEqual([{ path: "", message: "" }]);
  });
});

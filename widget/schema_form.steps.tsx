import { act, fireEvent, screen, within } from "@testing-library/react";
import { register } from "@sustenaut/pubtest";
import * as quickpickle from "quickpickle";
import { After, Given, When } from "quickpickle";
import widget, { messages, type Model } from "./schema_form";

// Steps for widget/features/schema-form.feature: SchemaFormWidget's front end in jsdom, on pubtest's steps.
register(quickpickle, { runner: "quickpickle" });

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

type Drawn = ReturnType<typeof fakeModel> & { el?: HTMLElement; drawn: (() => void)[] };
type World = { widget: Drawn; attempt: (action: () => unknown) => Promise<unknown> };

const schema = {
  type: "object",
  required: ["site"],
  properties: { site: { type: "string", title: "Site", minLength: 2 } },
};
const uischema = { type: "VerticalLayout", elements: [{ type: "Control", scope: "#/properties/site" }] };
const settle = () => act(() => new Promise((resolve) => setTimeout(resolve, 30)));

/** What the widget shows: the Site field's value, what it last saved, and the listeners it keeps on the model. */
function shown({ saved, listeners, el }: Drawn) {
  const field = el?.isConnected ? (within(el).getByLabelText("Site") as HTMLInputElement) : undefined;
  return {
    field: field?.value,
    saved: saved.at(-1),
    listeners: [...listeners.values()].reduce((n, l) => n + l.size, 0),
  };
}

function draw(drawn: Drawn) {
  const el = document.createElement("div");
  document.body.append(el);
  let cleanup: () => void = () => {};
  act(() => {
    cleanup = widget.render({ model: drawn.model, el });
  });
  drawn.el = el;
  drawn.drawn.push(() => {
    act(() => cleanup());
    el.remove();
  });
}

// Each scenario takes down what it drew, so the next one draws into an empty document.
After(async (world) => {
  for (const takeDown of (world as unknown as World).widget?.drawn.splice(0) ?? []) takeDown();
});

Given("a model of the site form whose value is {string}", (world: World, value: string) => {
  world.widget = { ...fakeModel({ schema, uischema, value: JSON.parse(value), errors: [] }), drawn: [] };
});

Given("a model of the site form with no value", (world: World) => {
  world.widget = { ...fakeModel({ schema, uischema }), drawn: [] };
});

When("the widget is drawn", (world: World) =>
  world.attempt(async () => {
    draw(world.widget);
    await settle();
    return shown(world.widget);
  }),
);

When("the widget is drawn twice", (world: World) =>
  world.attempt(async () => {
    draw(world.widget);
    draw(world.widget);
    await settle();
    return shown(world.widget);
  }),
);

When("its first style is read", (world: World) =>
  world.attempt(() => world.widget.el?.querySelector("style")?.textContent),
);

When("{string} is typed into the field", (world: World, text: string) =>
  world.attempt(async () => {
    fireEvent.change(screen.getByLabelText("Site"), { target: { value: text } });
    await settle();
    return shown(world.widget);
  }),
);

When("Python changes the value to {string}", (world: World, value: string) =>
  world.attempt(async () => {
    world.widget.model.set("value", JSON.parse(value));
    act(() => world.widget.emit("change:value"));
    await settle();
    return shown(world.widget);
  }),
);

When("the widget is taken down", (world: World) =>
  world.attempt(() => {
    for (const takeDown of world.widget.drawn.splice(0)) takeDown();
    return shown(world.widget);
  }),
);

When("the registered properties are read", (world: World) =>
  world.attempt(() =>
    [...document.querySelectorAll("#sustenaut-schema-form-properties")].map((style) => style.textContent),
  ),
);

When("the first registered property style is read", (world: World) =>
  world.attempt(() => document.querySelector("#sustenaut-schema-form-properties")?.textContent),
);

When("no errors are turned into messages", (world: World) => world.attempt(() => messages(undefined)));

When("the errors {string} are turned into messages", (world: World, errors: string) =>
  world.attempt(() => messages(JSON.parse(errors))),
);

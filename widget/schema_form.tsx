// SchemaFormWidget's front end, an anywidget module: @sustenaut/ui's SchemaForm drawn from the model's
// `schema` and `uischema`. The form's data goes back to Python as `value`, its validation messages as `errors`.
import { SchemaForm } from "@sustenaut/ui/jsonforms";
import { createRoot } from "react-dom/client";
import css from "./schema_form.css?inline";

/** The part of anywidget's model this widget uses. */
export type Model = {
  get(name: string): unknown;
  set(name: string, value: unknown): void;
  save_changes(): void;
  on(event: string, callback: () => void): void;
  off(event: string, callback: () => void): void;
};

type JsonFormsError = { instancePath?: string; message?: string };

/** What the form reports: a JSON Pointer to the value and the message. */
export function messages(errors: JsonFormsError[] | undefined): { path: string; message: string }[] {
  return (errors ?? []).map((e) => ({ path: e.instancePath ?? "", message: e.message ?? "" }));
}

/** Tailwind registers its variables with @property, which a shadow root ignores; registered in the document,
 *  they hold inside the widget's shadow root too. */
function registerProperties() {
  if (document.getElementById("sustenaut-schema-form-properties")) return;
  const style = document.createElement("style");
  style.id = "sustenaut-schema-form-properties";
  style.textContent = (css.match(/@property[^{]*\{[^}]*\}/g) ?? []).join("\n");
  document.head.append(style);
}

function render({ model, el }: { model: Model; el: HTMLElement }) {
  const style = document.createElement("style");
  style.textContent = css;
  el.append(style);
  registerProperties();
  const mount = document.createElement("div");
  mount.className = "font-sans text-ink";
  el.append(mount);
  const root = createRoot(mount);
  const draw = () =>
    root.render(
      <SchemaForm
        schema={model.get("schema") as object}
        uischema={model.get("uischema") as never}
        data={model.get("value") ?? {}}
        onChange={({ data, errors }) => {
          model.set("value", data ?? {});
          model.set("errors", messages(errors));
          model.save_changes();
        }}
      />,
    );
  draw();
  const events = ["change:schema", "change:uischema", "change:value"];
  for (const e of events) model.on(e, draw);
  return () => {
    for (const e of events) model.off(e, draw);
    root.unmount();
  };
}

export default { render };

"""SchemaFormWidget: a form drawn with @sustenaut/ui's SchemaForm, for marimo through anywidget.

The front end is widget/schema_form.tsx, built into static/schema_form.js by `make widget` (`npm run build`).
The widget's `value` is the form's data; `errors` are JSON Forms' validation messages, as
`{"path", "message"}`.
"""

from __future__ import annotations

from pathlib import Path

import anywidget
import traitlets

STATIC = Path(__file__).resolve().parent / "static"
BUNDLE = STATIC / "schema_form.js"


class SchemaFormWidget(anywidget.AnyWidget):
    _esm = BUNDLE

    schema = traitlets.Dict().tag(sync=True)
    uischema = traitlets.Dict().tag(sync=True)
    value = traitlets.Dict().tag(sync=True)
    errors = traitlets.List().tag(sync=True)

    def __init__(self, **kwargs):
        if not BUNDLE.exists():
            raise FileNotFoundError(f"{BUNDLE} is not built: run `make widget`")
        super().__init__(**kwargs)

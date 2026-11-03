"""Forms a notebook asks its reader to fill in.

A form is `<name>.form.json` beside the notebook: `{"schema": <JSON Schema>, "uischema": <JSON Forms UI schema>}`.
The widget draws it with @sustenaut/ui's SchemaForm; Python checks the values against the same schema with
jsonschema (draft 7, as JSON Forms' ajv), so a value the notebook uses has passed the form's rules.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator

ROOT = Path(__file__).resolve().parent.parent
FORMS = ROOT / "notebooks"


@dataclass(frozen=True)
class FormError:
    """One rule a value breaks: a JSON Pointer to it ("" for the whole form) and the message."""

    path: str
    message: str


@dataclass(frozen=True)
class Form:
    name: str
    schema: dict[str, Any]
    uischema: dict[str, Any]

    def errors(self, values: Mapping[str, Any]) -> list[FormError]:
        """What is wrong with `values`, by path; empty when they pass every rule."""
        validator = Draft7Validator(self.schema, format_checker=Draft7Validator.FORMAT_CHECKER)
        found = sorted(validator.iter_errors(dict(values)), key=lambda e: list(map(str, e.absolute_path)))
        return [FormError("".join(f"/{part}" for part in e.absolute_path), e.message) for e in found]

    def is_valid(self, values: Mapping[str, Any]) -> bool:
        return not self.errors(values)

    def widget(self, value: Mapping[str, Any] | None = None):
        """The form as a SchemaFormWidget, starting from `value`."""
        from .widget import SchemaFormWidget

        return SchemaFormWidget(schema=self.schema, uischema=self.uischema, value=dict(value or {}))


def load_form(name: str, directory: Path = FORMS) -> Form:
    """Read `<directory>/<name>.form.json`, refusing a schema that is not valid JSON Schema."""
    document = json.loads((directory / f"{name}.form.json").read_text())
    schema, uischema = document["schema"], document["uischema"]
    Draft7Validator.check_schema(schema)
    return Form(name, schema, uischema)

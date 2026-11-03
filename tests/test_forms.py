import json

import pytest
from jsonschema.exceptions import SchemaError

from notebooks_lib.forms import FORMS, Form, FormError, load_form
from notebooks_lib.widget import BUNDLE, SchemaFormWidget


@pytest.fixture
def form():
    return load_form("site_costs")


def test_a_form_loads_its_schema_and_ui_schema(form):
    assert form.name == "site_costs"
    assert form.schema["required"] == ["period", "projects"]
    assert form.uischema["type"] == "Group"


def test_valid_values_pass(form):
    values = {"period": {"start": "2026-03-01", "end": "2026-03-31"}, "projects": ["visit_ee"]}
    assert form.errors(values) == []
    assert form.is_valid(values)


def test_errors_name_the_value_by_its_path(form):
    errors = form.errors({"projects": ["riga"], "period": {"start": "not a date"}})
    assert [e.path for e in errors] == ["/period", "/period/start", "/projects/0"]
    assert all(isinstance(e, FormError) and e.message for e in errors)
    assert "'end' is a required property" in errors[0].message
    assert not form.is_valid({})
    assert [e.path for e in form.errors({})] == ["", ""]


def test_the_model_form_accepts_the_data_files():
    from notebooks_lib.costs import model_defaults

    model = load_form("site_costs.model")
    assert model.uischema["type"] == "Categorization"
    assert model.errors(model_defaults()) == []
    bad = model_defaults() | {"load_now": 200, "multipliers": {"pub": 0}}
    assert {e.path for e in model.errors(bad)} == {"/load_now", "/multipliers/pub"}


def test_a_schema_that_is_not_json_schema_is_refused(tmp_path):
    (tmp_path / "bad.form.json").write_text(json.dumps({"schema": {"type": 5}, "uischema": {}}))
    with pytest.raises(SchemaError):
        load_form("bad", tmp_path)


def test_a_missing_form_is_an_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_form("nothing", tmp_path)


def test_a_form_becomes_a_widget_whose_value_is_its_data(form):
    widget = form.widget({"projects": ["visit_ee"]})
    assert isinstance(widget, SchemaFormWidget)
    assert (widget.schema, widget.uischema, widget.value, widget.errors) == (
        form.schema,
        form.uischema,
        {"projects": ["visit_ee"]},
        [],
    )
    assert Form("x", {}, {}).widget().value == {}


def test_the_widget_needs_its_built_bundle(monkeypatch, tmp_path):
    assert BUNDLE.exists(), "run `make widget` first"
    monkeypatch.setattr("notebooks_lib.widget.BUNDLE", tmp_path / "missing.js")
    with pytest.raises(FileNotFoundError, match="make widget"):
        SchemaFormWidget()


@pytest.mark.parametrize("path", sorted(FORMS.glob("*.form.json")), ids=lambda p: p.name)
def test_every_form_is_valid_json_schema_with_a_ui_schema(path):
    form = load_form(path.name.removesuffix(".form.json"))
    assert form.uischema["type"] in {"VerticalLayout", "HorizontalLayout", "Group", "Categorization"}

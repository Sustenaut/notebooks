import json

from pytest_bdd import given, parsers, scenarios, when

from notebooks_lib.costs import model_defaults
from notebooks_lib.forms import FORMS, Form, load_form
from notebooks_lib.widget import SchemaFormWidget

scenarios("forms.feature")

LAYOUTS = {"VerticalLayout", "HorizontalLayout", "Group", "Categorization"}


def checked(form, values):
    errors = form.errors(values)
    return {
        "errors": [{"path": e.path, "message": e.message} for e in errors],
        "paths": [e.path for e in errors],
        "kinds": sorted({type(e).__name__ for e in errors}),
        "valid": form.is_valid(values),
    }


@given("the values are the cost model's defaults")
def defaults(ctx):
    ctx.values = model_defaults()


@given(parsers.parse('the values are the cost model\'s defaults, but for "{changes}"'))
def defaults_but(ctx, changes):
    ctx.values = model_defaults() | json.loads(changes)


@given(parsers.parse('the form "{name}" whose schema is "{schema}" and ui schema is "{uischema}"'))
def a_form(ctx, name, schema, uischema):
    ctx.form = Form(name, json.loads(schema), json.loads(uischema))


@given(parsers.parse('the widget\'s bundle is "{name}" in the scratch directory'))
def bundle_at(ctx, monkeypatch, name):
    monkeypatch.setattr("notebooks_lib.widget.BUNDLE", ctx.directory / name)


@when(parsers.parse('the form "{name}" is loaded'))
def form_loaded(ctx, name):
    ctx.attempt(lambda: load_form(name))


@when(parsers.parse('the form "{name}" is loaded from the scratch directory'))
def form_loaded_from(ctx, name):
    ctx.attempt(lambda: load_form(name, ctx.directory))


@when(parsers.parse('the form "{name}" checks the values "{values}"'))
def form_checks_given(ctx, name, values):
    ctx.attempt(lambda: checked(load_form(name), json.loads(values)))


@when(parsers.parse('the form "{name}" checks the values'))
def form_checks(ctx, name):
    ctx.attempt(lambda: checked(load_form(name), ctx.values))


@when(parsers.parse('the form becomes a widget starting from "{values}"'))
def becomes_widget_from(ctx, values):
    ctx.attempt(lambda: ctx.form.widget(json.loads(values)))


@when("the form becomes a widget")
def becomes_widget(ctx):
    ctx.attempt(lambda: ctx.form.widget())


@when("the widget is made")
def widget_made(ctx):
    ctx.attempt(SchemaFormWidget)


@when("every form is loaded")
def every_form(ctx):
    def load():
        forms = [load_form(path.name.removesuffix(".form.json")) for path in sorted(FORMS.glob("*.form.json"))]
        return {"not laid out": [form.name for form in forms if form.uischema["type"] not in LAYOUTS]}

    ctx.attempt(load)

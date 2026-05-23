import pathlib

from django import template
from django.template import engines
from django.template.loader import render_to_string

register = template.Library()


@register.filter
def getfield(form, key):
    """Return the BoundField for `key`, or empty string if absent."""
    if not form or key not in form.fields:
        return ""
    return form[key]


@register.simple_tag(takes_context=True)
def theme_partial(context, spec=None):
    """Render `spec.partial` from the campaign's theme directory if present,
    else from the fallback partials directory.

    Both branches receive the same context (form/field/spec/theme/campaign).
    """
    if not spec:
        return ""
    partial_rel = spec["partial"]              # e.g. "partials/_text.html"
    theme = context.get("theme")
    if theme is not None:
        theme_path = pathlib.Path(theme.directory) / partial_rel
        if theme_path.is_file():
            tpl = engines["django"].from_string(
                theme_path.read_text(encoding="utf-8")
            )
            field = context["form"][spec["key"]] if spec["key"] in context["form"].fields else None
            return tpl.render({**context.flatten(), "field": field, "spec": spec})

    # Fallback: campaigns/templates/campaigns/_fallback_partials/<filename>
    fallback_name = "campaigns/_fallback_partials/" + partial_rel.rsplit("/", 1)[-1]
    field = context["form"][spec["key"]] if spec["key"] in context["form"].fields else None
    return render_to_string(fallback_name, {**context.flatten(),
                                            "field": field, "spec": spec})

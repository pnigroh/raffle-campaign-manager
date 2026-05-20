# Per-Campaign Templates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `Theme` model that owns a public form bundle (HTML + assets); each Campaign picks a theme; existing Futboleros design becomes the seeded default so nothing breaks at deploy time.

**Architecture:** A new `Theme` model stores name/slug/is_default. Theme files live on disk under `<settings.THEMES_ROOT>/<slug>/` — `<slug>.html` templates + `assets/` directory. Devs upload `.zip` bundles via Django admin (superuser only). Operators set `Campaign.theme` to pick a theme. At request time the view reads the theme's `submission_form.html` from disk and renders it via `engines["django"].from_string(...)`. Assets served from `/theme-assets/<slug>/...` — nginx in prod, Django's `serve` view in dev. The current Futboleros design is moved to `campaigns/themes/futboleros/` in-repo and copied to `<THEMES_ROOT>/futboleros/` by the migration.

**Tech Stack:** Django 4.2, Postgres (prod) / SQLite (dev), Unfold admin, pytest.

**Spec:** [`docs/superpowers/specs/2026-05-20-per-campaign-templates-design.md`](../specs/2026-05-20-per-campaign-templates-design.md)

---

## Pre-flight

- [ ] **Confirm clean working tree on main**

```bash
cd /home/elgran/Projects/raffle-campaign
git status                              # clean
git log -1 --oneline                    # expect d32a2bd (spec commit) or later
git checkout main && git pull
docker exec raffle-web python manage.py test campaigns -v 0
```
Expected: 115 tests pass on main (the 32 multi-domain tests are on PR #2 — not on main yet).

- [ ] **Confirm container image is fresh**

```bash
RAFFLE_CAMPAIGN_WEB_PORT=8500 docker compose up -d
docker exec raffle-web pip show dj-database-url | head -2   # confirm package present
```

- [ ] **Create the feature branch**

```bash
git checkout -b feat/per-campaign-templates
```

- [ ] **Decide branch base.** PR #2 (multi-domain) is open against main. This plan is independent of multi-domain — does not touch `Domain`, `Campaign.domain`, or any host-gate code. **If you want this branch to land BEFORE the multi-domain merge,** base on `main`. **If you want it to land AFTER**, rebase onto post-merge main when the time comes. Recommended: base on `main` now; resolve any tiny conflicts at integration time.

---

## Task 1: Theme model + helper function (no migration yet)

Adds the `Theme` Python class and the `_copy_default_theme_to_themes_root()` helper. No migration yet — that's Task 2. We're staging the model and helper code so the migration in Task 2 can reference them.

**Files:**
- Modify: `campaigns/models.py` (append `Theme` near the end, after `RaffleWinner`)
- Create: `campaigns/themes/__init__.py` (empty marker)
- Create: `campaigns/themes_setup.py` (helper function — NOT named `setup.py` because that would conflict with pip's setup.py convention if anyone ever pip-installs the app)
- Modify: `raffle_project/settings.py` (add `THEMES_ROOT`)
- Test: `campaigns/tests/test_themes.py` (new)

- [ ] **Step 1.1: Write the failing test for the Theme model**

`campaigns/tests/test_themes.py`:

```python
from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings

from campaigns.models import Theme


class ThemeModelTests(TestCase):
    def test_str_is_name(self):
        t = Theme.objects.create(name="Futboleros", slug="futboleros")
        self.assertEqual(str(t), "Futboleros")

    def test_directory_uses_themes_root(self):
        t = Theme.objects.create(name="X", slug="x")
        self.assertEqual(t.directory, Path(settings.THEMES_ROOT) / "x")

    def test_get_default_returns_only_default_row(self):
        Theme.objects.create(name="Plain", slug="plain", is_default=False)
        d = Theme.objects.create(name="Default", slug="default", is_default=True)
        self.assertEqual(Theme.get_default(), d)
```

- [ ] **Step 1.2: Run the test to verify it fails**

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_themes -v 2
```
Expected: `ImportError: cannot import name 'Theme' from 'campaigns.models'`.

- [ ] **Step 1.3: Add `THEMES_ROOT` to `raffle_project/settings.py`**

Insert near other `*_ROOT` settings (search for `MEDIA_ROOT`). The setting defaults to `BASE_DIR / "themes"` in dev; prod's `.env.prod` will set it to `/srv/raffle/themes`.

```python
THEMES_ROOT = os.environ.get(
    "THEMES_ROOT", str(BASE_DIR / "themes")
)
```

- [ ] **Step 1.4: Add the `Theme` model to `campaigns/models.py`**

Append to the end of the file (after `RaffleWinner`):

```python
class Theme(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    description = models.CharField(max_length=500, blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="themes_created",
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_default"],
                condition=models.Q(is_default=True),
                name="only_one_default_theme",
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def directory(self):
        from pathlib import Path
        from django.conf import settings as dj_settings
        return Path(dj_settings.THEMES_ROOT) / self.slug

    @classmethod
    def get_default(cls):
        return cls.objects.get(is_default=True)
```

- [ ] **Step 1.5: Create the empty `campaigns/themes/__init__.py`**

```bash
mkdir -p campaigns/themes
touch campaigns/themes/__init__.py
```

This marker turns `campaigns/themes/` into a Python package; Task 4 will populate it with the Futboleros bundle.

- [ ] **Step 1.6: Create the helper function `campaigns/themes_setup.py`**

```python
"""Copy the in-repo source theme into THEMES_ROOT.

Called from the data migration that creates the default Theme row, AND from
the `setup_default_theme` management command (operator recovery tool).
"""
import shutil
from pathlib import Path

from django.conf import settings


REPO_DEFAULT_THEME_DIR = Path(__file__).resolve().parent / "themes" / "futboleros"


def copy_default_theme_to_themes_root(force=False):
    """Copy ``campaigns/themes/futboleros/`` into ``<THEMES_ROOT>/futboleros/``.

    Idempotent by default. With ``force=True``, removes the destination first.
    Returns the destination Path. Raises if the source directory is missing.
    """
    src = REPO_DEFAULT_THEME_DIR
    if not src.is_dir():
        raise RuntimeError(
            f"Source default theme directory missing: {src}. "
            "Did Task 4 (repo restructure) run yet?"
        )
    dest = Path(settings.THEMES_ROOT) / "futboleros"
    if dest.exists():
        if not force:
            return dest
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest)
    return dest
```

- [ ] **Step 1.7: Re-run the tests**

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_themes -v 2
```

Expected: all 3 tests pass. (The `IntegrityError` test that needs the partial-unique constraint is in Task 2, not Task 1 — these three tests only exercise model fields, the `directory` property, and `get_default`.)

Also run the full suite to confirm no regression in pre-existing tests:

```bash
docker exec raffle-web python manage.py test campaigns -v 0
```

If you see `ModuleNotFoundError: themes` or similar from any pre-existing test trying to import `campaigns.themes` as a module (the package marker added in Step 1.5), fix the import — that package is empty by design at this point.

- [ ] **Step 1.8: Commit**

```bash
git add campaigns/models.py campaigns/themes/__init__.py campaigns/themes_setup.py campaigns/tests/test_themes.py raffle_project/settings.py
git commit -m "feat(themes): Theme model + helper to copy default theme to THEMES_ROOT"
```

---

## Task 2: Migration adds Theme + Campaign.theme FK + populates default directory

This is the migration that turns Task 1's Python code into a deployable schema change. It also calls the helper to populate `<THEMES_ROOT>/futboleros/` so the runtime view never sees a Theme row pointing at a missing directory.

But — **note the chicken-and-egg**: the helper reads from `campaigns/themes/futboleros/`. Task 4 is the task that puts files there. So this task's migration would fail today.

**Resolution:** in this task, the migration creates the Theme row but skips the directory copy via a try/except guarded on the source directory existing. Task 4 then adds the source files. Task 5 (re-runnable migration callback) adds a one-off data migration step that does the copy after Task 4 has shipped.

Cleanest sequencing: **this migration creates only the model and FK + the default Theme row**. The directory population happens via a SEPARATE data migration in Task 4 (after the files exist in repo).

**Files:**
- Create: `campaigns/migrations/0012_theme.py` (auto-generated then hand-extended)
- Create: `campaigns/migrations/0013_campaign_theme_fk.py` (auto-generated)
- Modify: `campaigns/models.py` (add `theme` FK to Campaign)
- Test: `campaigns/tests/test_themes.py` (append)

- [ ] **Step 2.1: Write the failing tests**

Append to `campaigns/tests/test_themes.py`:

```python
class ThemeConstraintsTests(TestCase):
    def test_only_one_default_allowed(self):
        from django.db import IntegrityError
        Theme.objects.create(name="A", slug="a", is_default=True)
        with self.assertRaises(IntegrityError):
            Theme.objects.create(name="B", slug="b", is_default=True)

    def test_default_theme_is_seeded_by_migration(self):
        # 0012 seeds the Futboleros row.
        self.assertTrue(
            Theme.objects.filter(slug="futboleros", is_default=True).exists()
        )


class CampaignThemeFKTests(TestCase):
    def test_campaign_theme_is_nullable(self):
        from campaigns.models import Campaign
        # Should succeed without specifying theme=
        c = Campaign.objects.create(
            name="C", slug="c", start_date="2026-06-01", end_date="2026-06-30"
        )
        self.assertIsNone(c.theme_id)

    def test_campaign_can_reference_theme(self):
        from campaigns.models import Campaign
        t = Theme.objects.create(name="X", slug="x")
        c = Campaign.objects.create(
            name="C", slug="c", start_date="2026-06-01", end_date="2026-06-30",
            theme=t,
        )
        self.assertEqual(c.theme, t)
```

If Task 1's third test was renamed `_skip_...`, rename it back to `test_get_default_returns_only_default_row` now.

- [ ] **Step 2.2: Verify it fails**

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_themes -v 2
```
Expected: tests fail because no migration exists yet.

- [ ] **Step 2.3: Add `Campaign.theme` field**

In `campaigns/models.py`, inside the `Campaign` class, add the field (place after the existing core fields, before timestamps):

```python
    theme = models.ForeignKey(
        "Theme",
        on_delete=models.PROTECT,
        related_name="campaigns",
        null=True,
        blank=True,
    )
```

(`"Theme"` as a string reference because Theme is defined later in the file.)

- [ ] **Step 2.4: Generate the migrations**

```bash
docker exec raffle-web python manage.py makemigrations campaigns --name theme
docker exec raffle-web python manage.py makemigrations campaigns --name campaign_theme_fk
```

Expected: creates `0012_theme.py` (Theme model + unique constraint) and `0013_campaign_theme_fk.py` (AddField on Campaign).

Inspect both — the auto-generated content should be clean. Verify:
- `0012_theme.py` operations include `CreateModel` AND `AddConstraint(UniqueConstraint(...))`.
- `0013_campaign_theme_fk.py` operations include `AddField('campaign', 'theme', ForeignKey(null=True, ...))`.

- [ ] **Step 2.5: Hand-edit `0012_theme.py` to seed the default Theme row**

Open the generated `0012_theme.py` and append a `RunPython` operation after `CreateModel`/`AddConstraint`:

```python
def seed_default_theme(apps, schema_editor):
    Theme = apps.get_model("campaigns", "Theme")
    Theme.objects.get_or_create(
        slug="futboleros",
        defaults={
            "name": "Futboleros (Mundial 2026)",
            "description": "Original Mundial 2026 design — La Nube que te mueve",
            "is_default": True,
        },
    )


def reverse_noop(apps, schema_editor):
    pass
```

And in the Migration class, add at the end of `operations`:

```python
        migrations.RunPython(seed_default_theme, reverse_noop),
```

Note: the directory population (`copy_default_theme_to_themes_root`) is NOT in this migration. It happens in Task 4 after the source files exist on disk.

- [ ] **Step 2.6: Apply migrations + run tests**

```bash
docker exec raffle-web python manage.py migrate campaigns
docker exec raffle-web python manage.py test campaigns.tests.test_themes -v 2
docker exec raffle-web python manage.py test campaigns -v 0
```
Expected: all theme tests pass; full suite green (115 baseline + new theme tests ≈ 120-ish).

- [ ] **Step 2.7: Commit**

```bash
git add campaigns/models.py campaigns/migrations/0012_theme.py campaigns/migrations/0013_campaign_theme_fk.py campaigns/tests/test_themes.py
git commit -m "feat(themes): Theme model migration + Campaign.theme FK + seed Futboleros row"
```

---

## Task 3: `theme_static` template tag

A small `{% theme_static "logo.svg" %}` tag that resolves to `/theme-assets/<slug>/logo.svg`. Needed by Task 4 (rewriting Futboleros template paths) so it ships first.

**Files:**
- Create: `campaigns/templatetags/__init__.py` (empty marker)
- Create: `campaigns/templatetags/theme_tags.py`
- Test: `campaigns/tests/test_themes.py` (append)

- [ ] **Step 3.1: Write the failing test**

Append to `campaigns/tests/test_themes.py`:

```python
from django.template import Context, Template


class ThemeStaticTagTests(TestCase):
    def test_returns_theme_assets_url_with_slug(self):
        theme = Theme.objects.create(name="X", slug="my-theme")
        tpl = Template("{% load theme_tags %}{% theme_static 'logo.svg' %}")
        rendered = tpl.render(Context({"theme": theme}))
        self.assertEqual(rendered, "/theme-assets/my-theme/logo.svg")

    def test_falls_back_to_default_when_theme_not_in_context(self):
        # Default theme was seeded by migration 0012 — slug=futboleros.
        tpl = Template("{% load theme_tags %}{% theme_static 'logo.svg' %}")
        rendered = tpl.render(Context({}))
        self.assertEqual(rendered, "/theme-assets/futboleros/logo.svg")

    def test_handles_nested_path(self):
        theme = Theme.objects.create(name="X", slug="x")
        tpl = Template("{% load theme_tags %}{% theme_static 'fonts/foo.woff2' %}")
        rendered = tpl.render(Context({"theme": theme}))
        self.assertEqual(rendered, "/theme-assets/x/fonts/foo.woff2")
```

- [ ] **Step 3.2: Verify fail**

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_themes.ThemeStaticTagTests -v 2
```
Expected: `TemplateSyntaxError: 'theme_tags' is not a registered tag library`.

- [ ] **Step 3.3: Create the template tag module**

```bash
mkdir -p campaigns/templatetags
touch campaigns/templatetags/__init__.py
```

`campaigns/templatetags/theme_tags.py`:

```python
from django import template

from campaigns.models import Theme

register = template.Library()


@register.simple_tag(takes_context=True)
def theme_static(context, path):
    """Resolve to /theme-assets/<theme.slug>/<path>.

    Looks up ``theme`` in the rendering context; if missing, falls back to
    the default Theme (the row with ``is_default=True``). The default lookup
    happens at most once per render — calling code with many tag invocations
    on the same render still hits the DB once because Django's template
    context caches the variable resolution.
    """
    theme = context.get("theme") or Theme.get_default()
    return f"/theme-assets/{theme.slug}/{path}"
```

- [ ] **Step 3.4: Run tests**

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_themes.ThemeStaticTagTests -v 2
```
Expected: 3 tests pass.

- [ ] **Step 3.5: Commit**

```bash
git add campaigns/templatetags/__init__.py campaigns/templatetags/theme_tags.py campaigns/tests/test_themes.py
git commit -m "feat(themes): theme_static template tag"
```

---

## Task 4: Repo restructure — COPY Futboleros files to themes/futboleros/ + rewrite asset paths

Move the in-repo source of the Futboleros theme into the bundle layout the spec defines. Runtime is unaffected by this task — the OLD `templates/campaigns/submission_form.html` and `submission_success.html` files stay in place; views still reference them. Task 9 is the go-live moment that deletes the old files and switches the views.

This task also adds a SECOND data migration to call the helper from Task 1 so `<THEMES_ROOT>/futboleros/` is populated on every `migrate` run.

**Files:**
- Create: `campaigns/themes/futboleros/submission_form.html` (copy of `campaigns/templates/campaigns/submission_form.html` with rewritten paths)
- Create: `campaigns/themes/futboleros/submission_success.html` (copy + rewritten paths)
- Create: `campaigns/themes/futboleros/assets/...` (subset of `campaigns/static/campaigns/landing/*` + `campaigns/static/campaigns/fonts/Andreas.ttf` — keep the originals where they are; they'll be deleted in Task 9)
- Create: `campaigns/migrations/0014_populate_default_theme_directory.py`
- Test: `campaigns/tests/test_themes.py` (append)

- [ ] **Step 4.1: Inventory existing assets used by the Futboleros templates**

```bash
grep -oE "{% static '[^']+' %}" campaigns/templates/campaigns/submission_form.html campaigns/templates/campaigns/submission_success.html | sort -u
```
Capture the list — every `{% static 'campaigns/...' %}` reference is an asset to copy.

- [ ] **Step 4.2: Copy template files and rewrite paths**

```bash
# Create the bundle directory layout
mkdir -p campaigns/themes/futboleros/assets/landing
mkdir -p campaigns/themes/futboleros/assets/fonts

# Copy templates (preserve originals)
cp campaigns/templates/campaigns/submission_form.html campaigns/themes/futboleros/submission_form.html
cp campaigns/templates/campaigns/submission_success.html campaigns/themes/futboleros/submission_success.html

# Copy assets
cp campaigns/static/campaigns/landing/*.png campaigns/themes/futboleros/assets/landing/
cp campaigns/static/campaigns/fonts/Andreas.ttf campaigns/themes/futboleros/assets/fonts/
```

(Use the exact asset list from Step 4.1 — adjust the wildcards if your inventory shows other files.)

- [ ] **Step 4.3: Rewrite asset paths inside the copies**

Edit `campaigns/themes/futboleros/submission_form.html`:

1. Replace `{% load static %}` at the top with `{% load theme_tags %}` (or add the load if static is needed elsewhere — usually it isn't in a self-contained theme template).
2. Replace every `{% static 'campaigns/landing/<filename>' %}` with `{% theme_static 'landing/<filename>' %}`.
3. Replace every `{% static 'campaigns/fonts/<filename>' %}` with `{% theme_static 'fonts/<filename>' %}`.

Use sed for the bulk substitution:

```bash
sed -i \
  -e "s|{% load static %}|{% load theme_tags %}|g" \
  -e "s|{% static 'campaigns/landing/\([^']*\)' %}|{% theme_static 'landing/\1' %}|g" \
  -e "s|{% static 'campaigns/fonts/\([^']*\)' %}|{% theme_static 'fonts/\1' %}|g" \
  campaigns/themes/futboleros/submission_form.html \
  campaigns/themes/futboleros/submission_success.html
```

After sed: run `grep -n "{% static" campaigns/themes/futboleros/*.html` — should return empty. Any remaining `{% static %}` calls are non-theme references and need a judgment call (most likely they're for `{% url %}` or CSRF, which are NOT `{% static %}` — so empty grep is expected).

- [ ] **Step 4.4: Verify the in-repo source compiles**

Quickly check that the rewritten templates parse:

```bash
docker exec raffle-web python manage.py shell -c "
from django.template import Template
from pathlib import Path
src = Path('/app/campaigns/themes/futboleros/submission_form.html').read_text()
t = Template(src)
print('submission_form.html parses OK')
src2 = Path('/app/campaigns/themes/futboleros/submission_success.html').read_text()
t2 = Template(src2)
print('submission_success.html parses OK')
"
```

Expected: both "parses OK" lines. If you see `TemplateSyntaxError`, fix the offending line.

- [ ] **Step 4.5: Generate the directory-population migration**

```bash
docker exec raffle-web python manage.py makemigrations campaigns --empty --name populate_default_theme_directory
```

Edit the generated `0014_populate_default_theme_directory.py`:

```python
from django.db import migrations


def populate(apps, schema_editor):
    # Lazy import — at migration time `campaigns.themes_setup` is importable.
    from campaigns.themes_setup import copy_default_theme_to_themes_root
    try:
        copy_default_theme_to_themes_root()
    except RuntimeError:
        # Source directory missing — happens only in extreme test isolation
        # where the source files weren't checked out. Don't fail migration;
        # tests that need the directory will set it up themselves.
        pass


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("campaigns", "0013_campaign_theme_fk"),
    ]
    operations = [migrations.RunPython(populate, reverse_noop)]
```

- [ ] **Step 4.6: Add the directory-population test**

Append to `campaigns/tests/test_themes.py`:

```python
class DefaultThemeDirectoryTests(TestCase):
    def test_default_theme_directory_is_populated_after_migrate(self):
        from django.conf import settings
        default = Theme.get_default()
        directory = Path(settings.THEMES_ROOT) / default.slug
        self.assertTrue(directory.is_dir(), f"{directory} missing")
        self.assertTrue((directory / "submission_form.html").is_file())
        self.assertTrue((directory / "submission_success.html").is_file())
```

- [ ] **Step 4.7: Apply migration + run tests**

```bash
docker exec raffle-web python manage.py migrate campaigns
docker exec raffle-web python manage.py test campaigns.tests.test_themes -v 2
```
Expected: all theme tests pass, including `test_default_theme_directory_is_populated_after_migrate`.

- [ ] **Step 4.8: Commit**

```bash
git add campaigns/themes/futboleros/ campaigns/migrations/0014_populate_default_theme_directory.py campaigns/tests/test_themes.py
git commit -m "feat(themes): copy Futboleros bundle to themes/futboleros/ + populate THEMES_ROOT in migration"
```

---

## Task 5: Theme.save() override + post-delete signal

Two invariants to enforce:

1. **At most one default theme.** The `UniqueConstraint` enforces this at the DB level, but raising an `IntegrityError` from the admin gives the user a cryptic message. Better: override `save()` so setting `is_default=True` automatically demotes any other default.
2. **Deleting a Theme cleans up its directory.** `Campaign.theme` uses `on_delete=PROTECT`, so themes with campaigns can't be deleted. But unreferenced themes CAN be deleted, and the directory on disk should go with them.

**Files:**
- Modify: `campaigns/models.py` (extend `Theme` with `save` override; add post-delete signal handler in the same file)
- Test: `campaigns/tests/test_themes.py` (append)

- [ ] **Step 5.1: Write the failing tests**

Append:

```python
import os
import tempfile

from django.db.models.signals import post_delete


class ThemeDefaultDemotionTests(TestCase):
    def test_setting_a_new_default_demotes_the_previous_one(self):
        old = Theme.get_default()  # Futboleros, seeded
        new = Theme.objects.create(name="New", slug="new", is_default=True)
        old.refresh_from_db()
        self.assertFalse(old.is_default)
        self.assertTrue(new.is_default)

    def test_unsetting_is_default_is_fine(self):
        t = Theme.objects.create(name="T", slug="t", is_default=False)
        # No assertion — just shouldn't raise.
        t.save()


class ThemeDeleteSignalTests(TestCase):
    def test_deleting_unreferenced_theme_removes_directory(self):
        # Use a temp THEMES_ROOT so we don't touch the real default theme dir.
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(THEMES_ROOT=tmp):
                t = Theme.objects.create(name="X", slug="x-delete-test")
                t.directory.mkdir(parents=True)
                (t.directory / "submission_form.html").write_text("hi")
                self.assertTrue(t.directory.is_dir())
                t.delete()
                self.assertFalse(
                    Path(tmp, "x-delete-test").is_dir(),
                    "directory should have been removed",
                )

    def test_deleting_theme_with_campaigns_is_blocked(self):
        from django.db.models import ProtectedError
        from campaigns.models import Campaign
        t = Theme.objects.create(name="X", slug="x-protected")
        Campaign.objects.create(
            name="C", slug="c-protected",
            start_date="2026-06-01", end_date="2026-06-30",
            theme=t,
        )
        with self.assertRaises(ProtectedError):
            t.delete()
```

- [ ] **Step 5.2: Verify fail**

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_themes.ThemeDefaultDemotionTests campaigns.tests.test_themes.ThemeDeleteSignalTests -v 2
```
Expected: `test_setting_a_new_default_demotes_the_previous_one` fails with `IntegrityError`; `test_deleting_unreferenced_theme_removes_directory` fails because no signal handler.

- [ ] **Step 5.3: Add `save` override + signal handler to `Theme`**

In `campaigns/models.py`, replace the existing `Theme` class definition's body (keep the fields and Meta the same) — add at the bottom of the class:

```python
    def save(self, *args, **kwargs):
        if self.is_default:
            Theme.objects.filter(is_default=True).exclude(pk=self.pk).update(
                is_default=False
            )
        super().save(*args, **kwargs)
```

Then, AT THE END of `campaigns/models.py` (after the `Theme` class), add the signal handler:

```python
import shutil  # if not already imported at top

from django.db.models.signals import post_delete
from django.dispatch import receiver


@receiver(post_delete, sender=Theme)
def _remove_theme_directory(sender, instance, **kwargs):
    """When a Theme row is deleted, remove its on-disk directory.

    Protected by Campaign.theme's on_delete=PROTECT: deletion only fires
    when no Campaign references the theme.
    """
    if instance.directory.exists():
        shutil.rmtree(instance.directory)
```

Move the `import shutil` to the top of the file with the other imports.

- [ ] **Step 5.4: Run tests**

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_themes -v 2
```
Expected: all 4 new tests pass; existing tests still green.

- [ ] **Step 5.5: Commit**

```bash
git add campaigns/models.py campaigns/tests/test_themes.py
git commit -m "feat(themes): demote-other-default save() + post-delete signal removes directory"
```

---

## Task 6: Asset URL routing (dev only)

In production, nginx serves `/theme-assets/<slug>/<path>` directly. In dev, Django serves them via the `serve` view. Wire the URL route.

**Files:**
- Modify: `raffle_project/urls.py`
- Test: `campaigns/tests/test_themes.py` (append)

- [ ] **Step 6.1: Write the failing test**

Append:

```python
from django.test import Client


class ThemeAssetServingTests(TestCase):
    def test_dev_serves_existing_asset(self):
        # The seeded Futboleros theme has assets/fonts/Andreas.ttf
        # (created by Task 4).
        c = Client()
        r = c.get("/theme-assets/futboleros/fonts/Andreas.ttf")
        self.assertEqual(r.status_code, 200)
        self.assertGreater(int(r["Content-Length"]), 1000)  # font is ~50KB

    def test_dev_404s_missing_asset(self):
        c = Client()
        r = c.get("/theme-assets/futboleros/nope.png")
        self.assertEqual(r.status_code, 404)

    def test_dev_404s_unknown_theme(self):
        c = Client()
        r = c.get("/theme-assets/does-not-exist/logo.svg")
        self.assertEqual(r.status_code, 404)
```

- [ ] **Step 6.2: Verify fail**

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_themes.ThemeAssetServingTests -v 2
```
Expected: 404 on the first test because no URL route.

- [ ] **Step 6.3: Add the URL route to `raffle_project/urls.py`**

Open `raffle_project/urls.py`. Inside the `urlpatterns` list, ONLY if `settings.DEBUG` (or always — Django's `serve` view is safe but bypassed in prod by nginx anyway), add:

```python
from django.conf import settings
from django.views.static import serve as static_serve


def _theme_asset_view(request, slug, path):
    """Dev-only theme asset serving. In prod, nginx serves these directly."""
    asset_root = Path(settings.THEMES_ROOT) / slug / "assets"
    if not asset_root.is_dir():
        from django.http import Http404
        raise Http404
    return static_serve(request, path, document_root=str(asset_root))


urlpatterns += [
    path("theme-assets/<slug:slug>/<path:path>", _theme_asset_view, name="theme_asset"),
]
```

Add `from pathlib import Path` at the top of `raffle_project/urls.py` if not already imported.

(The route is registered unconditionally — `static_serve` is fine on both dev and prod, but in prod nginx short-circuits the request before Django sees it.)

- [ ] **Step 6.4: Run tests**

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_themes.ThemeAssetServingTests -v 2
```
Expected: 3 tests pass.

- [ ] **Step 6.5: Commit**

```bash
git add raffle_project/urls.py campaigns/tests/test_themes.py
git commit -m "feat(themes): /theme-assets/<slug>/<path> URL route"
```

---

## Task 7: ThemeAdmin + .zip upload + validation

The admin form a developer uses to upload a new theme bundle. Form validation enforces the rules in spec §4.3.

**Files:**
- Create: `campaigns/forms.py` (if it doesn't exist; otherwise modify) — add `ThemeUploadForm`
- Modify: `campaigns/admin.py` (add `ThemeAdmin`)
- Create: `campaigns/themes_upload.py` (extraction + validation logic, keeps admin.py clean)
- Test: `campaigns/tests/test_themes.py` (append)

- [ ] **Step 7.1: Write the failing tests**

Append:

```python
import io
import zipfile

from django.core.files.uploadedfile import SimpleUploadedFile


def _build_zip(files):
    """Build a small in-memory zip. ``files`` is dict[name -> bytes]."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    buf.seek(0)
    return SimpleUploadedFile("bundle.zip", buf.read(), content_type="application/zip")


class ThemeBundleValidationTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self._override = override_settings(THEMES_ROOT=self.tmp)
        self._override.enable()
        self.addCleanup(self._override.disable)

    def test_valid_bundle_extracts_to_theme_directory(self):
        from campaigns.themes_upload import extract_bundle
        bundle = _build_zip({
            "submission_form.html": b"<html>{{ campaign.name }}</html>",
            "submission_success.html": b"<html>ok</html>",
            "assets/logo.svg": b"<svg/>",
        })
        theme = Theme.objects.create(name="T1", slug="t1")
        extract_bundle(bundle, theme)
        self.assertTrue((theme.directory / "submission_form.html").is_file())
        self.assertTrue((theme.directory / "submission_success.html").is_file())
        self.assertTrue((theme.directory / "assets" / "logo.svg").is_file())

    def test_bundle_missing_required_file_rejected(self):
        from django.core.exceptions import ValidationError
        from campaigns.themes_upload import validate_bundle
        bundle = _build_zip({
            "submission_form.html": b"<html/>",
            # NO submission_success.html
        })
        with self.assertRaises(ValidationError) as cm:
            validate_bundle(bundle)
        self.assertIn("submission_success.html", str(cm.exception))

    def test_zip_slip_rejected(self):
        from django.core.exceptions import ValidationError
        from campaigns.themes_upload import validate_bundle
        bundle = _build_zip({
            "submission_form.html": b"<html/>",
            "submission_success.html": b"<html/>",
            "../../../etc/passwd": b"haxx",
        })
        with self.assertRaises(ValidationError):
            validate_bundle(bundle)

    def test_disallowed_extension_rejected(self):
        from django.core.exceptions import ValidationError
        from campaigns.themes_upload import validate_bundle
        bundle = _build_zip({
            "submission_form.html": b"<html/>",
            "submission_success.html": b"<html/>",
            "assets/evil.sh": b"#!/bin/sh\nrm -rf /",
        })
        with self.assertRaises(ValidationError) as cm:
            validate_bundle(bundle)
        self.assertIn("evil.sh", str(cm.exception))

    def test_reupload_replaces_directory_atomically(self):
        from campaigns.themes_upload import extract_bundle
        theme = Theme.objects.create(name="T2", slug="t2")
        first = _build_zip({
            "submission_form.html": b"first version",
            "submission_success.html": b"<html/>",
        })
        extract_bundle(first, theme)
        self.assertEqual(
            (theme.directory / "submission_form.html").read_bytes(),
            b"first version",
        )
        second = _build_zip({
            "submission_form.html": b"SECOND version",
            "submission_success.html": b"<html/>",
        })
        extract_bundle(second, theme)
        self.assertEqual(
            (theme.directory / "submission_form.html").read_bytes(),
            b"SECOND version",
        )
```

- [ ] **Step 7.2: Verify fail**

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_themes.ThemeBundleValidationTests -v 2
```
Expected: `ModuleNotFoundError: No module named 'campaigns.themes_upload'`.

- [ ] **Step 7.3: Create `campaigns/themes_upload.py`**

```python
"""Validation + extraction of theme bundle .zip uploads.

Public API:
- ``validate_bundle(uploaded_file)`` — raises ``ValidationError`` on any issue.
- ``extract_bundle(uploaded_file, theme)`` — validates, then atomically
  populates ``theme.directory``.
"""
import os
import shutil
import zipfile
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError


REQUIRED_FILES = ("submission_form.html", "submission_success.html")
ALLOWED_ASSET_EXTENSIONS = {
    ".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif",
    ".css", ".woff", ".woff2", ".ttf", ".otf", ".ico",
}
MAX_UNCOMPRESSED_SIZE = 10 * 1024 * 1024  # 10 MB


def _is_safe_path(name):
    """Reject path traversal, absolute paths, and zip-slip."""
    if name.startswith("/") or name.startswith("\\"):
        return False
    parts = Path(name).parts
    if ".." in parts:
        return False
    if any(p.startswith("..") for p in parts):
        return False
    return True


def validate_bundle(uploaded_file):
    """Validate a .zip upload. Raises ValidationError on any issue."""
    try:
        zf = zipfile.ZipFile(uploaded_file)
    except zipfile.BadZipFile as e:
        raise ValidationError(f"Not a valid .zip file: {e}")

    names = zf.namelist()

    # Required files at the root.
    for required in REQUIRED_FILES:
        if required not in names:
            raise ValidationError(
                f"Bundle is missing required file: {required}"
            )

    # Path safety + total uncompressed size.
    total = 0
    for info in zf.infolist():
        if not _is_safe_path(info.filename):
            raise ValidationError(
                f"Unsafe path in bundle: {info.filename!r}"
            )
        total += info.file_size
        if total > MAX_UNCOMPRESSED_SIZE:
            raise ValidationError(
                f"Bundle uncompressed size exceeds {MAX_UNCOMPRESSED_SIZE // 1024 // 1024} MB"
            )

    # Asset extension allowlist (anything under assets/).
    for name in names:
        if name in REQUIRED_FILES or name.endswith("/"):
            continue
        if name.startswith("assets/"):
            ext = Path(name).suffix.lower()
            if ext not in ALLOWED_ASSET_EXTENSIONS:
                raise ValidationError(
                    f"Disallowed asset extension in bundle: {name}"
                )
        else:
            raise ValidationError(
                f"Unexpected file outside assets/: {name}"
            )

    # Always rewind for re-reading.
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)


def extract_bundle(uploaded_file, theme):
    """Validate + atomically extract a bundle into theme.directory."""
    validate_bundle(uploaded_file)
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)
    zf = zipfile.ZipFile(uploaded_file)

    dest = theme.directory
    staging = dest.with_name(dest.name + ".new")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    for info in zf.infolist():
        if info.filename.endswith("/"):
            continue
        target = staging / info.filename
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)

    if dest.exists():
        shutil.rmtree(dest)
    os.rename(staging, dest)
```

- [ ] **Step 7.4: Add `ThemeAdmin` to `campaigns/admin.py`**

In `campaigns/admin.py`, alongside the other admin classes:

```python
from django import forms

from .models import Theme
from .themes_upload import extract_bundle


class ThemeUploadForm(forms.ModelForm):
    bundle = forms.FileField(
        required=False,
        help_text=(
            "Upload a .zip containing submission_form.html, "
            "submission_success.html, and an optional assets/ directory. "
            "Max 10 MB."
        ),
    )

    class Meta:
        model = Theme
        fields = ("name", "slug", "description", "is_default", "bundle")


@admin.register(Theme)
class ThemeAdmin(ModelAdmin):
    form = ThemeUploadForm
    list_display = ("name", "slug", "is_default", "created_by", "created_at")
    search_fields = ("name", "slug", "description")
    readonly_fields = ("created_at", "created_by")

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
        bundle = form.cleaned_data.get("bundle")
        if bundle:
            extract_bundle(bundle, obj)
```

If `ModelAdmin` isn't already imported in admin.py from `unfold.admin`, ensure the import is at the top.

- [ ] **Step 7.5: Run tests**

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_themes.ThemeBundleValidationTests -v 2
```
Expected: 5 tests pass.

Also run the full suite:

```bash
docker exec raffle-web python manage.py test campaigns -v 0
```

- [ ] **Step 7.6: Commit**

```bash
git add campaigns/themes_upload.py campaigns/admin.py campaigns/tests/test_themes.py
git commit -m "feat(admin): ThemeAdmin with .zip upload + bundle validation"
```

---

## Task 8: Add a permission test for ThemeAdmin

Verify that only superusers can add/change/delete themes via the admin.

**Files:**
- Test: `campaigns/tests/test_themes.py` (append)

- [ ] **Step 8.1: Write the test**

Append:

```python
from django.contrib.auth.models import User
from django.urls import reverse


class ThemeAdminPermissionsTests(TestCase):
    def setUp(self):
        self.su = User.objects.create_superuser("root", "r@x.test", "x")
        self.staff = User.objects.create_user(
            "alice", "a@x.test", "x", is_staff=True
        )

    def test_staff_cannot_view_theme_changelist(self):
        self.client.force_login(self.staff)
        r = self.client.get(reverse("admin:campaigns_theme_changelist"))
        # has_module_permission=False means the user gets a 403 or is redirected
        # away from the changelist.
        self.assertIn(r.status_code, (302, 403, 404))

    def test_superuser_sees_theme_changelist(self):
        self.client.force_login(self.su)
        r = self.client.get(reverse("admin:campaigns_theme_changelist"))
        self.assertEqual(r.status_code, 200)
```

- [ ] **Step 8.2: Run + verify it passes (the implementation is in Task 7)**

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_themes.ThemeAdminPermissionsTests -v 2
```
Expected: 2 tests pass.

- [ ] **Step 8.3: Commit**

```bash
git add campaigns/tests/test_themes.py
git commit -m "test(themes): ThemeAdmin is superuser-only"
```

---

## Task 9: View rewrites + delete old `templates/campaigns/submission_*.html`

The go-live moment. The three public views switch to the engine.from_string pattern. The old in-repo `submission_form.html` / `submission_success.html` files are deleted (their content lives at `campaigns/themes/futboleros/` and on disk at `<THEMES_ROOT>/futboleros/`).

**Files:**
- Modify: `campaigns/views.py` (3 view functions)
- Delete: `campaigns/templates/campaigns/submission_form.html`
- Delete: `campaigns/templates/campaigns/submission_success.html`
- Delete (or evaluate): some `campaigns/static/campaigns/landing/*` files and `campaigns/static/campaigns/fonts/Andreas.ttf` — only if NO other in-repo template uses them. If any remain referenced (e.g., the dashboard might use the logo), leave those in place.
- Test: `campaigns/tests/test_themes.py` (append render tests)

- [ ] **Step 9.1: Write the failing render tests**

Append:

```python
class ThemeRenderTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        # Override THEMES_ROOT and build a tiny custom theme + the default.
        self._override = override_settings(THEMES_ROOT=self.tmp)
        self._override.enable()
        self.addCleanup(self._override.disable)

        # Custom theme
        self.t = Theme.objects.create(name="Mini", slug="mini")
        self.t.directory.mkdir(parents=True)
        (self.t.directory / "submission_form.html").write_text(
            "<html>FORM:{{ campaign.name }}</html>"
        )
        (self.t.directory / "submission_success.html").write_text(
            "<html>OK:{{ campaign.name }}</html>"
        )

        # Default theme directory (used by Campaigns with theme=None)
        default = Theme.get_default()
        default.directory.mkdir(parents=True)
        (default.directory / "submission_form.html").write_text(
            "<html>DEFAULT FORM:{{ campaign.name }}</html>"
        )
        (default.directory / "submission_success.html").write_text(
            "<html>DEFAULT OK:{{ campaign.name }}</html>"
        )

        from campaigns.models import Campaign
        self.c_themed = Campaign.objects.create(
            name="Themed", slug="themed",
            start_date="2026-06-01", end_date="2026-06-30",
            is_active=True, theme=self.t,
        )
        self.c_default = Campaign.objects.create(
            name="Plain", slug="plain",
            start_date="2026-06-01", end_date="2026-06-30",
            is_active=True,
        )

    def test_themed_campaign_renders_its_theme(self):
        r = self.client.get("/submit/themed/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"FORM:Themed", r.content)

    def test_unset_theme_falls_back_to_default(self):
        r = self.client.get("/submit/plain/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"DEFAULT FORM:Plain", r.content)

    def test_broken_theme_directory_404s(self):
        # Wipe the themed theme's submission_form.html
        (self.t.directory / "submission_form.html").unlink()
        r = self.client.get("/submit/themed/")
        self.assertEqual(r.status_code, 404)
```

- [ ] **Step 9.2: Verify fail**

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_themes.ThemeRenderTests -v 2
```
Expected: `test_themed_campaign_renders_its_theme` fails because the view still uses `render(request, "campaigns/submission_form.html", ...)`, not the theme directory.

- [ ] **Step 9.3: Rewrite `submission_form` and `submission_success` in `campaigns/views.py`**

Replace the existing `def submission_form(...)` body — find it (around line 33). The current body uses `render(request, 'campaigns/submission_form.html', context)`. Replace the final return statement with:

```python
    from django.template import engines

    theme = campaign.theme_id and campaign.theme or Theme.get_default()
    tpl_path = theme.directory / "submission_form.html"
    if not tpl_path.is_file():
        from django.http import Http404
        raise Http404
    template = engines["django"].from_string(tpl_path.read_text(encoding="utf-8"))
    context["theme"] = theme
    return HttpResponse(template.render(context, request))
```

(The local helpers — `_get_managed_campaign_or_403`, the existing `context` dict, etc. — stay as-is. Only the final render is replaced.)

Make sure `Theme` is imported at the top of `views.py`:

```python
from .models import Campaign, Prize, Submission, SubmissionCode, Raffle, RaffleWinner, Theme
```

Repeat for `submission_success` (uses `submission_success.html`) and `submission_form_preview` (uses `submission_form.html` — same template, different staff-mode context).

Refactor: extract a helper to avoid duplication:

```python
def _render_theme_template(request, campaign, template_name, context):
    theme = campaign.theme or Theme.get_default()
    tpl_path = theme.directory / template_name
    if not tpl_path.is_file():
        raise Http404
    from django.template import engines
    template = engines["django"].from_string(tpl_path.read_text(encoding="utf-8"))
    context["theme"] = theme
    return HttpResponse(template.render(context, request))
```

Place this helper near the top of `views.py` with the other helpers. Then in each view:

```python
return _render_theme_template(request, campaign, "submission_form.html", context)
```

- [ ] **Step 9.4: Delete the old in-repo templates**

```bash
git rm campaigns/templates/campaigns/submission_form.html
git rm campaigns/templates/campaigns/submission_success.html
```

(The content is preserved at `campaigns/themes/futboleros/submission_form.html` and `submission_success.html`.)

- [ ] **Step 9.5: Audit the static assets that moved into the theme**

```bash
grep -rn "campaigns/landing\|campaigns/fonts/Andreas" \
    campaigns/templates campaigns/admin.py campaigns/views.py raffle_project
```

For each remaining reference (likely in `dashboard.html` or `base.html`, or zero hits):
- If a reference exists, leave both copies (one in `static/`, one in `themes/futboleros/assets/`). The originals stay; theme assets are an additional copy.
- If no reference exists, the originals can be deleted:

```bash
git rm campaigns/static/campaigns/landing/*.png   # adjust to actual files
git rm campaigns/static/campaigns/fonts/Andreas.ttf
```

(Be conservative — when in doubt, leave the originals.)

- [ ] **Step 9.6: Run tests**

```bash
docker exec raffle-web python manage.py test campaigns -v 0
```
Expected: full suite green, including the 3 new render tests. If any pre-existing test fails because it asserts content from the old template at the old path, fix it by EITHER (a) creating a Theme/Campaign fixture and using the test-client through the new code path, OR (b) accepting that the old test was tightly coupled to file-system layout and updating its assertions.

- [ ] **Step 9.7: Commit**

```bash
git add campaigns/views.py campaigns/templates/campaigns/ campaigns/static/campaigns/ campaigns/tests/test_themes.py
git commit -m "feat(themes): public views render from theme.directory + remove old in-repo templates"
```

---

## Task 10: Expose `Campaign.theme` in CampaignAdmin

So operators can pick a theme on the Campaign change form.

**Files:**
- Modify: `campaigns/admin.py` (CampaignAdmin fieldsets)
- Test: `campaigns/tests/test_themes.py` (append)

- [ ] **Step 10.1: Write the failing test**

```python
class CampaignAdminThemeDropdownTests(TestCase):
    def test_campaign_change_form_includes_theme_field(self):
        from campaigns.models import Campaign
        su = User.objects.create_superuser("root", "r@x.test", "x")
        c = Campaign.objects.create(
            name="C", slug="c",
            start_date="2026-06-01", end_date="2026-06-30",
        )
        self.client.force_login(su)
        r = self.client.get(
            reverse("admin:campaigns_campaign_change", args=[c.id])
        )
        self.assertContains(r, "id_theme")
        self.assertContains(r, "Futboleros (Mundial 2026)")
```

- [ ] **Step 10.2: Verify fail**

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_themes.CampaignAdminThemeDropdownTests -v 2
```
Expected: fails because `id_theme` isn't in the rendered form.

- [ ] **Step 10.3: Add `theme` to `CampaignAdmin.fieldsets`**

In `campaigns/admin.py`, locate the `CampaignAdmin.fieldsets`. Find the "Basics" section (the one that contains `name`, `slug`, `description`). Add `'theme'` to its `fields` tuple, AFTER `slug` and BEFORE `description`:

```python
        ('Basics', {
            'fields': ('name', 'slug', 'theme', 'description', 'is_active'),
        }),
```

(If the multi-domain branch has been merged and `domain` is also in this fieldset, place `theme` right after `domain`.)

- [ ] **Step 10.4: Run tests**

```bash
docker exec raffle-web python manage.py test campaigns -v 0
```
Expected: full suite green.

- [ ] **Step 10.5: Commit**

```bash
git add campaigns/admin.py campaigns/tests/test_themes.py
git commit -m "feat(admin): expose Campaign.theme in CampaignAdmin Basics fieldset"
```

---

## Task 11: `setup_default_theme` management command

Operator recovery tool: re-populate `<THEMES_ROOT>/futboleros/` if it gets wiped.

**Files:**
- Create: `campaigns/management/__init__.py` (likely exists)
- Create: `campaigns/management/commands/__init__.py` (likely exists)
- Create: `campaigns/management/commands/setup_default_theme.py`
- Test: `campaigns/tests/test_themes.py` (append)

- [ ] **Step 11.1: Write the failing test**

Append:

```python
from io import StringIO
from django.core.management import call_command


class SetupDefaultThemeCommandTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self._override = override_settings(THEMES_ROOT=self.tmp)
        self._override.enable()
        self.addCleanup(self._override.disable)

    def test_command_populates_directory(self):
        out = StringIO()
        call_command("setup_default_theme", stdout=out)
        self.assertTrue((Path(self.tmp) / "futboleros" / "submission_form.html").is_file())

    def test_command_is_idempotent_without_force(self):
        call_command("setup_default_theme")
        target = Path(self.tmp) / "futboleros" / "submission_form.html"
        target.write_text("MUTATED")
        call_command("setup_default_theme")
        # Without --force, the mutated content is preserved.
        self.assertEqual(target.read_text(), "MUTATED")

    def test_force_refreshes(self):
        call_command("setup_default_theme")
        target = Path(self.tmp) / "futboleros" / "submission_form.html"
        target.write_text("MUTATED")
        call_command("setup_default_theme", "--force")
        self.assertNotEqual(target.read_text(), "MUTATED")
```

- [ ] **Step 11.2: Verify fail**

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_themes.SetupDefaultThemeCommandTests -v 2
```
Expected: `CommandError: Unknown command 'setup_default_theme'`.

- [ ] **Step 11.3: Create the command**

```bash
mkdir -p campaigns/management/commands
touch campaigns/management/__init__.py campaigns/management/commands/__init__.py
```

`campaigns/management/commands/setup_default_theme.py`:

```python
from django.core.management.base import BaseCommand

from campaigns.themes_setup import copy_default_theme_to_themes_root


class Command(BaseCommand):
    help = (
        "Copy the in-repo default theme into THEMES_ROOT/futboleros/. "
        "Idempotent by default; use --force to re-copy."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Replace the destination directory even if it exists.",
        )

    def handle(self, *args, **options):
        dest = copy_default_theme_to_themes_root(force=options["force"])
        self.stdout.write(self.style.SUCCESS(f"Default theme at {dest}"))
```

- [ ] **Step 11.4: Run tests**

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_themes.SetupDefaultThemeCommandTests -v 2
```
Expected: 3 tests pass.

- [ ] **Step 11.5: Commit**

```bash
git add campaigns/management/ campaigns/tests/test_themes.py
git commit -m "feat(themes): setup_default_theme management command (operator recovery)"
```

---

## Task 12: Authoring docs

A guide for the next developer who needs to ship a theme.

**Files (create):**
- `docs/themes/authoring.md`

- [ ] **Step 12.1: Write the docs**

```markdown
# Theme authoring guide

A "theme" is a `.zip` bundle that styles the public submission form + success page for one or more campaigns. Each Campaign has a `theme` field; if unset, the seeded default theme (`futboleros`) is used.

## Bundle layout

```
my-theme.zip
├── submission_form.html         (REQUIRED)
├── submission_success.html      (REQUIRED)
└── assets/                      (optional)
    ├── logo.svg
    ├── fonts/
    │   └── MyFont.woff2
    └── styles.css
```

## Upload

1. Log into the Django admin as a superuser.
2. Themes → Add theme.
3. Fill `name`, `slug`, `description`. The slug becomes the URL prefix for the theme's assets (`/theme-assets/<slug>/...`).
4. Upload the `.zip` in the "Bundle" field.
5. Save. The server validates the bundle and extracts it to `<settings.THEMES_ROOT>/<slug>/`.

Re-uploading replaces the directory atomically. Deleting the theme removes its directory (only allowed if no campaigns reference it).

## Validation rules

The uploader rejects bundles that:
- Aren't a valid `.zip`
- Are larger than 10 MB uncompressed
- Lack `submission_form.html` or `submission_success.html` at the root
- Contain any path with `..` or starting with `/`
- Contain assets with extensions outside the allowlist (allowed: `svg, png, jpg, jpeg, webp, gif, css, woff, woff2, ttf, otf, ico`)

## Template context

Your `submission_form.html` and `submission_success.html` are rendered through Django's normal template engine. Available variables:

| Variable | Type | Available in |
|---|---|---|
| `campaign` | Campaign instance — has `.name`, `.slug`, `.public_url`, `.display_title`, `.primary_color`, `.logo`, `.sidebar_color`, `.start_date`, `.end_date`, `.description`, etc. | both |
| `prizes` | QuerySet of active Prize rows ordered by `.order` | both |
| `theme` | The resolved Theme — useful as `{{ theme.slug }}` | both |
| `form` | Bound Django Form for the submission | `submission_form` only |
| `submission` | Just-created Submission instance | `submission_success` only |
| `code_field_name`, `code_field_label` | str — used by the existing Futboleros template | `submission_form` only |

## Referencing assets

Use the `theme_static` tag for any path inside your `assets/` directory:

```django
{% load theme_tags %}

<link rel="stylesheet" href="{% theme_static 'styles.css' %}">
<img src="{% theme_static 'logo.svg' %}">

<style>
  @font-face {
    font-family: 'MyFont';
    src: url("{% theme_static 'fonts/MyFont.woff2' %}");
  }
</style>
```

`{% theme_static 'logo.svg' %}` resolves to `/theme-assets/<your-slug>/logo.svg`. Hardcoded paths work but tie the theme to its slug.

## Minimal example

`submission_form.html`:

```django
{% load theme_tags %}
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>{{ campaign.name }}</title>
  <link rel="stylesheet" href="{% theme_static 'styles.css' %}">
</head>
<body>
  <h1>{{ campaign.name }}</h1>
  <form method="post" enctype="multipart/form-data">
    {% csrf_token %}
    {{ form.as_p }}
    <button type="submit">Submit</button>
  </form>
</body>
</html>
```

`submission_success.html`:

```django
{% load theme_tags %}
<!DOCTYPE html>
<html>
<head>
  <title>Thanks</title>
  <link rel="stylesheet" href="{% theme_static 'styles.css' %}">
</head>
<body>
  <h1>Thanks, {{ submission.first_name }}!</h1>
  <p>Your entry is recorded.</p>
</body>
</html>
```

`assets/styles.css`:

```css
body { font-family: system-ui; max-width: 480px; margin: 40px auto; }
```

Zip those three files (preserving the `assets/` directory) and upload.

## Local development

In dev, the same upload flow works. THEMES_ROOT defaults to `<repo>/themes/` (gitignored). Assets served by Django's `/theme-assets/<slug>/<path>` URL route.

To preview a theme without uploading:
1. Drop the bundle layout into `<repo>/themes/<slug>/` manually.
2. Create a Theme row in admin or shell with that slug.
3. Assign a Campaign to it.
```

- [ ] **Step 12.2: Commit**

```bash
mkdir -p docs/themes
# (write the file above to docs/themes/authoring.md)
git add docs/themes/authoring.md
git commit -m "docs(themes): authoring guide"
```

---

## Task 13: Operator docs + backup wiring

`RUNNING.md`, `docs/deployment/host-setup.md`, `docs/deployment/restore-playbook.md`, and `scripts/raffle-restic-backup.sh` updates.

**Files:**
- Modify: `RUNNING.md`
- Modify: `docs/deployment/host-setup.md`
- Modify: `docs/deployment/restore-playbook.md`
- Modify: `scripts/raffle-restic-backup.sh`

- [ ] **Step 13.1: Update `RUNNING.md`**

Append a section near the end:

```markdown
## Themes (local dev)

The public submission form and success page render from a theme bundle, not directly from `campaigns/templates/`. Local dev uses `<repo>/themes/<slug>/` as `THEMES_ROOT`.

After `migrate` runs the first time, the default Futboleros theme is auto-populated at `<repo>/themes/futboleros/`. If you wipe the directory, restore it with:

\`\`\`bash
docker exec raffle-web python manage.py setup_default_theme
\`\`\`

To test a custom theme without going through the upload UI:
1. Build the bundle layout at `<repo>/themes/<my-slug>/{submission_form.html, submission_success.html, assets/}`.
2. Create the Theme row: `docker exec -it raffle-web python manage.py shell` → `from campaigns.models import Theme; Theme.objects.create(name="X", slug="my-slug")`.
3. Assign a Campaign to it in admin.
```

- [ ] **Step 13.2: Update `docs/deployment/host-setup.md`**

Add `/srv/raffle/themes` to the filesystem provisioning section. Find the existing block that creates `/srv/raffle/{pg,pgbackrest,media,staticfiles,config,migration}` (or similar). Add:

```bash
sudo install -d -o root -g root -m 755 /srv/raffle/themes
```

Then add a section about the nginx config for theme assets:

```markdown
## Theme asset routing (nginx)

Theme bundles ship images, fonts, and CSS under `/srv/raffle/themes/<slug>/assets/`. Add this `location` block to the app's nginx vhost (above the Django proxy_pass block):

\`\`\`nginx
location ~ ^/theme-assets/([^/]+)/(.+)$ {
    alias /srv/raffle/themes/$1/assets/$2;
    expires 7d;
    add_header Cache-Control "public, immutable";
}
\`\`\`

This bypasses Django for asset requests; the app only sees `/submit/<slug>/` and `/dashboard/`.

If you skip this step, theme assets will still serve in dev (Django handles the route), but prod is slower because every asset goes through gunicorn.
```

- [ ] **Step 13.3: Update `docs/deployment/restore-playbook.md`**

Append:

```markdown
## Themes during restore

`/srv/raffle/themes/` is backed up by restic alongside `/srv/raffle/media/`. After a restore:

1. Verify `/srv/raffle/themes/futboleros/` exists and contains the expected files.
2. If missing, run `docker exec raffle-prod python manage.py setup_default_theme --force` to repopulate from the in-repo source.
3. Verify any custom themes you've uploaded are present. If not, re-upload from your offline copy (themes are NOT in git for any non-default theme).
```

- [ ] **Step 13.4: Update `scripts/raffle-restic-backup.sh`**

Find the existing `INCLUDE` array or include arguments. Add `/srv/raffle/themes`:

```bash
restic backup \
    /srv/raffle/media \
    /srv/raffle/themes \
    ...
```

Place it between `/srv/raffle/media` and any other includes — keep alphabetical order if the script uses one.

- [ ] **Step 13.5: Commit**

```bash
git add RUNNING.md docs/deployment/host-setup.md docs/deployment/restore-playbook.md scripts/raffle-restic-backup.sh
git commit -m "docs+backup: operator docs for themes + restic includes themes dir"
```

---

## Task 14: Push + open PR + update memory

- [ ] **Step 14.1: Push the branch and open PR**

```bash
git push -u origin feat/per-campaign-templates
gh pr create --title "Per-campaign templates" --body "$(cat <<'EOF'
## Summary
- New `Theme` model + `Campaign.theme` FK. Each Campaign picks a theme; null = default.
- Devs upload `.zip` bundles via Django admin (superuser only). Validation enforces bundle layout + asset extension allowlist + 10 MB limit + zip-slip protection. Re-upload swaps atomically.
- Public views render the campaign's theme from `<THEMES_ROOT>/<slug>/submission_form.html` via `engines["django"].from_string(...)`. Assets served from `/theme-assets/<slug>/...` (nginx in prod, Django serve in dev).
- Existing Futboleros design moved to `campaigns/themes/futboleros/`; auto-seeded as the default theme via migration. No existing campaign requires action — they continue rendering Futboleros.
- `setup_default_theme` management command for operator recovery.
- Operator docs updated (RUNNING.md, host-setup.md, restore-playbook.md). Backup script includes `/srv/raffle/themes`.

## Spec + plan
- Spec: `docs/superpowers/specs/2026-05-20-per-campaign-templates-design.md`
- Plan: `docs/superpowers/plans/2026-05-20-per-campaign-templates.md`

## Test plan
- [ ] Full pytest: `docker exec raffle-web python manage.py test campaigns -v 0` (≥130 tests, 0 failures)
- [ ] Manual: upload a minimal test bundle via admin, assign to a campaign, GET `/submit/<slug>/` from the campaign's host — render uses the new bundle
- [ ] Manual: invalid bundle (missing required file) rejected at upload
- [ ] Manual: zip-slip bundle rejected
- [ ] Manual: delete a theme not referenced by any campaign — directory disappears
- [ ] Manual: delete a theme referenced by a campaign — ProtectedError

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 14.2: Update memory**

In `/home/elgran/.claude/projects/-home-elgran-Projects-raffle-campaign/memory/`:

- Create `project_per_campaign_templates_v2.md` (or update the existing `project_per_campaign_templates.md`) with the "shipped" status + PR link.
- Update `MEMORY.md` to point at the new/updated file.

(This step is done via the assistant's memory tooling, not via git.)

- [ ] **Step 14.3: After merge, verify dev still boots**

```bash
git checkout main && git pull
RAFFLE_CAMPAIGN_WEB_PORT=8500 docker compose up -d
docker exec raffle-web python manage.py migrate
docker exec raffle-web python manage.py setup_default_theme
docker exec raffle-web python manage.py test campaigns -v 0
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8500/dashboard/login/  # 200
```

---

## Out-of-scope follow-ups (not in this plan)

- Caching: per-view + ETag once a high-traffic theme appears.
- A `themes.W001` system check that warns when a Theme row has a missing on-disk directory.
- Operator-authored HTML (would require template sandboxing — a separate workstream).
- Per-campaign override of variables (`headline_color`, `logo`) on top of a theme. The existing `display_title`/`logo`/`primary_color`/`sidebar_color` fields on Campaign cover most of this need.
- Theme inheritance (`{% extends "themes/base/..." %}`).
- Theme versioning + rollback (git history of `campaigns/themes/futboleros/` covers the default).
- Theme migration helpers (renaming a context variable would break every theme that uses it).

# Per-Campaign Templates — Design Spec

**Date:** 2026-05-20
**Status:** Approved (design phase complete; implementation plan to follow)
**Author:** brainstorm session with user

---

## 1. Problem statement

`campaigns/templates/campaigns/submission_form.html` is currently a fully customer-specific design (5-step Mundial 2026 / Futboleros, 854 lines, custom Andreas font, blue+red palette, custom AJAX state machine). `submission_success.html` is the legacy generic navy "RaffleManager" lockup (212 lines, untouched since the initial commit).

There is no canonical "platform" public form — the file in `campaigns/templates/campaigns/submission_form.html` is one customer's bespoke design that happens to be the global default. Any new customer who needs a different design today would either:

- Replace the file in git, destroying Futboleros's design,
- Maintain a fork per customer, or
- Stuff conditionals into the existing template for every variant.

None of those scale. The goal is to make the public form + success pages **selectable per Campaign**, with developers shipping new "themes" via an admin-side upload mechanism so operators can pick from a list.

This spec is downstream of the multi-domain campaigns workstream ([[project_multi_domain_campaigns]]) — Campaigns are already bound to Domains, and the tenant-isolation primitives (`visible_to`) are in place. Theme selection becomes a regular Campaign field gated by those same primitives.

## 2. Goals

- **G1.** Each Campaign can have its own `theme`, which controls how the public submission form and success page render. Selecting a theme is a one-field choice in the Campaign change form.
- **G2.** Developers ship a new theme via a single `.zip` upload to a Django admin page — no code redeploy required for the theme content itself.
- **G3.** Existing campaigns continue to render exactly as they do today, with no operator action required. The current Futboleros design becomes the seeded default theme.
- **G4.** Themes are stored on disk under `/srv/raffle/themes/<slug>/` (prod) — a new bind-mount that joins the existing `/srv/raffle/{pg,media,pgbackrest,...}` family — so the zero-data-loss backup stack picks them up.
- **G5.** Theme `assets/` (images, fonts, CSS) are served from a stable URL `/theme-assets/<slug>/...` so theme HTML can reference them with a small custom template tag.
- **G6.** Validation on upload prevents zip-slip, path traversal, and arbitrary file types; theme directories cannot escape `/srv/raffle/themes/`.

## 3. Non-goals

- **Operator-authored HTML.** Only developers (superusers) create or edit themes. Operators select from the existing theme list. Sandboxing operator-supplied Django template tags is out of scope.
- **Per-campaign variable overrides.** Operators don't override `headline_color` or `logo` per campaign separately from the theme — those choices belong to the theme bundle itself. The existing per-campaign branding fields (`display_title`, `logo`, `primary_color`, `sidebar_color`) remain available to theme authors as template context but are not a separate "theme override UI".
- **Theme inheritance / partials sharing across themes.** Each theme is a complete bundle. No `extends "base-theme/...html"` across themes.
- **Multiple `is_default` themes per Domain.** One default theme platform-wide.
- **Theme versioning.** Re-upload replaces the directory atomically. No history; if devs want to roll back, they re-upload the prior bundle. The git history of `campaigns/themes/futboleros/` covers the in-repo default theme.
- **Theme marketplace / public discovery.** Themes are an internal admin concept.
- **Live preview before save.** Operators select a theme via FK dropdown, save the campaign, then visit `/submit/<slug>/preview/` to see it. No inline iframe preview.

## 4. Architecture

### 4.1 Theme model

```python
class Theme(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    description = models.CharField(max_length=500, blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True
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

    @property
    def directory(self):
        return Path(settings.THEMES_ROOT) / self.slug

    @classmethod
    def get_default(cls):
        return cls.objects.get(is_default=True)
```

The `UniqueConstraint` with `condition` enforces at most one row with `is_default=True` at the DB level (Postgres partial unique index; SQLite simulates this via the same syntax in Django 4.1+).

Setting `is_default=True` on an admin save also demotes the previous default in a `save()` override (defense in depth — the partial constraint catches a race, but the user-visible error from a constraint failure is poor; the save() override gives operators a clean "default updated" experience).

### 4.2 Campaign changes

```diff
 class Campaign(models.Model):
     ...
+    theme = models.ForeignKey(
+        Theme,
+        on_delete=models.PROTECT,
+        related_name="campaigns",
+        null=True,
+        blank=True,
+    )
```

`null=True` means "use the default theme". `on_delete=PROTECT` so an operator can't delete a Theme that campaigns still depend on.

### 4.3 Bundle layout

A theme `.zip` bundle has this structure:

```
my-theme.zip
├── submission_form.html         (REQUIRED)
├── submission_success.html      (REQUIRED)
└── assets/                      (optional, may contain subdirectories)
    ├── logo.svg
    ├── fonts/
    │   └── MyFont.woff2
    └── styles.css
```

Validation (rejected at upload time):

| Rule | Reason |
|---|---|
| `.zip` extension + valid zip structure | Format sanity |
| Total uncompressed size ≤ 10 MB | Prevent disk-fill |
| `submission_form.html` and `submission_success.html` at bundle root | Contract |
| Asset files must use extensions: `svg, png, jpg, jpeg, webp, gif, css, woff, woff2, ttf, otf, ico` | Prevent shipping executables/scripts |
| No paths containing `..`, no absolute paths, no symlinks | Zip-slip defense |
| No files outside the bundle root or `assets/` subtree | Predictable layout |

### 4.4 Storage

- `settings.THEMES_ROOT`:
  - Prod: `/srv/raffle/themes` (new bind-mount, mode 755, owned by root; container reads it)
  - Dev: `BASE_DIR / "themes"` (gitignored)
- On upload, the admin form extracts the validated `.zip` to `<THEMES_ROOT>/<slug>.new/`, then `os.rename(<slug>.new, <slug>)` — atomic POSIX swap. If `<slug>` previously existed, the old directory is removed BEFORE the rename. This is a brief moment where the directory doesn't exist; concurrent reads during that window get a 404 from the view (Section 4.6 handles this).
- On theme deletion, `shutil.rmtree(<THEMES_ROOT>/<slug>)` runs in a post-delete signal handler. Deletion is gated by `on_delete=PROTECT` on `Campaign.theme`, so the directory removal only fires when no campaigns reference the theme — safe.

### 4.5 Asset URL serving

- URL pattern: `/theme-assets/<slug>/<path:rest>`
- **Dev:** Django view that wraps `django.views.static.serve` with `document_root=settings.THEMES_ROOT / <slug> / assets`. This is the standard pattern Django docs use for serving user-uploaded media in dev.
- **Prod:** nginx serves directly from the bind-mount. Add a `location` block (documented in `docs/deployment/host-setup.md`):

```nginx
location ~ ^/theme-assets/([^/]+)/(.+)$ {
    alias /srv/raffle/themes/$1/assets/$2;
    expires 7d;
    add_header Cache-Control "public, immutable";
}
```

Django doesn't see asset requests in prod — nginx short-circuits them. The Django URL route is registered only when `DEBUG=True` (and skipped when `DEBUG=False` to make accidental hits explicit).

### 4.6 Runtime rendering

The three public views (`submission_form`, `submission_success`, `submission_form_preview`) follow the same pattern:

```python
from django.template import engines


def submission_form(request, campaign_slug):
    campaign = _get_campaign_for_host(request, campaign_slug)
    theme = campaign.theme or Theme.get_default()
    template_path = theme.directory / "submission_form.html"
    if not template_path.is_file():
        # Theme bundle is corrupted (deleted manually, mid-upload, etc.).
        # Fail fast — operator must re-upload.
        raise Http404
    template = engines["django"].from_string(
        template_path.read_text(encoding="utf-8")
    )
    return HttpResponse(template.render(context, request))
```

Notes:
- No custom template loader. Direct filesystem read keeps the magic low.
- Rendered HTML passes through Django's normal template engine — full autoescape, `{% if %}`, `{% for %}`, `{% url %}`, etc.
- File reads happen per request. Acceptable for human-paced submission flows; can be cached later via Django's per-view cache if a high-traffic theme needs it.
- The `Http404` on missing-file is conservative — better than a 500. Operators see a 404, check `manage.py check`, and re-upload.

### 4.7 The `{% theme_static %}` template tag

Theme authors reference assets via:

```html
{% load theme_tags %}
<link rel="stylesheet" href="{% theme_static 'styles.css' %}">
<img src="{% theme_static 'logo.svg' %}">
<style>
  @font-face {
    src: url("{% theme_static 'fonts/MyFont.woff2' %}");
  }
</style>
```

Implementation:

```python
@register.simple_tag(takes_context=True)
def theme_static(context, path):
    theme = context.get("theme") or Theme.get_default()
    return f"/theme-assets/{theme.slug}/{path}"
```

The `theme` variable is in the rendering context (populated by the view), so the tag self-resolves to the right slug. Hardcoded `/theme-assets/futboleros/...` paths also work but couple the theme to its slug — `{% theme_static %}` is the recommended idiom.

### 4.8 Template context contract

Theme authors can rely on the following variables being present:

| Variable | Type | Available in |
|---|---|---|
| `campaign` | `Campaign` instance | both pages |
| `prizes` | `QuerySet[Prize]` filtered to active, ordered by `order` | both pages |
| `theme` | `Theme` instance (the resolved theme, never None) | both pages |
| `form` | bound `SubmissionForm` | `submission_form` only |
| `code_field_name`, `code_field_label` | str (already used by existing template) | `submission_form` only |
| `submission` | the freshly-created `Submission` instance | `submission_success` only |

`docs/themes/authoring.md` documents the contract with a minimal example bundle. Renaming or removing a context variable is a breaking change that requires bumping every theme that uses it — call it out in CHANGELOG.

### 4.9 Permissions

- **Create / edit / delete Theme:** `is_superuser` only in this iteration. (Future: a `template_uploaders` group with `add_theme` / `change_theme` / `delete_theme` perms. Out of scope here.)
- **Select Theme per Campaign:** anyone who can edit the Campaign — i.e., superusers + domain managers + direct campaign managers via the existing `visible_to` primitive. The theme dropdown on the Campaign form is unfiltered (themes are global; all visible to all editors).
- **View theme assets:** public. Anyone hitting `/theme-assets/<slug>/<file>` gets the file. This is correct — theme assets are loaded by anonymous browsers viewing public submission forms.

## 5. Migration & rollout

### 5.1 Repo restructure — **COPY** files into new location (no moves yet, no deletes)

The order matters: we cannot delete the old `templates/campaigns/submission_form.html` until the views in §5.3 are updated, because the views still reference the old path. So this phase only COPIES, then §5.3 finishes the transition.

- COPY `campaigns/templates/campaigns/submission_form.html` → `campaigns/themes/futboleros/submission_form.html`.
- COPY `campaigns/templates/campaigns/submission_success.html` → `campaigns/themes/futboleros/submission_success.html`.
- COPY relevant assets (`campaigns/static/campaigns/landing/*`, `campaigns/static/campaigns/fonts/Andreas.ttf`, etc.) → `campaigns/themes/futboleros/assets/...`. The originals stay in `campaigns/static/` until §5.3.
- Rewrite asset paths inside the NEW copies (`campaigns/themes/futboleros/*.html`) from `{% static 'campaigns/landing/...' %}` to `{% theme_static 'logo.png' %}` (and same for fonts). The originals are untouched.
- **The old `templates/campaigns/*.html` and `static/campaigns/*` files remain in place at the end of this phase.** Nothing changes at runtime.
- §5.3 (view rewrites) is the phase that finally deletes the originals, in the same commit that switches the views over.

### 5.2 Model + initial migrations (`0012_theme.py`, `0013_campaign_theme_fk.py`)

- `0012_theme.py`:
  - `CreateModel Theme` (fields per §4.1)
  - `AddConstraint UniqueConstraint(is_default=True)` partial unique
  - `RunPython`: create the seed row `Theme(name="Futboleros (Mundial 2026)", slug="futboleros", is_default=True, description="Original Mundial 2026 design — La Nube que te mueve")` **AND** call the helper from §5.4 that copies `campaigns/themes/futboleros/` into `<THEMES_ROOT>/futboleros/` so the directory is populated by the same migration that creates the Theme row. This guarantees the runtime view never sees a Theme row whose directory doesn't exist on disk — true in prod, dev, CI, and test environments.

- `0013_campaign_theme_fk.py`:
  - `AddField Campaign.theme` (nullable FK, PROTECT). No backfill needed — null means default, so every existing campaign keeps rendering Futboleros.

### 5.3 View + asset URL implementation (separate commit)

This is the "go-live" commit — the views switch over and the old in-repo originals can finally be deleted.

- Update three public views (`submission_form`, `submission_success`, `submission_form_preview`) to use the pattern in §4.6.
- Add the `theme_tags` template tag library with `{% theme_static %}`.
- Add a URL route `/theme-assets/<slug>/<path:rest>/` (registered as a normal public URL — no auth required; only added to `urlpatterns` when `DEBUG=True` so prod relies on nginx).
- Add `ThemeAdmin` with `.zip` upload widget. Form `clean` enforces validation rules in §4.3.
- Add `Campaign.theme` to `CampaignAdmin` fieldsets (Basics section, next to `domain` and `slug`).
- Add `Theme.save()` override that demotes the previous default when a new one is set.
- Add `Theme` post-delete signal handler that `shutil.rmtree`s the directory.
- **Delete the now-unused files:**
  - `campaigns/templates/campaigns/submission_form.html` (originals from §5.1 are now only in `campaigns/themes/futboleros/`)
  - `campaigns/templates/campaigns/submission_success.html`
  - Original `campaigns/static/campaigns/landing/*` and `campaigns/static/campaigns/fonts/Andreas.ttf` — replaced by their copies under `campaigns/themes/futboleros/assets/`.
- This commit is atomic: at no point during normal operation does the view reference a missing file.

### 5.4 Default theme directory population

A small helper function `_copy_default_theme_to_themes_root()` lives in `campaigns/themes/__init__.py`:

- Copies `campaigns/themes/futboleros/` (in-repo) → `<THEMES_ROOT>/futboleros/` (on-disk).
- Idempotent: skips if the on-disk directory already exists. A `force=True` arg refreshes.

The helper is called from two places:

1. **The 0012 migration's `RunPython` step** (per §5.2). This is the primary path — every migrate run (prod, dev, CI, test) populates the directory. Tests don't need extra setup. Operators don't need to remember an extra command.
2. **A management command `setup_default_theme`** that just calls the helper with `force=True`. This exists for operator recovery: if `/srv/raffle/themes/futboleros/` is wiped accidentally, the operator runs `docker exec raffle-prod python manage.py setup_default_theme --force` to restore without touching the DB or migrations.

The Dockerfile does NOT need an extra step — the directory is populated at migrate time, and `migrate` already runs at startup.

### 5.5 Operator docs

- `RUNNING.md` — note the new `themes/` directory, the `setup_default_theme` command, and how to develop a new theme locally.
- `docs/deployment/host-setup.md` — add `/srv/raffle/themes` to the filesystem provisioning section (mode 755, root owned); add the nginx `location ~ ^/theme-assets/...` block; mention `setup_default_theme` runs at container start.
- `docs/deployment/restore-playbook.md` — themes directory is backed up by restic alongside `/srv/raffle/media`. After a restore, verify themes are present and re-run `setup_default_theme` if not.
- `docs/themes/authoring.md` (NEW) — for developers building new themes: bundle layout, required files, context variables, `{% theme_static %}` usage, validation rules, and a minimal "Hello World" example bundle.

### 5.6 Backup integration

- Add `/srv/raffle/themes` to the restic include list in `scripts/raffle-restic-backup.sh`. This is the only backup-stack change.
- pgBackRest already covers Postgres (the `Theme` rows). No change there.

## 6. File structure (changes)

```
campaigns/
├── models.py                       # +Theme; modify Campaign (add theme FK)
├── admin.py                        # +ThemeAdmin; CampaignAdmin gets theme in Basics fieldset
├── views.py                        # 3 public views switch to engines["django"].from_string
├── templatetags/                   (new dir)
│   ├── __init__.py
│   └── theme_tags.py               # {% theme_static %}
├── migrations/
│   ├── 0012_theme.py               (new)
│   └── 0013_campaign_theme_fk.py   (new)
├── management/
│   └── commands/
│       └── setup_default_theme.py  (new)
├── themes/                         (new dir — in-repo source of default theme)
│   └── futboleros/
│       ├── submission_form.html    (moved from campaigns/templates/campaigns/)
│       ├── submission_success.html (moved from campaigns/templates/campaigns/)
│       └── assets/
│           ├── (moved from campaigns/static/campaigns/landing/*)
│           └── (moved from campaigns/static/campaigns/fonts/*)
├── tests/
│   └── test_themes.py              (new)
├── forms.py                        # +ThemeUploadForm (admin-side; not customer-facing)
docs/
├── themes/
│   └── authoring.md                (new)
└── superpowers/specs/
    └── 2026-05-20-per-campaign-templates-design.md   (this file)
raffle_project/
├── settings.py                     # THEMES_ROOT setting
└── urls.py                         # /theme-assets/<slug>/<path:rest>/ (DEBUG only)
scripts/
└── raffle-restic-backup.sh         # add /srv/raffle/themes to include list
```

Estimated change: ~250 LOC code + ~200 LOC tests + spec + docs.

## 7. Tests

`campaigns/tests/test_themes.py`:

| # | Test | What it verifies |
|---|---|---|
| 1 | `test_theme_str_is_name` | Basic Theme repr |
| 2 | `test_default_theme_is_seeded_by_migration` | Migration 0012 creates Futboleros row |
| 3 | `test_only_one_default_theme_allowed` | Setting `is_default=True` on a second row fails / demotes the first |
| 4 | `test_get_default_returns_seeded_theme` | `Theme.get_default()` works |
| 5 | `test_campaign_theme_fk_nullable` | Existing campaigns can keep `theme=None` |
| 6 | `test_zip_upload_creates_theme_directory` | Happy path: valid bundle → theme.directory has the expected files |
| 7 | `test_zip_upload_rejects_missing_required_file` | Bundle without submission_form.html → ValidationError |
| 8 | `test_zip_upload_rejects_zip_slip` | Bundle with `../../../etc/passwd` → ValidationError |
| 9 | `test_zip_upload_rejects_disallowed_extension` | Bundle with `assets/evil.sh` → ValidationError |
| 10 | `test_zip_upload_atomic_swap_on_reupload` | Re-upload to existing slug replaces directory; old contents gone |
| 11 | `test_view_uses_campaign_theme_when_set` | Campaign with theme=X → view renders X's submission_form.html |
| 12 | `test_view_falls_back_to_default_when_campaign_theme_is_null` | Campaign with theme=None → view renders default theme |
| 13 | `test_view_404s_if_theme_directory_is_broken` | Missing template file → 404 |
| 14 | `test_theme_static_tag_resolves_to_correct_slug` | `{% theme_static 'logo.svg' %}` produces `/theme-assets/<slug>/logo.svg` |
| 15 | `test_theme_assets_url_serves_existing_file_in_dev` | DEBUG=True, GET `/theme-assets/futboleros/logo.svg` → 200 |
| 16 | `test_theme_assets_url_404s_for_missing_file` | GET `/theme-assets/futboleros/nope.png` → 404 |
| 17 | `test_setup_default_theme_command_is_idempotent` | Running twice doesn't fail or change result |
| 18 | `test_setup_default_theme_force_refreshes` | `--force` re-copies even if directory exists |
| 19 | `test_only_superuser_can_create_theme_in_admin` | Non-superuser POSTs to theme add → 403/302 |
| 20 | `test_campaign_admin_shows_theme_dropdown_to_managers` | Manager opens campaign change form → theme select is present |
| 21 | `test_protect_blocks_theme_delete_when_campaign_references_it` | Theme has campaigns → delete raises ProtectedError |

That brings the suite from 147 → ~168 passing.

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Operator force-deletes a theme directory on disk → views 404 in prod | The view raises 404 cleanly; `manage.py check` does NOT detect this (file system check not implemented in this scope). Operators see the 404, run `setup_default_theme` or re-upload via admin. Future: add a `themes.W001` system check that verifies every Theme row has its `directory` populated. Filed as follow-up. |
| Theme upload race: two operators upload `same-slug.zip` simultaneously | The atomic swap means only one wins; the other's `os.rename` operates on the already-renamed-out directory and either succeeds harmlessly or raises. Acceptable for the expected operator volume (single-digit uploads per week). |
| Bundle author's template references a context variable that doesn't exist | Django renders the variable as empty string by default (autoescape). The page renders broken but doesn't 500. Bundle author tests in dev. |
| Bundle author injects `{% load %}` to pull in arbitrary tags | The render uses `engines["django"]` with the default Django template backend. `{% load %}` can only load tag libraries registered in `INSTALLED_APPS`. Bundle authors are trusted developers (superuser permission required to upload) — this is acceptable. |
| Adding `theme_static` URL in dev exposes `/srv/raffle/themes/` directory listing | We use `django.views.static.serve` which only serves named files, not directory indexes. `show_indexes=False` is the Django default. |
| Backup snapshot from before this spec ships, restored after → no themes directory on disk | After restore, run `python manage.py setup_default_theme` and verify. Documented in `restore-playbook.md`. |
| Theme deletion races with a public submission render | The protect FK ensures themes referenced by Campaigns can't be deleted. Themes not referenced can be deleted, and any in-flight requests for them get 404. Acceptable. |
| `engines["django"].from_string(text).render(context, request)` re-parses the template every request | At expected volume (humans clicking forms), unmeasurable. If it ever shows up in profiling, add an LRU cache keyed on `(theme.slug, mtime)` in the view. Not in scope for v1. |

## 9. Implementation phases (preview; the implementation plan will expand each)

1. **Phase 1 — Theme model + Campaign FK + migrations.** Migrations 0012, 0013. Seeded default theme row. Tests 1-5, 21.
2. **Phase 2 — Repo restructure.** Move Futboleros files under `campaigns/themes/futboleros/`. Rewrite asset paths to `{% theme_static %}`. No view changes yet — the in-repo files are only the source for the default theme directory.
3. **Phase 3 — `setup_default_theme` management command + Dockerfile wiring.** Tests 17, 18.
4. **Phase 4 — Theme upload + admin form + validation.** ThemeAdmin with `.zip` widget + clean() rules. Tests 6-10, 19.
5. **Phase 5 — Asset URL routing (dev) + nginx docs (prod).** Tests 15, 16.
6. **Phase 6 — `theme_static` template tag.** Test 14.
7. **Phase 7 — Three view rewrites + render-from-disk pattern.** Tests 11-13.
8. **Phase 8 — Campaign admin `theme` field in Basics fieldset.** Test 20.
9. **Phase 9 — Authoring docs + operator docs + backup wiring + restore-playbook.**

The implementation plan will break each phase into TDD tasks with explicit commits.

# Trivia Question at Submission Time — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded Futboleros trivia question with a random pick from an operator-managed pool of 10 questions, each with its own illustration image, shared across both Futboleros campaigns (Honduras + Guatemala).

**Architecture:** New `TriviaQuestion` Django model with M2M to `Campaign`. The `submission_form` view injects one randomly picked question into the theme template context. The Futboleros theme's existing 5-step wizard renders the picked question into the existing trivia step; all CTAs throughout the trivia/result steps say "Finalizar". Other themes and campaigns with no trivia questions degrade gracefully.

**Tech Stack:** Django 4.x + SQLite (dev), pytest, Unfold admin, Bootstrap 5 (theme), ImageField uploads under `media/trivia/`, PDF illustration extraction via `pdftoppm` + ImageMagick.

**Spec reference:** `docs/superpowers/specs/2026-05-27-trivia-question-design.md`.

---

## File Structure

**New files:**
- `campaigns/migrations/0017_trivia_question.py` — schema migration for `TriviaQuestion` model + M2M through-table.
- `campaigns/migrations/0018_trivia_question_perms.py` — grants CRUD perms on `TriviaQuestion` to the `Campaign Managers` group.
- `campaigns/migrations/0019_seed_futboleros_trivia.py` — seeds 10 questions + attaches images + assigns to both Futboleros campaigns.
- `campaigns/tests/test_trivia.py` — model, view-context, theme-rendering, admin-scoping, migration-smoke tests.
- `themes/futboleros/assets/trivia/q1.png` … `q10.png` — illustration images extracted from PDF slides 30-37.
- `themes/futboleros/assets/trivia/fallback.png` — generic soccer scene used when a `TriviaQuestion.image` is blank.
- `scripts/extract_trivia_images.sh` — committed helper script that re-derives the 10 illustrations from the PDF (so a future operator can regenerate without remembering the crop coordinates).

**Modified files:**
- `campaigns/models.py` — add `TriviaQuestion` model below `Submission`.
- `campaigns/admin.py` — register `TriviaQuestionAdmin` with its own M2M-aware scoping.
- `campaigns/views.py` — `submission_form` and `submission_form_preview` inject `trivia_question` into the template context.
- `themes/futboleros/submission_form.html` — trivia `<section>` becomes conditional on `{% if trivia_question %}`; prompt + options + image + button copy rewired to model data; JS comparator + form-success guard updated.

---

## Task 1: Extract the 10 illustration images from the PDF

**Files:**
- Create: `scripts/extract_trivia_images.sh`
- Create: `themes/futboleros/assets/trivia/q1.png` … `q10.png`
- Create: `themes/futboleros/assets/trivia/fallback.png`

The PDF source `/home/elgran/Downloads/NUBE BLANCA ROSAL PROMO MUNDIAL.pdf` slides 30-37 each show one trivia question card with an illustration tile inside it. We extract those 8 tiles and reuse 2 of them for the 10 page-38 questions (q1/q3/q6 → USA map; q4/q8 → Obelisco).

- [ ] **Step 1: Write the extraction script**

Create `scripts/extract_trivia_images.sh`:

```bash
#!/usr/bin/env bash
# Re-derive the 10 trivia illustrations from the PDF source.
# Run from repo root: bash scripts/extract_trivia_images.sh
set -euo pipefail

PDF="${PDF:-/home/elgran/Downloads/NUBE BLANCA ROSAL PROMO MUNDIAL.pdf}"
OUT="themes/futboleros/assets/trivia"
TMP="$(mktemp -d)"
trap "rm -rf $TMP" EXIT

mkdir -p "$OUT"

# Render slides 30-37 at 200 DPI. pdftoppm writes "<prefix>-NN.png" with NN
# padded to the page count's width; -f/-l + -singlefile would not work for a
# range, so we render then rename.
pdftoppm -png -r 200 -f 30 -l 37 "$PDF" "$TMP/slide"

# The illustration tile sits inside the white card on the right of each slide.
# At 200 DPI the page is ~2756x1551 px. The tile is roughly:
#   x=2050  y=830  w=460  h=290
# These numbers were measured against slide 30; all 8 slides share the layout.
CROP="460x290+2050+830"
for n in 30 31 32 33 34 35 36 37; do
  convert "$TMP/slide-${n}.png" -crop "$CROP" +repage "$TMP/tile-${n}.png"
done

# Map slide → question number (some slides serve two questions).
# Question→slide mapping is defined in the spec §7.
cp "$TMP/tile-31.png" "$OUT/q1.png"   # USA map
cp "$TMP/tile-30.png" "$OUT/q2.png"   # crowd
cp "$TMP/tile-31.png" "$OUT/q3.png"   # USA map (reused)
cp "$TMP/tile-32.png" "$OUT/q4.png"   # Obelisco BA
cp "$TMP/tile-34.png" "$OUT/q5.png"   # stadium seats
cp "$TMP/tile-31.png" "$OUT/q6.png"   # USA map (reused)
cp "$TMP/tile-35.png" "$OUT/q7.png"   # player + ball
cp "$TMP/tile-32.png" "$OUT/q8.png"   # Obelisco BA (reused)
cp "$TMP/tile-33.png" "$OUT/q9.png"   # Ángel de la Independencia
cp "$TMP/tile-36.png" "$OUT/q10.png"  # team photo

# Fallback: q2 (crowd) is the most generic; reuse it.
cp "$OUT/q2.png" "$OUT/fallback.png"

echo "Wrote $(ls "$OUT" | wc -l) files into $OUT"
```

```bash
chmod +x scripts/extract_trivia_images.sh
```

- [ ] **Step 2: Verify host has `pdftoppm` and `convert`**

Run:
```bash
which pdftoppm convert
```
Expected: both paths print. Install via `sudo apt-get install -y poppler-utils imagemagick` if not.

- [ ] **Step 3: Run the script**

Run from repo root:
```bash
bash scripts/extract_trivia_images.sh
```
Expected: `Wrote 11 files into themes/futboleros/assets/trivia` (q1..q10 plus fallback).

- [ ] **Step 4: Visually spot-check 2–3 tiles**

Run:
```bash
ls -la themes/futboleros/assets/trivia/
file themes/futboleros/assets/trivia/q1.png themes/futboleros/assets/trivia/q5.png
```
Expected: 11 files present, each ~50-200 KB PNG (NOT 0 bytes), `file` reports `PNG image data, 460 x 290`.

If a tile shows just background/whitespace (crop misaligned), open one in an image viewer to confirm the crop rectangle. Adjust `CROP="460x290+2050+830"` in the script and re-run. The crop is only "wrong" if the white card on the right is empty in the result — small misalignments are fine because the tile sits inside a uniformly-coloured area.

- [ ] **Step 5: Commit**

```bash
git add scripts/extract_trivia_images.sh themes/futboleros/assets/trivia/
git commit -m "chore(trivia): extract 10 illustration tiles from PDF source

Adds a reproducible script + the 11 PNGs (q1..q10 + fallback) it
produces. Tiles map to page-38 questions per spec §7; three slide
images are reused across two questions each."
```

---

## Task 2: Add the `TriviaQuestion` model

**Files:**
- Modify: `campaigns/models.py` (append below the existing `Submission` model)
- Create: `campaigns/migrations/0017_trivia_question.py` (generated by `makemigrations`)
- Create: `campaigns/tests/test_trivia.py`

- [ ] **Step 1: Write failing model test**

Create `campaigns/tests/test_trivia.py`:

```python
"""Tests for the TriviaQuestion model + admin + view wiring."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from campaigns.models import Campaign, Domain, TriviaQuestion

User = get_user_model()


def _campaign(slug="c", manager=None):
    domain = Domain.objects.get_or_create(hostname="localhost")[0]
    now = timezone.now()
    c = Campaign.objects.create(
        name=slug.title(),
        slug=slug,
        domain=domain,
        description=f"{slug} desc",
        start_date=now - timedelta(days=1),
        end_date=now + timedelta(days=7),
    )
    if manager:
        c.managers.add(manager)
    return c


class TriviaQuestionModelTests(TestCase):
    def test_defaults(self):
        q = TriviaQuestion.objects.create(
            text="Q?",
            option_a="A", option_b="B", option_c="C",
            correct="a",
        )
        self.assertTrue(q.is_active)
        self.assertEqual(q.display_order, 0)
        self.assertEqual(q.campaigns.count(), 0)
        self.assertEqual(q.image_alt, "")

    def test_str_truncates_long_text(self):
        long = "x" * 200
        q = TriviaQuestion.objects.create(
            text=long, option_a="A", option_b="B", option_c="C", correct="a",
        )
        self.assertLessEqual(len(str(q)), 80)

    def test_correct_choice_validates(self):
        q = TriviaQuestion(
            text="Q?", option_a="A", option_b="B", option_c="C", correct="z",
        )
        with self.assertRaises(ValidationError):
            q.full_clean()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker exec raffle-web pytest campaigns/tests/test_trivia.py -v
```
Expected: ImportError on `TriviaQuestion` (model doesn't exist yet).

- [ ] **Step 3: Add the model**

Append to `campaigns/models.py` (after the existing `Submission` model, before `Raffle` if alphabetical, otherwise at end):

```python
class TriviaQuestion(models.Model):
    CORRECT_CHOICES = [("a", "A"), ("b", "B"), ("c", "C")]

    text = models.CharField(max_length=300)
    image = models.ImageField(upload_to="trivia/", blank=True, null=True)
    image_alt = models.CharField(max_length=200, blank=True, default="")
    option_a = models.CharField(max_length=120)
    option_b = models.CharField(max_length=120)
    option_c = models.CharField(max_length=120)
    correct = models.CharField(max_length=1, choices=CORRECT_CHOICES)
    campaigns = models.ManyToManyField(
        "Campaign", related_name="trivia_questions", blank=True,
    )
    is_active = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("display_order", "id")

    def __str__(self):
        return (self.text[:77] + "...") if len(self.text) > 80 else self.text
```

- [ ] **Step 4: Generate migration**

```bash
docker exec raffle-web python manage.py makemigrations campaigns -n trivia_question
```
Expected: creates `campaigns/migrations/0017_trivia_question.py` with `CreateModel("TriviaQuestion", ...)`.

If the generated number is not `0017` (e.g., merge migrations or someone else added one), rename the file and update its `dependencies` to match.

- [ ] **Step 5: Apply migration + run tests**

```bash
docker exec raffle-web python manage.py migrate
docker exec raffle-web pytest campaigns/tests/test_trivia.py -v
```
Expected: 3 tests pass.

- [ ] **Step 6: Commit**

```bash
git add campaigns/models.py campaigns/migrations/0017_trivia_question.py campaigns/tests/test_trivia.py
git commit -m "feat(trivia): add TriviaQuestion model

text + image + 3 options + correct choice + M2M campaigns. Defaults:
is_active=True, display_order=0, no campaigns. Validated against
spec §4."
```

---

## Task 3: Grant CRUD perms on `TriviaQuestion` to the `Campaign Managers` group

**Files:**
- Create: `campaigns/migrations/0018_trivia_question_perms.py`
- Modify: `campaigns/tests/test_trivia.py` (append new test class)

- [ ] **Step 1: Add failing test**

Append to `campaigns/tests/test_trivia.py`:

```python
from django.contrib.auth.models import Group, Permission


class CampaignManagersGroupTriviaPermsTests(TestCase):
    def test_group_has_full_crud_on_trivia_question(self):
        grp = Group.objects.get(name="Campaign Managers")
        codes = set(grp.permissions.values_list("codename", flat=True))
        for action in ("view", "add", "change", "delete"):
            self.assertIn(f"{action}_triviaquestion", codes)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker exec raffle-web pytest campaigns/tests/test_trivia.py::CampaignManagersGroupTriviaPermsTests -v
```
Expected: AssertionError — perms not in the group.

- [ ] **Step 3: Write the migration**

Create `campaigns/migrations/0018_trivia_question_perms.py`:

```python
"""Grant CRUD perms on TriviaQuestion to the 'Campaign Managers' group.

Mirrors the pattern from 0005_create_campaign_managers_group.py and
0011_add_domain_perms_to_campaign_managers_group.py: call
`create_permissions` defensively because the post_migrate signal that
normally creates Permission rows for new models has not fired during
data-migration execution.
"""

from django.db import migrations


def grant_perms(apps, schema_editor):
    from django.contrib.auth.management import create_permissions

    # Force-create Permission rows for the campaigns app (post_migrate hasn't fired).
    app_config = apps.get_app_config("campaigns")
    app_config.models_module = True  # required by create_permissions in migration context
    create_permissions(app_config, apps=apps, verbosity=0)

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    try:
        grp = Group.objects.get(name="Campaign Managers")
    except Group.DoesNotExist:
        return

    ct = ContentType.objects.get(app_label="campaigns", model="triviaquestion")
    for action in ("view", "add", "change", "delete"):
        perm = Permission.objects.get(content_type=ct, codename=f"{action}_triviaquestion")
        grp.permissions.add(perm)


def revoke_perms(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    try:
        grp = Group.objects.get(name="Campaign Managers")
        ct = ContentType.objects.get(app_label="campaigns", model="triviaquestion")
    except (Group.DoesNotExist, ContentType.DoesNotExist):
        return

    for action in ("view", "add", "change", "delete"):
        try:
            perm = Permission.objects.get(content_type=ct, codename=f"{action}_triviaquestion")
            grp.permissions.remove(perm)
        except Permission.DoesNotExist:
            pass


class Migration(migrations.Migration):
    dependencies = [
        ("campaigns", "0017_trivia_question"),
    ]
    operations = [
        migrations.RunPython(grant_perms, reverse_code=revoke_perms),
    ]
```

- [ ] **Step 4: Apply migration + run test**

```bash
docker exec raffle-web python manage.py migrate
docker exec raffle-web pytest campaigns/tests/test_trivia.py::CampaignManagersGroupTriviaPermsTests -v
```
Expected: PASS.

- [ ] **Step 5: Run the whole trivia test file to confirm no regressions**

```bash
docker exec raffle-web pytest campaigns/tests/test_trivia.py -v
```
Expected: 4 tests pass.

- [ ] **Step 6: Commit**

```bash
git add campaigns/migrations/0018_trivia_question_perms.py campaigns/tests/test_trivia.py
git commit -m "feat(trivia): grant TriviaQuestion CRUD to Campaign Managers group"
```

---

## Task 4: Register `TriviaQuestionAdmin` with M2M-aware scoping

**Files:**
- Modify: `campaigns/admin.py` (add new admin class + register; add `TriviaQuestion` to the imports)
- Modify: `campaigns/tests/test_trivia.py` (append admin tests)

The existing `CampaignScopedAdminMixin` uses an FK lookup (`_campaign_field = 'campaign'`). `TriviaQuestion` uses an M2M (`campaigns`), so we write our own `get_queryset` / `has_change_permission` / `has_delete_permission` directly using `_user_managed_campaign_ids`. This is intentionally NOT a generalisation of the mixin — only TriviaQuestion needs M2M scoping today.

- [ ] **Step 1: Write failing admin tests**

Append to `campaigns/tests/test_trivia.py`:

```python
from django.contrib.admin.sites import site as admin_site


class TriviaQuestionAdminScopingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.mgr_hn = User.objects.create_user(
            username="mgr_hn", password="x", is_staff=True,
        )
        cls.mgr_gt = User.objects.create_user(
            username="mgr_gt", password="x", is_staff=True,
        )
        cls.superuser = User.objects.create_superuser(
            username="root", password="x",
        )
        cls.hn = _campaign(slug="hn", manager=cls.mgr_hn)
        cls.gt = _campaign(slug="gt", manager=cls.mgr_gt)
        cls.q_hn = TriviaQuestion.objects.create(
            text="HN only", option_a="A", option_b="B", option_c="C", correct="a",
        )
        cls.q_hn.campaigns.add(cls.hn)
        cls.q_gt = TriviaQuestion.objects.create(
            text="GT only", option_a="A", option_b="B", option_c="C", correct="b",
        )
        cls.q_gt.campaigns.add(cls.gt)
        cls.q_both = TriviaQuestion.objects.create(
            text="Both", option_a="A", option_b="B", option_c="C", correct="c",
        )
        cls.q_both.campaigns.add(cls.hn, cls.gt)

    def _admin(self):
        return admin_site._registry[TriviaQuestion]

    def _request(self, user):
        from django.test import RequestFactory
        rf = RequestFactory()
        req = rf.get("/admin/campaigns/triviaquestion/")
        req.user = user
        return req

    def test_hn_manager_sees_hn_and_both(self):
        qs = self._admin().get_queryset(self._request(self.mgr_hn))
        ids = set(qs.values_list("id", flat=True))
        self.assertEqual(ids, {self.q_hn.id, self.q_both.id})

    def test_gt_manager_sees_gt_and_both(self):
        qs = self._admin().get_queryset(self._request(self.mgr_gt))
        ids = set(qs.values_list("id", flat=True))
        self.assertEqual(ids, {self.q_gt.id, self.q_both.id})

    def test_superuser_sees_all(self):
        qs = self._admin().get_queryset(self._request(self.superuser))
        ids = set(qs.values_list("id", flat=True))
        self.assertEqual(ids, {self.q_hn.id, self.q_gt.id, self.q_both.id})

    def test_hn_manager_cannot_change_gt_only_question(self):
        admin = self._admin()
        req = self._request(self.mgr_hn)
        self.assertFalse(admin.has_change_permission(req, obj=self.q_gt))
        self.assertTrue(admin.has_change_permission(req, obj=self.q_hn))
        self.assertTrue(admin.has_change_permission(req, obj=self.q_both))

    def test_hn_manager_cannot_delete_gt_only_question(self):
        admin = self._admin()
        req = self._request(self.mgr_hn)
        self.assertFalse(admin.has_delete_permission(req, obj=self.q_gt))
        self.assertTrue(admin.has_delete_permission(req, obj=self.q_hn))
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker exec raffle-web pytest campaigns/tests/test_trivia.py::TriviaQuestionAdminScopingTests -v
```
Expected: KeyError on `admin_site._registry[TriviaQuestion]` — admin not registered yet.

- [ ] **Step 3: Register the admin**

In `campaigns/admin.py`:

a) Add `TriviaQuestion` to the model imports (line ~11):

```python
from .models import Campaign, Domain, Prize, SubmissionCode, Submission, Raffle, RaffleWinner, Store, Theme, TriviaQuestion
```

b) Append a new admin class at the end of the file (after `RaffleWinnerAdmin`):

```python
@admin.register(TriviaQuestion)
class TriviaQuestionAdmin(ModelAdmin):
    """Admin for the trivia question bank.

    Not using `CampaignScopedAdminMixin` because that mixin assumes an FK
    to Campaign; TriviaQuestion uses an M2M. We re-implement the three
    scoping methods directly against `_user_managed_campaign_ids`.
    """

    list_display = ("text_short", "correct_display", "image_thumb", "campaign_count", "is_active", "display_order")
    list_filter = ("is_active", "campaigns")
    search_fields = ("text", "option_a", "option_b", "option_c")
    filter_horizontal = ("campaigns",)
    ordering = ("display_order", "id")
    fieldsets = (
        ("Question", {"fields": ("text", "image", "image_alt", "is_active", "display_order")}),
        ("Options", {"fields": ("option_a", "option_b", "option_c", "correct")}),
        ("Assignment", {"fields": ("campaigns",)}),
    )

    def text_short(self, obj):
        return (obj.text[:60] + "...") if len(obj.text) > 60 else obj.text
    text_short.short_description = "Question"

    def correct_display(self, obj):
        return f"{obj.correct.upper()}: {getattr(obj, f'option_{obj.correct}')}"
    correct_display.short_description = "Correct answer"

    def image_thumb(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="height:36px; border-radius:6px; object-fit:cover;" />',
                obj.image.url,
            )
        return "—"
    image_thumb.short_description = "Image"

    def campaign_count(self, obj):
        return obj.campaigns.count()
    campaign_count.short_description = "Campaigns"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        ids = _user_managed_campaign_ids(request)
        if ids is None:
            return qs
        return qs.filter(campaigns__id__in=ids).distinct()

    def has_change_permission(self, request, obj=None):
        if obj is None or request.user.is_superuser:
            return super().has_change_permission(request, obj)
        ids = _user_managed_campaign_ids(request)
        return obj.campaigns.filter(id__in=ids).exists()

    def has_delete_permission(self, request, obj=None):
        if obj is None or request.user.is_superuser:
            return super().has_delete_permission(request, obj)
        ids = _user_managed_campaign_ids(request)
        return obj.campaigns.filter(id__in=ids).exists()
```

- [ ] **Step 4: Run tests to verify pass**

```bash
docker exec raffle-web pytest campaigns/tests/test_trivia.py::TriviaQuestionAdminScopingTests -v
```
Expected: 5 tests pass.

- [ ] **Step 5: Smoke-check Django admin loads**

```bash
docker exec raffle-web python manage.py check
```
Expected: no errors. (Migration warning W001 about ALLOWED_HOSTS is unrelated.)

- [ ] **Step 6: Commit**

```bash
git add campaigns/admin.py campaigns/tests/test_trivia.py
git commit -m "feat(trivia): register TriviaQuestionAdmin with M2M scoping

Custom get_queryset/has_change_permission/has_delete_permission instead
of CampaignScopedAdminMixin (which assumes an FK to Campaign)."
```

---

## Task 5: Inject `trivia_question` into the submission-form view context

**Files:**
- Modify: `campaigns/views.py` (lines 73-100 and 108-120)
- Modify: `campaigns/tests/test_trivia.py` (append view tests)

- [ ] **Step 1: Write failing view tests**

Append to `campaigns/tests/test_trivia.py`:

```python
from django.urls import reverse


class TriviaQuestionViewContextTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.hn = _campaign(slug="hn-view")
        cls.gt = _campaign(slug="gt-view")
        cls.q_hn = TriviaQuestion.objects.create(
            text="HN Q1", option_a="A", option_b="B", option_c="C", correct="a",
        )
        cls.q_hn.campaigns.add(cls.hn)
        cls.q_hn_inactive = TriviaQuestion.objects.create(
            text="HN inactive", option_a="A", option_b="B", option_c="C",
            correct="a", is_active=False,
        )
        cls.q_hn_inactive.campaigns.add(cls.hn)
        cls.q_gt = TriviaQuestion.objects.create(
            text="GT Q1", option_a="A", option_b="B", option_c="C", correct="b",
        )
        cls.q_gt.campaigns.add(cls.gt)

    def test_view_injects_trivia_question_for_campaign_with_active_question(self):
        resp = self.client.get(
            reverse("submission_form", args=[self.hn.slug]), HTTP_HOST="localhost",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["trivia_question"], self.q_hn)

    def test_view_does_not_pick_inactive_questions(self):
        # The HN campaign has q_hn (active) and q_hn_inactive (inactive).
        # Repeatedly hit the endpoint; we must never see the inactive one.
        for _ in range(8):
            resp = self.client.get(
                reverse("submission_form", args=[self.hn.slug]), HTTP_HOST="localhost",
            )
            self.assertNotEqual(resp.context["trivia_question"], self.q_hn_inactive)

    def test_view_does_not_pick_questions_assigned_to_other_campaigns(self):
        for _ in range(8):
            resp = self.client.get(
                reverse("submission_form", args=[self.hn.slug]), HTTP_HOST="localhost",
            )
            self.assertNotEqual(resp.context["trivia_question"], self.q_gt)

    def test_view_injects_none_when_campaign_has_no_questions(self):
        empty = _campaign(slug="empty-view")
        resp = self.client.get(
            reverse("submission_form", args=[empty.slug]), HTTP_HOST="localhost",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.context["trivia_question"])

    def test_preview_view_also_injects_trivia_question(self):
        resp = self.client.get(
            reverse("submission_form_preview", args=[self.hn.slug, "a"]),
            HTTP_HOST="localhost",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["trivia_question"], self.q_hn)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker exec raffle-web pytest campaigns/tests/test_trivia.py::TriviaQuestionViewContextTests -v
```
Expected: KeyError on `resp.context["trivia_question"]` (key not set).

- [ ] **Step 3: Add a helper to `campaigns/views.py`**

Just above `def submission_form(request, campaign_slug):` (around line 73), add:

```python
def _pick_trivia_question(campaign):
    """Return one random active TriviaQuestion assigned to this campaign, or None."""
    from .models import TriviaQuestion
    return (
        TriviaQuestion.objects
        .filter(campaigns=campaign, is_active=True)
        .order_by("?")
        .first()
    )
```

- [ ] **Step 4: Inject into both view contexts**

In `submission_form` (around lines 95-100), change the context dict from:

```python
    return _render_theme_template(request, campaign, "submission_form.html", {
        "campaign": campaign,
        "form": form,
        "form_fields": FormCls.Meta.field_specs,
        "campaign_open": campaign_open,
    })
```

to:

```python
    return _render_theme_template(request, campaign, "submission_form.html", {
        "campaign": campaign,
        "form": form,
        "form_fields": FormCls.Meta.field_specs,
        "campaign_open": campaign_open,
        "trivia_question": _pick_trivia_question(campaign),
    })
```

In `submission_form_preview` (around lines 115-120), make the same context addition:

```python
    return _render_theme_template(request, campaign, "submission_form.html", {
        "campaign": campaign,
        "form": form,
        "form_fields": FormCls.Meta.field_specs,
        "campaign_open": True,
        "trivia_question": _pick_trivia_question(campaign),
    })
```

- [ ] **Step 5: Run view tests to verify pass**

```bash
docker exec raffle-web pytest campaigns/tests/test_trivia.py::TriviaQuestionViewContextTests -v
```
Expected: 5 tests pass.

- [ ] **Step 6: Run the whole trivia file**

```bash
docker exec raffle-web pytest campaigns/tests/test_trivia.py -v
```
Expected: all tests pass (model + perms + admin + view).

- [ ] **Step 7: Commit**

```bash
git add campaigns/views.py campaigns/tests/test_trivia.py
git commit -m "feat(trivia): inject random TriviaQuestion into submission view context

submission_form + submission_form_preview now pass trivia_question (one
random active question assigned to the campaign, or None). Themes that
don't render it are unaffected."
```

---

## Task 6: Update the Futboleros theme template

**Files:**
- Modify: `themes/futboleros/submission_form.html` (trivia section, JS guess handler, form-success guard, CSS)
- Modify: `campaigns/tests/test_trivia.py` (append rendering tests)

- [ ] **Step 1: Write failing rendering tests**

Append to `campaigns/tests/test_trivia.py`:

```python
class TriviaQuestionThemeRenderingTests(TestCase):
    """Verifies the Futboleros theme renders the trivia step correctly.

    These tests render the actual themes/futboleros/submission_form.html
    via the view; assertions look at the response body.
    """

    @classmethod
    def setUpTestData(cls):
        cls.campaign = _campaign(slug="render-test")
        # Force the futboleros theme on this campaign.
        from campaigns.models import Theme
        theme, _ = Theme.objects.get_or_create(
            slug="futboleros", defaults={"name": "Futboleros"},
        )
        cls.campaign.theme = theme
        cls.campaign.save()
        cls.question = TriviaQuestion.objects.create(
            text="¿Cuál es la capital de Honduras?",
            option_a="San Pedro Sula",
            option_b="Tegucigalpa",
            option_c="La Ceiba",
            correct="b",
        )
        cls.question.campaigns.add(cls.campaign)

    def _get(self):
        return self.client.get(
            reverse("submission_form", args=[self.campaign.slug]),
            HTTP_HOST="localhost",
        )

    def test_renders_trivia_section_when_question_present(self):
        body = self._get().content.decode()
        self.assertIn('data-step="trivia"', body)
        self.assertIn("¿Cuál es la capital de Honduras?", body)
        self.assertIn("Tegucigalpa", body)

    def test_omits_trivia_section_when_no_question(self):
        empty = _campaign(slug="render-empty")
        from campaigns.models import Theme
        empty.theme = Theme.objects.get(slug="futboleros")
        empty.save()
        body = self.client.get(
            reverse("submission_form", args=[empty.slug]),
            HTTP_HOST="localhost",
        ).content.decode()
        self.assertNotIn('data-step="trivia"', body)

    def test_radio_values_are_letters(self):
        body = self._get().content.decode()
        self.assertIn('name="trivia" value="a"', body)
        self.assertIn('name="trivia" value="b"', body)
        self.assertIn('name="trivia" value="c"', body)
        self.assertNotIn('name="trivia" value="0"', body)

    def test_js_comparator_uses_correct_letter(self):
        body = self._get().content.decode()
        # correct=b for this question
        self.assertIn("picked.value === 'b'", body)

    def test_cta_says_finalizar_not_adivinar(self):
        body = self._get().content.decode()
        self.assertIn("FINALIZAR", body)
        self.assertNotIn("ADIVINAR", body)
        self.assertNotIn("SIGUIENTE", body)

    def test_image_falls_back_when_blank(self):
        # The seeded question has no image — the template's else branch
        # should reference the static fallback path.
        body = self._get().content.decode()
        self.assertIn("trivia/fallback.png", body)

    def test_nube_blanca_logo_is_present_in_response(self):
        # The brand-logo <img> sits outside the step sections; it must be
        # in the response regardless of which step is the active one.
        body = self._get().content.decode()
        self.assertIn("logo_nube.png", body)
        self.assertIn('class="brand-logo"', body)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker exec raffle-web pytest campaigns/tests/test_trivia.py::TriviaQuestionThemeRenderingTests -v
```
Expected: several fail. The hardcoded prompt text still renders; `value="0|1|2"` is still in the template; `ADIVINAR` still appears; `fallback.png` doesn't appear; JS comparator is `picked.value === '2'`.

- [ ] **Step 3: Update the trivia section in the template**

Open `themes/futboleros/submission_form.html`. Around line 611-645, replace the entire `<!-- Step 3: Trivia -->` section with:

```html
  <!-- Step 3: Trivia -->
  {% if trivia_question %}
  <section class="step" data-step="trivia">
    <h1 class="pill-heading">¡YA ESTÁS JUGANDO!</h1>

    <div class="card">
      <p class="trivia-question">
        Escoge la respuesta correcta de estas tres opciones y<br>
        te diremos el nivel de pasión futbolera que tienes:
      </p>

      <p class="trivia-prompt">{{ trivia_question.text }}</p>

      <div class="options">
        <label class="option">
          <input type="radio" name="trivia" value="a">
          <span class="dot" aria-hidden="true"></span>
          <span>{{ trivia_question.option_a }}</span>
        </label>
        <label class="option">
          <input type="radio" name="trivia" value="b">
          <span class="dot" aria-hidden="true"></span>
          <span>{{ trivia_question.option_b }}</span>
        </label>
        <label class="option">
          <input type="radio" name="trivia" value="c">
          <span class="dot" aria-hidden="true"></span>
          <span>{{ trivia_question.option_c }}</span>
        </label>
      </div>

      <img class="trivia-illustration"
           src="{% if trivia_question.image %}{{ trivia_question.image.url }}{% else %}{% theme_static 'trivia/fallback.png' %}{% endif %}"
           alt="{{ trivia_question.image_alt|default:trivia_question.text }}">

      <div class="center-actions">
        <button type="button" class="btn btn-wide" id="guessBtn" disabled>FINALIZAR</button>
      </div>
    </div>
  </section>
  {% endif %}
```

- [ ] **Step 4: Add `.trivia-illustration` CSS rule**

In the same file, inside the `<style>` block. Find the block starting `/* === Card used on form / trivia / result screens === */` (around line 285) and locate the existing rules `.trivia-question` and `.trivia-prompt` (lines ~458-465). Just below them, add:

```css
    .trivia-illustration {
      display: block;
      margin: 12px auto 18px;
      max-width: 240px;
      max-height: 140px;
      width: 100%;
      border-radius: 14px;
      object-fit: cover;
    }
```

- [ ] **Step 4b: Fix the Nube Blanca logo position to match the AI/PDF source**

Source of truth: `~/Downloads/Landing_Carpeta 0(1)/Landing_Carpeta 0/Landing.ai` and PDF slides 30-37. The logo should be visible on top on mobile (currently hidden on the trivia step) and top-RIGHT on desktop (currently top-LEFT).

In `themes/futboleros/submission_form.html`:

a) Mobile: remove the `[data-step="trivia"]` selector from the mobile hide-rule. Around line 187-191, change:

```css
    /* Mobile: hide on the form + trivia steps (only show on welcome/success/fail) */
    .stage[data-step="form"] .brand-logo,
    .stage[data-step="trivia"] .brand-logo {
      display: none;
    }
```

to:

```css
    /* Mobile: hide on the form step only. Welcome/trivia/success/fail show the logo on top. */
    .stage[data-step="form"] .brand-logo {
      display: none;
    }
```

b) Desktop: move the fixed logo from the top-left to the top-right. Around line 121-135, change:

```css
      /* Desktop: logo ALWAYS visible at top-left of viewport on every step.
         position: fixed bypasses ancestor positioning chain. !important
         overrides the mobile hide rules for form/trivia. */
      .brand-logo,
      .stage[data-step="form"] .brand-logo,
      .stage[data-step="trivia"] .brand-logo {
        display: block !important;
        position: fixed;
        top: clamp(24px, 5vh, 80px);
        left: clamp(24px, 4vw, 96px);
        margin: 0 !important;
        width: auto;
        max-width: min(28vw, 360px);
        z-index: 50;
      }
```

to:

```css
      /* Desktop: logo ALWAYS visible at top-RIGHT of viewport on every step,
         matching the AI/PDF source. position: fixed bypasses ancestor
         positioning chain. !important overrides the mobile hide rule for form. */
      .brand-logo,
      .stage[data-step="form"] .brand-logo,
      .stage[data-step="trivia"] .brand-logo {
        display: block !important;
        position: fixed;
        top: clamp(24px, 5vh, 80px);
        right: clamp(24px, 4vw, 96px);
        left: auto;
        margin: 0 !important;
        width: auto;
        max-width: min(28vw, 360px);
        z-index: 50;
      }
```

No HTML changes — the `<img class="brand-logo">` element already exists at the top of `#stage` and is unaffected by these rule changes.

- [ ] **Step 5: Update the JS — guess comparator + form-success guard**

In the same file, find the form-success branch in the form submit handler (around lines 781-785). Replace:

```js
          if (res.ok && res.url && res.url.includes('/success/')) {
            go('trivia');
            return;
          }
```

with:

```js
          if (res.ok && res.url && res.url.includes('/success/')) {
            if (stage.querySelector('.step[data-step="trivia"]')) {
              go('trivia');
            } else {
              window.location.href = res.url;
            }
            return;
          }
```

Then find the trivia guess handler (around lines 815-819). Replace:

```js
      guessBtn.addEventListener('click', () => {
        const picked = document.querySelector('input[name="trivia"]:checked');
        if (!picked) return;
        go(picked.value === '2' ? 'success' : 'fail');
      });
```

with:

```js
      guessBtn.addEventListener('click', () => {
        const picked = document.querySelector('input[name="trivia"]:checked');
        if (!picked) return;
        go(picked.value === '{{ trivia_question.correct }}' ? 'success' : 'fail');
      });
```

Note: the template-injected `{{ trivia_question.correct }}` only renders inside the `{% if trivia_question %}` block — but the guess handler is OUTSIDE that block, in the page's main `<script>`. The Django template engine still expands `{{ }}` because the whole HTML is rendered as a template. If `trivia_question` is None, the expansion yields an empty string and the comparison `picked.value === ''` always evaluates false → trivia would land on `fail`. That's fine because when `trivia_question` is None, the trivia `<section>` doesn't exist in the DOM so `guessBtn` is null and the `if (guessBtn)` outer guard short-circuits — the handler is never wired.

- [ ] **Step 6: Run rendering tests to verify pass**

```bash
docker exec raffle-web pytest campaigns/tests/test_trivia.py::TriviaQuestionThemeRenderingTests -v
```
Expected: 6 tests pass.

- [ ] **Step 7: Run the whole trivia test file**

```bash
docker exec raffle-web pytest campaigns/tests/test_trivia.py -v
```
Expected: all tests pass.

- [ ] **Step 8: Run the full test suite to confirm no regressions in other themes / flows**

```bash
docker exec raffle-web pytest -x
```
Expected: all green. If a test in `test_submission_form_redesign.py` or `test_themes.py` fails because the old hardcoded trivia text disappeared, update those tests to assert against the new conditional rendering instead.

- [ ] **Step 9: Commit**

```bash
git add themes/futboleros/submission_form.html campaigns/tests/test_trivia.py
git commit -m "feat(trivia): wire Futboleros theme to dynamic question

Trivia section conditional on trivia_question context var. Radio
values become a/b/c letters; CTA renamed FINALIZAR; new illustration
<img> with static fallback; JS guess comparator uses the correct
letter from the template; form-success branch guards go('trivia')
against a missing section."
```

---

## Task 7: Seed the 10 page-38 questions + assign to both Futboleros campaigns

**Files:**
- Create: `campaigns/migrations/0019_seed_futboleros_trivia.py`
- Modify: `campaigns/tests/test_trivia.py` (append seed smoke tests)

- [ ] **Step 1: Write failing smoke test**

Append to `campaigns/tests/test_trivia.py`:

```python
class FutbolerosSeedTests(TestCase):
    """Smoke: the data migration seeded 10 questions on both Futboleros campaigns.

    The migration is allowed to be a no-op if the Futboleros campaigns aren't
    present (e.g., a fresh dev DB before seed_demo_proposals runs). If they
    are present, these assertions hold.
    """

    def test_both_campaigns_have_ten_active_questions(self):
        for slug in ("futboleros-bn-hn", "futboleros-bn-gt"):
            try:
                c = Campaign.objects.get(slug=slug)
            except Campaign.DoesNotExist:
                self.skipTest(f"Campaign {slug} not present in this DB")
            count = c.trivia_questions.filter(is_active=True).count()
            self.assertEqual(count, 10, f"{slug} has {count} trivia questions")

    def test_every_seeded_question_has_image(self):
        try:
            hn = Campaign.objects.get(slug="futboleros-bn-hn")
        except Campaign.DoesNotExist:
            self.skipTest("futboleros-bn-hn not present")
        for q in hn.trivia_questions.all():
            self.assertTrue(q.image and q.image.name, f"{q} has no image")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker exec raffle-web pytest campaigns/tests/test_trivia.py::FutbolerosSeedTests -v
```
Expected: failure (campaigns exist in dev DB but have 0 questions assigned).

- [ ] **Step 3: Write the seed migration**

Create `campaigns/migrations/0019_seed_futboleros_trivia.py`:

```python
"""Seed the 10 page-38 World Cup trivia questions for both Futboleros campaigns.

Idempotent: re-running has no effect (get_or_create on text). Reverse migration
only removes the seeded rows by their exact text (operator-added rows are
preserved). Skips silently if either Futboleros campaign is absent.

Image attachments are read from themes/futboleros/assets/trivia/q{n}.png and
saved into the ImageField's MEDIA_ROOT location at migration time.
"""

from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.db import migrations


QUESTIONS = [
    # (n, text, a, b, c, correct)
    (1, "¿En qué países se disputará el Mundial 2026?",
     "España, Portugal y Marruecos", "Estados Unidos, México y Canadá",
     "Brasil, Argentina y Uruguay", "b"),
    (2, "¿Cuántos equipos participarán por primera vez en el Mundial 2026?",
     "32 equipos", "48 equipos", "40 equipos", "b"),
    (3, "¿Qué país organizará la final del Mundial 2026?",
     "México", "Canadá", "Estados Unidos", "c"),
    (4, "¿Cuál de estas ciudades NO será sede del Mundial 2026?",
     "Ciudad de México", "Los Ángeles", "Buenos Aires", "c"),
    (5, "¿Qué estadio albergará la final del Mundial 2026?",
     "Estadio Azteca", "MetLife Stadium", "Rose Bowl", "b"),
    (6, "¿Cuál de estos países es coanfitrión del Mundial 2026 junto a Estados Unidos y México?",
     "Canadá", "Costa Rica", "Panamá", "a"),
    (7, "¿En qué año se celebrará el próximo Mundial de la FIFA?",
     "2025", "2026", "2027", "b"),
    (8, "¿Qué selección es la actual campeona del mundo (2022) y participará en el Mundial 2026?",
     "Brasil", "Francia", "Argentina", "c"),
    (9, "¿Qué estadio mexicano será sede del Mundial 2026?",
     "Estadio Jalisco", "Estadio Azteca", "Estadio Universitario", "b"),
    (10, "¿Cuántos países anfitriones tienen cupo automático para el Mundial 2026?",
     "1", "2", "3", "c"),
]

CAMPAIGN_SLUGS = ("futboleros-bn-hn", "futboleros-bn-gt")


def _image_path(n):
    # settings.BASE_DIR points at the repo root in this project.
    return Path(settings.BASE_DIR) / "themes" / "futboleros" / "assets" / "trivia" / f"q{n}.png"


def seed(apps, schema_editor):
    TriviaQuestion = apps.get_model("campaigns", "TriviaQuestion")
    Campaign = apps.get_model("campaigns", "Campaign")

    campaigns = list(Campaign.objects.filter(slug__in=CAMPAIGN_SLUGS))
    if not campaigns:
        return  # nothing to seed onto

    for n, text, a, b, c, correct in QUESTIONS:
        q, created = TriviaQuestion.objects.get_or_create(
            text=text,
            defaults={
                "option_a": a, "option_b": b, "option_c": c,
                "correct": correct, "display_order": n, "is_active": True,
            },
        )
        # Attach image (always, even if row pre-existed, in case file was missing).
        path = _image_path(n)
        if path.exists() and not q.image:
            with path.open("rb") as fh:
                q.image.save(f"q{n}.png", File(fh), save=True)
        # Assign to both Futboleros campaigns (idempotent via M2M .add).
        for camp in campaigns:
            q.campaigns.add(camp)


def unseed(apps, schema_editor):
    TriviaQuestion = apps.get_model("campaigns", "TriviaQuestion")
    texts = [text for (_, text, *_rest) in QUESTIONS]
    TriviaQuestion.objects.filter(text__in=texts).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("campaigns", "0018_trivia_question_perms"),
    ]
    operations = [
        migrations.RunPython(seed, reverse_code=unseed),
    ]
```

- [ ] **Step 4: Apply migration**

```bash
docker exec raffle-web python manage.py migrate
```
Expected: `0019_seed_futboleros_trivia... OK`. No tracebacks.

- [ ] **Step 5: Confirm via shell**

```bash
docker exec raffle-web python manage.py shell -c "
from campaigns.models import Campaign
for slug in ('futboleros-bn-hn', 'futboleros-bn-gt'):
    c = Campaign.objects.get(slug=slug)
    qs = list(c.trivia_questions.values_list('id', 'text', 'image'))
    print(slug, 'count=', len(qs))
    for row in qs:
        print(' ', row)
"
```
Expected: each campaign prints `count= 10` and ten rows, all with non-empty `image` paths under `trivia/q{n}.png`.

- [ ] **Step 6: Run smoke tests**

```bash
docker exec raffle-web pytest campaigns/tests/test_trivia.py::FutbolerosSeedTests -v
```
Expected: 2 tests pass.

- [ ] **Step 7: Run full test suite**

```bash
docker exec raffle-web pytest -x
```
Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add campaigns/migrations/0019_seed_futboleros_trivia.py campaigns/tests/test_trivia.py
git commit -m "feat(trivia): seed 10 page-38 questions onto both Futboleros campaigns

Data migration: get_or_create on text (idempotent), attaches each
question's illustration from themes/futboleros/assets/trivia/q{n}.png,
assigns to futboleros-bn-hn + futboleros-bn-gt. Reverse migration only
removes rows whose text matches the seeded set (operator-added
questions are preserved)."
```

---

## Task 8: End-to-end manual verification

**Files:** none (in-browser smoke).

- [ ] **Step 1: Ensure app is running**

```bash
RAFFLE_CAMPAIGN_WEB_PORT=8500 docker compose up -d
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8500/dashboard/login/
```
Expected: `200`.

- [ ] **Step 2: Hit each campaign 8+ times, sanity-check random distribution**

```bash
for i in $(seq 1 16); do
  curl -s http://localhost:8500/submit/futboleros-bn-hn/ | grep -oE 'class="trivia-prompt">[^<]+' | head -1
done | sort | uniq -c | sort -rn
```
Expected: most of the 10 questions appear at least once across 16 hits; no single question dominates absurdly. (Statistical roughness is fine — `?` ordering is non-uniform but adequate.)

Repeat for `futboleros-bn-gt` — same shape.

- [ ] **Step 3: Walk the full flow in a browser**

Visit `http://localhost:8500/submit/futboleros-bn-gt/`, then:
1. Click EMPEZAR → form appears.
2. Fill the form with valid data (use a unique email/code).
3. Click ENVIAR → trivia step appears with one of the 10 questions and its illustration image.
4. Confirm the CTA button reads **FINALIZAR**, not ADIVINAR / SIGUIENTE.
5. Pick the correct option (use the spec §7 table) → reveal screen shows `¡Eres un crack!` titular.
6. Click FINALIZAR → page reloads to welcome.
7. Repeat with a wrong option → reveal screen shows `¡Fallaste!` titular. Click FINALIZAR → welcome.

- [ ] **Step 4: Deep-link the trivia step for screenshot QA**

Visit `http://localhost:8500/submit/futboleros-bn-hn/?step=trivia`. Confirm:
- A page-38 question renders with its image.
- Three options labeled with the question's `option_a/b/c` text (not generic Lorem).
- Button says FINALIZAR.
- **Mobile** (DevTools narrow viewport, e.g. 390px): the Nube Blanca logo (red wordmark) appears at the top of the trivia card area.
- **Desktop** (viewport ≥ 768px): the Nube Blanca logo sits in the **top-right** corner of the viewport (not top-left). It stays visible on all 5 steps.

- [ ] **Step 5: Confirm Theme-Smoke (non-Futboleros) campaign still works**

Visit `http://localhost:8500/submit/theme-smoke/` (this campaign uses the default theme, not Futboleros — should be unaffected). Expected: page renders normally, no JS errors in console, no reference to trivia in the response body.

- [ ] **Step 6: Confirm admin works**

Log in to `http://localhost:8500/admin/` as `admin` / `admin123`. Click `Trivia questions`. Expected: 10 rows shown with thumbnail images, correct-answer column populated, campaign-count = 2 for each, search and filter work.

Log in as `futboleros-gt` / `futboleros123` (campaign manager from a prior session). Open `Trivia questions`. Expected: same 10 rows (because they're assigned to both Futboleros campaigns, and this user manages both). Cannot see questions from any other campaign (there aren't any other campaigns with trivia today, so this is implicit).

- [ ] **Step 7: If everything is green, push**

```bash
git push origin main
```
Expected: push succeeds. (Per global instructions, all commits must be followed by a push.)

- [ ] **Step 8: Submit Mila-bot work report**

Dispatch a background haiku agent to POST to http://localhost:8200/reports/create/ summarising: spec + plan written, 10-question trivia pool live on both Futboleros campaigns, random pick per page load, Finalizar CTAs throughout. Per global rules: ONE agent, GET /reports/ first to check for duplicates.

---

## Self-Review Notes

Coverage check against spec:

| Spec § | Covered by |
|---|---|
| §4 model | Task 2 |
| §5 view wiring | Task 5 |
| §6 theme template | Task 6 |
| §7 question content + images | Tasks 1 (images), 7 (seed) |
| §8 admin | Task 4 |
| §9 migrations 0017/0018/0019 | Tasks 2, 3, 7 |
| §10 tests (model/view/theme/admin/migration smoke) | Tasks 2, 4, 5, 6, 7 |
| §11 rollout (local smoke) | Task 8 |

Edge cases covered:
- Inactive question never picked — Task 5 (test_view_does_not_pick_inactive_questions).
- Cross-campaign isolation — Task 5 (test_view_does_not_pick_questions_assigned_to_other_campaigns).
- Empty pool — Task 5 (test_view_injects_none_when_campaign_has_no_questions) + Task 6 (test_omits_trivia_section_when_no_question) + Task 6 form-success JS guard.
- Image fallback — Task 6 (test_image_falls_back_when_blank).
- Manager scoping in admin — Task 4 (test_hn_manager_cannot_change_gt_only_question).

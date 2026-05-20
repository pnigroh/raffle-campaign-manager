# Multi-Domain Campaigns + Tenant Isolation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind each campaign to a specific hostname so public submission forms 404 on any other domain, and enforce tenant isolation in the dashboard/admin so non-superuser managers only see what they own.

**Architecture:** A new `Domain` model owns campaigns via FK; slug uniqueness moves from global to per-domain. Access is gated in two places: public views match the request's `Host:` header to `Campaign.domain.hostname`, and dashboard/admin views filter through a single `Campaign.objects.visible_to(user)` queryset method that unions domain-level and campaign-level manager assignments. A fallback Domain row with empty `managers` lets the existing per-campaign access pattern continue to work for one-off clients.

**Tech Stack:** Django 5.x, Postgres (prod) / SQLite (dev), Django admin via Unfold, pytest.

**Spec:** [`docs/superpowers/specs/2026-05-13-multi-domain-campaigns-design.md`](../specs/2026-05-13-multi-domain-campaigns-design.md)

---

## Pre-flight

- [ ] **Confirm working tree is clean and tests pass on main**

```bash
cd /home/elgran/Projects/raffle-campaign
git status                              # clean
git log -1 --oneline                    # expect 7b6f0e6 or later
docker exec raffle-web python manage.py test campaigns -v 2
```
Expected: all tests green (currently 122 passing per the cutover doc smoke test, but the live count may differ — record the baseline before starting Task 1).

- [ ] **Create a feature branch**

```bash
git checkout -b feat/multi-domain-campaigns
```

---

## Task 1: Domain model + querysets

Adds the new `Domain` model and the `visible_to` querysets in a dedicated `managers.py` so `models.py` stays focused on schema. Does NOT yet touch `Campaign` — that comes in Task 2 to keep migrations atomic and reviewable.

**Files:**
- Create: `campaigns/managers.py`
- Modify: `campaigns/models.py` (add `Domain` near the top of the file, before `Campaign`)
- Test: `campaigns/tests/test_domain_access.py` (new — start the file with two tests)

- [ ] **Step 1.1: Write the failing test for Domain creation + manager scoping**

`campaigns/tests/test_domain_access.py`:

```python
from django.contrib.auth.models import User
from django.test import TestCase

from campaigns.models import Domain


class DomainModelTests(TestCase):
    def test_domain_string_repr_is_hostname(self):
        d = Domain.objects.create(hostname="example.test")
        self.assertEqual(str(d), "example.test")

    def test_visible_to_superuser_returns_all(self):
        Domain.objects.create(hostname="a.test")
        Domain.objects.create(hostname="b.test")
        su = User.objects.create_superuser("root", "root@x.test", "x")
        self.assertEqual(Domain.objects.visible_to(su).count(), 2)

    def test_visible_to_manager_returns_only_managed(self):
        a = Domain.objects.create(hostname="a.test")
        Domain.objects.create(hostname="b.test")
        u = User.objects.create_user("alice", "a@x.test", "x")
        a.managers.add(u)
        qs = Domain.objects.visible_to(u)
        self.assertEqual(list(qs), [a])

    def test_visible_to_anonymous_returns_none(self):
        Domain.objects.create(hostname="a.test")
        from django.contrib.auth.models import AnonymousUser
        self.assertEqual(Domain.objects.visible_to(AnonymousUser()).count(), 0)
```

- [ ] **Step 1.2: Run the test to verify it fails**

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_domain_access -v 2
```

Expected: `ImportError: cannot import name 'Domain' from 'campaigns.models'`.

- [ ] **Step 1.3: Create `campaigns/managers.py`**

```python
"""QuerySet/Manager classes used by Domain and Campaign for tenant scoping.

Kept out of models.py so models.py stays focused on schema. Both classes
expose ``visible_to(user)`` which is the single source of truth for who can
see which row in dashboard, admin, and any future API surface.
"""
from django.db import models


class DomainQuerySet(models.QuerySet):
    def visible_to(self, user):
        if not getattr(user, "is_authenticated", False):
            return self.none()
        if user.is_superuser:
            return self
        return self.filter(managers=user).distinct()


class CampaignQuerySet(models.QuerySet):
    def visible_to(self, user):
        if not getattr(user, "is_authenticated", False):
            return self.none()
        if user.is_superuser:
            return self
        return self.filter(
            models.Q(domain__managers=user) | models.Q(managers=user)
        ).distinct()
```

- [ ] **Step 1.4: Add `Domain` to `campaigns/models.py`**

Insert near the top of `models.py`, **before** the `Campaign` class:

```python
from .managers import CampaignQuerySet, DomainQuerySet


class Domain(models.Model):
    hostname = models.CharField(max_length=253, unique=True)
    display_name = models.CharField(max_length=200, blank=True)
    managers = models.ManyToManyField(
        "auth.User",
        blank=True,
        related_name="managed_domains",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = DomainQuerySet.as_manager()

    class Meta:
        ordering = ["hostname"]

    def __str__(self):
        return self.hostname
```

- [ ] **Step 1.5: Generate the auto migration for Domain only**

```bash
docker exec raffle-web python manage.py makemigrations campaigns --name domain_model
```

Expected: creates `campaigns/migrations/0009_domain_model.py` containing just `CreateModel('Domain', ...)`. **Inspect the generated file** — it should NOT touch `Campaign` yet.

- [ ] **Step 1.6: Apply the migration and re-run the tests**

```bash
docker exec raffle-web python manage.py migrate campaigns
docker exec raffle-web python manage.py test campaigns.tests.test_domain_access -v 2
```

Expected: 4 tests pass.

- [ ] **Step 1.7: Commit**

```bash
git add campaigns/managers.py campaigns/models.py campaigns/migrations/0009_domain_model.py campaigns/tests/test_domain_access.py
git commit -m "feat(campaigns): Domain model + visible_to querysets"
```

---

## Task 2: Wire Campaign to Domain + per-domain slug uniqueness

Adds the FK, drops global slug uniqueness, adds the `(domain, slug)` composite constraint, and writes the data migration that seeds the fallback Domain and backfills every existing Campaign onto it.

**Files:**
- Modify: `campaigns/models.py` (Campaign class: add `domain` FK, change `slug` field, add Meta constraint, add `public_url` property and `objects = CampaignQuerySet.as_manager()`)
- Create: `campaigns/migrations/0010_campaign_domain_fk.py` (auto-generated then hand-extended)
- Test: `campaigns/tests/test_domain_access.py` (append two more tests)

- [ ] **Step 2.1: Write the failing tests — per-domain uniqueness + visible_to scoping**

Append to `campaigns/tests/test_domain_access.py`:

```python
from django.db import IntegrityError

from campaigns.models import Campaign


class CampaignDomainTests(TestCase):
    def setUp(self):
        self.a = Domain.objects.create(hostname="a.test")
        self.b = Domain.objects.create(hostname="b.test")

    def test_same_slug_two_domains_is_allowed(self):
        Campaign.objects.create(name="C1", slug="summer", domain=self.a)
        # No IntegrityError expected:
        Campaign.objects.create(name="C2", slug="summer", domain=self.b)
        self.assertEqual(Campaign.objects.filter(slug="summer").count(), 2)

    def test_same_slug_same_domain_is_rejected(self):
        Campaign.objects.create(name="C1", slug="summer", domain=self.a)
        with self.assertRaises(IntegrityError):
            Campaign.objects.create(name="C2", slug="summer", domain=self.a)

    def test_campaign_visible_via_domain_membership(self):
        c = Campaign.objects.create(name="C", slug="x", domain=self.a)
        u = User.objects.create_user("alice", "a@x.test", "x")
        self.a.managers.add(u)
        self.assertEqual(list(Campaign.objects.visible_to(u)), [c])

    def test_campaign_visible_via_direct_managers(self):
        c = Campaign.objects.create(name="C", slug="x", domain=self.a)
        u = User.objects.create_user("bob", "b@x.test", "x")
        c.managers.add(u)
        self.assertEqual(list(Campaign.objects.visible_to(u)), [c])

    def test_campaign_not_visible_to_other_tenant(self):
        Campaign.objects.create(name="C", slug="x", domain=self.a)
        other = User.objects.create_user("other", "o@x.test", "x")
        self.b.managers.add(other)
        self.assertEqual(Campaign.objects.visible_to(other).count(), 0)
```

- [ ] **Step 2.2: Verify the tests fail for the right reason**

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_domain_access -v 2
```

Expected: `TypeError: Campaign() got unexpected keyword argument 'domain'` (FK not on model yet).

- [ ] **Step 2.3: Modify `Campaign` in `campaigns/models.py`**

Three changes inside the `Campaign` class:

1. Change the `slug` field — drop `unique=True`:

```python
    slug = models.SlugField(blank=True)
```

2. Add the `domain` FK (place it next to `name`, before any timestamps):

```python
    domain = models.ForeignKey(
        Domain,
        on_delete=models.PROTECT,
        related_name="campaigns",
    )
```

3. Add the custom manager and Meta constraint, and a `public_url` property. Inside the existing `class Meta`:

```python
    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["domain", "slug"],
                name="unique_slug_per_domain",
            ),
        ]
```

After the existing class body, just before `def __str__`:

```python
    objects = CampaignQuerySet.as_manager()

    @property
    def public_url(self):
        return f"https://{self.domain.hostname}/submit/{self.slug}/"
```

- [ ] **Step 2.4: Generate the migration**

```bash
docker exec raffle-web python manage.py makemigrations campaigns --name campaign_domain_fk
```

Expected: creates `campaigns/migrations/0010_campaign_domain_fk.py`. The auto-generated file will ask for a one-off default because `domain` is non-nullable on existing rows — **answer `1` (provide a one-off default) and enter `1` (an integer placeholder)**. We will fix this immediately in the next step.

- [ ] **Step 2.5: Hand-edit `0010_campaign_domain_fk.py` to add the data migration**

Replace the auto-generated file with this (preserve the migration ID and dependency list Django produced — substitute below):

```python
from django.conf import settings
from django.db import migrations, models


def seed_fallback_and_backfill(apps, schema_editor):
    Domain = apps.get_model("campaigns", "Domain")
    Campaign = apps.get_model("campaigns", "Campaign")
    default_hostname = getattr(
        settings, "DEFAULT_FALLBACK_DOMAIN", "promo-domo.example"
    )
    fallback, _ = Domain.objects.get_or_create(
        hostname=default_hostname,
        defaults={"display_name": "Promo-Domo (fallback)"},
    )
    Campaign.objects.filter(domain__isnull=True).update(domain=fallback)


def reverse_noop(apps, schema_editor):
    # Reversing this migration just leaves the fallback Domain row in place;
    # any future Campaign rows can be re-pointed manually.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("campaigns", "0009_domain_model"),
    ]

    operations = [
        # 1. Add domain FK as NULLABLE first so we can backfill.
        migrations.AddField(
            model_name="campaign",
            name="domain",
            field=models.ForeignKey(
                null=True,
                on_delete=models.deletion.PROTECT,
                related_name="campaigns",
                to="campaigns.domain",
            ),
        ),

        # 2. Seed fallback domain + assign every existing campaign to it.
        migrations.RunPython(seed_fallback_and_backfill, reverse_noop),

        # 3. Now that every row has a domain, enforce NOT NULL.
        migrations.AlterField(
            model_name="campaign",
            name="domain",
            field=models.ForeignKey(
                on_delete=models.deletion.PROTECT,
                related_name="campaigns",
                to="campaigns.domain",
            ),
        ),

        # 4. Slug uniqueness moves from global to per-domain.
        migrations.AlterField(
            model_name="campaign",
            name="slug",
            field=models.SlugField(blank=True),
        ),
        migrations.AddConstraint(
            model_name="campaign",
            constraint=models.UniqueConstraint(
                fields=("domain", "slug"),
                name="unique_slug_per_domain",
            ),
        ),
    ]
```

- [ ] **Step 2.6: Apply the migration and re-run the tests**

```bash
docker exec raffle-web python manage.py migrate campaigns
docker exec raffle-web python manage.py test campaigns.tests.test_domain_access -v 2
```

Expected: all 8 tests in the file pass. Also re-run the full suite to confirm no regression in pre-existing tests that build campaigns without `domain=`:

```bash
docker exec raffle-web python manage.py test campaigns -v 2
```

If this fails with `IntegrityError: NOT NULL constraint failed: campaigns_campaign.domain_id`, the pre-existing test fixtures need a `Domain` set up. Add a class-level `setUp` to the failing TestCase that creates a Domain and passes it in. Don't bulk-edit — fix the ones that break.

- [ ] **Step 2.7: Commit**

```bash
git add campaigns/models.py campaigns/migrations/0010_campaign_domain_fk.py campaigns/tests/test_domain_access.py
git commit -m "feat(campaigns): Campaign.domain FK + per-domain slug uniqueness + data migration"
```

---

## Task 3: Public-form host gate — helper + correct/wrong-host tests

Adds the `_get_campaign_for_host` helper. Does not yet wire it into the views (Task 4).

**Files:**
- Modify: `campaigns/views.py` (add helper near the existing `_campaigns_for` and `_get_managed_campaign_or_403` helpers)
- Test: `campaigns/tests/test_domain_access.py` (append)

- [ ] **Step 3.1: Write the failing tests for the helper**

Append to `campaigns/tests/test_domain_access.py`:

```python
from django.http import Http404
from django.test import RequestFactory

from campaigns.views import _get_campaign_for_host


class GetCampaignForHostTests(TestCase):
    def setUp(self):
        self.a = Domain.objects.create(hostname="a.test")
        self.b = Domain.objects.create(hostname="b.test")
        self.c_a = Campaign.objects.create(
            name="A-summer", slug="summer", domain=self.a, is_active=True
        )
        self.c_b = Campaign.objects.create(
            name="B-summer", slug="summer", domain=self.b, is_active=True
        )

    def _req(self, host):
        rf = RequestFactory(HTTP_HOST=host)
        return rf.get("/")

    def test_correct_host_returns_campaign(self):
        c = _get_campaign_for_host(self._req("a.test"), "summer")
        self.assertEqual(c, self.c_a)

    def test_wrong_host_raises_404(self):
        with self.assertRaises(Http404):
            _get_campaign_for_host(self._req("nope.test"), "summer")

    def test_same_slug_different_host_disambiguates(self):
        a = _get_campaign_for_host(self._req("a.test"), "summer")
        b = _get_campaign_for_host(self._req("b.test"), "summer")
        self.assertEqual({a, b}, {self.c_a, self.c_b})

    def test_host_with_port_is_stripped(self):
        c = _get_campaign_for_host(self._req("a.test:8500"), "summer")
        self.assertEqual(c, self.c_a)

    def test_inactive_campaign_returns_404(self):
        self.c_a.is_active = False
        self.c_a.save()
        with self.assertRaises(Http404):
            _get_campaign_for_host(self._req("a.test"), "summer")
```

- [ ] **Step 3.2: Verify the tests fail**

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_domain_access.GetCampaignForHostTests -v 2
```

Expected: `ImportError: cannot import name '_get_campaign_for_host'`.

- [ ] **Step 3.3: Add the helper to `campaigns/views.py`**

Insert near the existing helpers (search for `_campaigns_for` to find the right block; place this right after `_get_managed_campaign_or_403`):

```python
def _get_campaign_for_host(request, slug):
    """Look up an active campaign bound to the request's host.

    Returns the Campaign or raises Http404. The host portion of
    ``request.get_host()`` is split on ``:`` because the reverse proxy
    terminates TLS and may forward ``a.test:8500`` in dev. We never
    expose port numbers in Domain.hostname.
    """
    host = request.get_host().split(":")[0]
    return get_object_or_404(
        Campaign,
        domain__hostname=host,
        slug=slug,
        is_active=True,
    )
```

- [ ] **Step 3.4: Run tests to verify they pass**

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_domain_access.GetCampaignForHostTests -v 2
```

Expected: 5 tests pass.

- [ ] **Step 3.5: Commit**

```bash
git add campaigns/views.py campaigns/tests/test_domain_access.py
git commit -m "feat(campaigns): _get_campaign_for_host helper + tests"
```

---

## Task 4: Wire host gate into the three public views

**Files:**
- Modify: `campaigns/views.py` (lines 33, 73, 78 — the three public views)
- Test: `campaigns/tests/test_domain_access.py` (append integration tests through the URL layer)

- [ ] **Step 4.1: Write integration tests through the test client**

Append to `campaigns/tests/test_domain_access.py`:

```python
class PublicViewHostGateTests(TestCase):
    def setUp(self):
        self.a = Domain.objects.create(hostname="a.test")
        self.b = Domain.objects.create(hostname="b.test")
        self.campaign = Campaign.objects.create(
            name="A-summer", slug="summer", domain=self.a, is_active=True
        )

    def test_submission_form_200_on_correct_host(self):
        r = self.client.get("/submit/summer/", HTTP_HOST="a.test")
        self.assertEqual(r.status_code, 200)

    def test_submission_form_404_on_wrong_host(self):
        r = self.client.get("/submit/summer/", HTTP_HOST="b.test")
        self.assertEqual(r.status_code, 404)

    def test_submission_success_404_on_wrong_host(self):
        r = self.client.get("/submit/summer/success/", HTTP_HOST="b.test")
        self.assertEqual(r.status_code, 404)
```

You may also need to add `ALLOWED_HOSTS` test override if Django rejects `a.test` / `b.test` outright. Place at the top of the new class:

```python
from django.test import TestCase, override_settings

@override_settings(ALLOWED_HOSTS=["a.test", "b.test", "nope.test", "*"])
class PublicViewHostGateTests(TestCase):
    ...
```

(Use `"*"` on the test override so the lower-level RequestFactory tests in Task 3 also work without per-test setup.)

- [ ] **Step 4.2: Verify the tests fail**

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_domain_access.PublicViewHostGateTests -v 2
```

Expected: `test_submission_form_404_on_wrong_host` fails with 200 (the current view ignores Host).

- [ ] **Step 4.3: Replace the three lookups in `campaigns/views.py`**

At line 34 (in `submission_form`):

```python
    campaign = _get_campaign_for_host(request, campaign_slug)
```

At line 74 (in `submission_success`):

```python
    campaign = _get_campaign_for_host(request, campaign_slug)
```

At line 82 (in `submission_form_preview`):

```python
    campaign = _get_campaign_for_host(request, campaign_slug)
```

(Each replaces the existing `campaign = get_object_or_404(Campaign, slug=campaign_slug, ...)` line. The other lookup site at line 26 — the helper for authenticated views — stays as-is; it's gated by login + `_get_managed_campaign_or_403`, not by host.)

- [ ] **Step 4.4: Run the tests**

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_domain_access.PublicViewHostGateTests -v 2
docker exec raffle-web python manage.py test campaigns -v 2
```

Expected: new tests pass; full suite still green. **Likely regression to watch:** any existing test that hits `/submit/<slug>/` without an `HTTP_HOST` matching the campaign's domain will now 404. Fix the failing test by adding a Domain to its setUp and passing `HTTP_HOST=...` on the client call. If many tests break, prefer fixing them one-by-one over weakening the gate.

- [ ] **Step 4.5: Commit**

```bash
git add campaigns/views.py campaigns/tests/test_domain_access.py
git commit -m "feat(campaigns): public submission views require matching host header"
```

---

## Task 5: DomainAdmin (new)

**Files:**
- Modify: `campaigns/admin.py` (add `DomainAdmin` class + register)
- Test: `campaigns/tests/test_domain_access.py` (append)

- [ ] **Step 5.1: Write the failing test**

Append:

```python
from django.urls import reverse


class DomainAdminTests(TestCase):
    def setUp(self):
        self.su = User.objects.create_superuser("root", "r@x.test", "x")
        self.manager = User.objects.create_user(
            "alice", "a@x.test", "x", is_staff=True
        )
        from django.contrib.auth.models import Group
        Group.objects.get(name="Campaign Managers").user_set.add(self.manager)
        self.a = Domain.objects.create(hostname="a.test")
        self.b = Domain.objects.create(hostname="b.test")
        self.a.managers.add(self.manager)

    def test_superuser_admin_shows_all_domains(self):
        self.client.force_login(self.su)
        r = self.client.get(reverse("admin:campaigns_domain_changelist"))
        self.assertContains(r, "a.test")
        self.assertContains(r, "b.test")

    def test_manager_admin_shows_only_own_domains(self):
        self.client.force_login(self.manager)
        r = self.client.get(reverse("admin:campaigns_domain_changelist"))
        self.assertContains(r, "a.test")
        self.assertNotContains(r, "b.test")
```

- [ ] **Step 5.2: Verify the test fails**

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_domain_access.DomainAdminTests -v 2
```

Expected: `NoReverseMatch: 'admin:campaigns_domain_changelist'` (admin not registered).

- [ ] **Step 5.3: Register `DomainAdmin` in `campaigns/admin.py`**

Add near the other admin classes:

```python
from unfold.admin import ModelAdmin

from .models import Domain


@admin.register(Domain)
class DomainAdmin(ModelAdmin):
    list_display = ("hostname", "display_name", "manager_count", "campaign_count")
    search_fields = ("hostname", "display_name")
    filter_horizontal = ("managers",)
    ordering = ("hostname",)

    def get_queryset(self, request):
        return Domain.objects.visible_to(request.user)

    @admin.display(description="Managers")
    def manager_count(self, obj):
        return obj.managers.count()

    @admin.display(description="Campaigns")
    def campaign_count(self, obj):
        return obj.campaigns.count()

    def has_add_permission(self, request):
        # Only superusers create new domains; managers can edit their own.
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
```

You may need to add `Domain` to the `from .models import ...` block at the top of `admin.py`.

Also add `view+change` perms on `Domain` to the "Campaign Managers" group. Create a new data migration:

```bash
docker exec raffle-web python manage.py makemigrations campaigns --empty --name add_domain_perms_to_campaign_managers_group
```

Edit the generated file (will be `0011_*`):

```python
from django.db import migrations


def add_domain_perms(apps, schema_editor):
    # Domain's permissions don't exist yet at this point in the migrate run
    # because post_migrate hasn't fired. Use the same pattern as
    # 0005_create_campaign_managers_group.py: materialize permissions first.
    from django.contrib.auth.management import create_permissions
    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    group, _ = Group.objects.get_or_create(name="Campaign Managers")
    ct = ContentType.objects.get(app_label="campaigns", model="domain")
    for codename in ("view_domain", "change_domain"):
        perm = Permission.objects.get(codename=codename, content_type=ct)
        group.permissions.add(perm)


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("campaigns", "0010_campaign_domain_fk"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]
    operations = [migrations.RunPython(add_domain_perms, reverse_noop)]
```

- [ ] **Step 5.4: Apply + test**

```bash
docker exec raffle-web python manage.py migrate campaigns
docker exec raffle-web python manage.py test campaigns.tests.test_domain_access.DomainAdminTests -v 2
```

Expected: 2 tests pass.

- [ ] **Step 5.5: Commit**

```bash
git add campaigns/admin.py campaigns/migrations/0011_add_domain_perms_to_campaign_managers_group.py campaigns/tests/test_domain_access.py
git commit -m "feat(admin): DomainAdmin scoped via visible_to + perms in Campaign Managers group"
```

---

## Task 6: CampaignAdmin updates — visible_to scoping + cross-tenant rejection

**Files:**
- Modify: `campaigns/admin.py` (`CampaignAdmin.get_queryset`, add `formfield_for_foreignkey`, modify `save_model`)
- Test: `campaigns/tests/test_domain_access.py` (append)

- [ ] **Step 6.1: Write the failing test**

```python
from django.core.exceptions import PermissionDenied


class CampaignAdminScopingTests(TestCase):
    def setUp(self):
        self.su = User.objects.create_superuser("root", "r@x.test", "x")
        self.alice = User.objects.create_user(
            "alice", "a@x.test", "x", is_staff=True
        )
        from django.contrib.auth.models import Group
        Group.objects.get(name="Campaign Managers").user_set.add(self.alice)
        self.a = Domain.objects.create(hostname="a.test")
        self.b = Domain.objects.create(hostname="b.test")
        self.a.managers.add(self.alice)
        self.c_a = Campaign.objects.create(
            name="A-camp", slug="x", domain=self.a, is_active=True
        )
        self.c_b = Campaign.objects.create(
            name="B-camp", slug="x", domain=self.b, is_active=True
        )

    def test_changelist_only_shows_visible(self):
        self.client.force_login(self.alice)
        r = self.client.get(reverse("admin:campaigns_campaign_changelist"))
        self.assertContains(r, "A-camp")
        self.assertNotContains(r, "B-camp")

    def test_cannot_open_other_tenants_campaign(self):
        self.client.force_login(self.alice)
        url = reverse("admin:campaigns_campaign_change", args=[self.c_b.id])
        r = self.client.get(url)
        # Django admin returns 302 to the changelist when get_object returns None
        self.assertIn(r.status_code, (302, 404))

    def test_domain_dropdown_filtered_for_non_superuser(self):
        from campaigns.admin import CampaignAdmin
        from django.contrib.admin.sites import AdminSite
        ma = CampaignAdmin(Campaign, AdminSite())
        rf = RequestFactory()
        req = rf.get("/")
        req.user = self.alice
        ff = ma.formfield_for_foreignkey(
            Campaign._meta.get_field("domain"), req
        )
        self.assertEqual(list(ff.queryset), [self.a])
```

- [ ] **Step 6.2: Verify it fails**

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_domain_access.CampaignAdminScopingTests -v 2
```

Expected: `test_domain_dropdown_filtered_for_non_superuser` fails — current admin returns all domains in the dropdown.

- [ ] **Step 6.3: Modify `CampaignAdmin` in `campaigns/admin.py`**

Locate the existing `class CampaignAdmin(ModelAdmin)` at line 72 and update its `get_queryset` (line 100) so it uses `visible_to`. Then add the two new methods:

```python
    def get_queryset(self, request):
        return Campaign.objects.visible_to(request.user)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "domain":
            kwargs["queryset"] = Domain.objects.visible_to(request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        # Defense-in-depth: even if the form's queryset filter was bypassed,
        # reject cross-tenant domain assignments here.
        if not request.user.is_superuser:
            if obj.domain_id not in Domain.objects.visible_to(
                request.user
            ).values_list("id", flat=True):
                from django.core.exceptions import PermissionDenied
                raise PermissionDenied(
                    "You don't manage that domain."
                )
        super().save_model(request, obj, form, change)
```

- [ ] **Step 6.4: Run tests**

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_domain_access.CampaignAdminScopingTests -v 2
docker exec raffle-web python manage.py test campaigns -v 2
```

Expected: 3 new tests pass; full suite green.

- [ ] **Step 6.5: Commit**

```bash
git add campaigns/admin.py campaigns/tests/test_domain_access.py
git commit -m "feat(admin): CampaignAdmin scopes via visible_to and rejects cross-tenant domains"
```

---

## Task 7: Close the ID-guessing hole in dashboard views

The existing dashboard helper `_get_managed_campaign_or_403` already gates by `Campaign.managers`, but the spec requires `visible_to` semantics (which also unions in `Domain.managers`). This task updates the helper.

**Files:**
- Modify: `campaigns/views.py` (rewrite `_campaigns_for` and `_get_managed_campaign_or_403` to delegate to `Campaign.objects.visible_to`)
- Test: `campaigns/tests/test_domain_access.py` (append) — verifies dashboard URLs for an unmanaged campaign return 403/404 even for domain managers of OTHER domains.

- [ ] **Step 7.1: Write the failing test**

```python
class DashboardScopingTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(
            "alice", "a@x.test", "x", is_staff=True
        )
        from django.contrib.auth.models import Group
        Group.objects.get(name="Campaign Managers").user_set.add(self.alice)
        self.a = Domain.objects.create(hostname="a.test")
        self.b = Domain.objects.create(hostname="b.test")
        self.a.managers.add(self.alice)
        self.c_a = Campaign.objects.create(
            name="A", slug="x", domain=self.a, is_active=True
        )
        self.c_b = Campaign.objects.create(
            name="B", slug="x", domain=self.b, is_active=True
        )

    def test_domain_manager_sees_domain_campaigns_in_dashboard(self):
        self.client.force_login(self.alice)
        r = self.client.get("/dashboard/")
        self.assertContains(r, "A")
        self.assertNotContains(r, "B")

    def test_id_guess_to_other_tenant_returns_404(self):
        self.client.force_login(self.alice)
        url = f"/dashboard/campaign/{self.c_b.id}/"
        r = self.client.get(url)
        self.assertEqual(r.status_code, 404)
```

- [ ] **Step 7.2: Verify fail**

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_domain_access.DashboardScopingTests -v 2
```

Expected: `test_domain_manager_sees_domain_campaigns_in_dashboard` fails — current `_campaigns_for` only checks `Campaign.managers`.

- [ ] **Step 7.3: Update the two helpers in `campaigns/views.py`**

Find `_campaigns_for(user)` (around line ~15) and replace with:

```python
def _campaigns_for(user):
    """Queryset of campaigns the user may see in dashboard views."""
    return Campaign.objects.visible_to(user)


def _get_managed_campaign_or_403(user, campaign_id):
    """Return campaign if user manages it (directly or via domain), else 404."""
    return get_object_or_404(_campaigns_for(user), id=campaign_id)
```

Note: the function now returns 404 instead of 403 (matches `get_object_or_404` semantics; matches `submission_form` behavior; consistent with "no info leak"). Any call site that previously inspected the response code for 403 vs 404 needs to be updated.

- [ ] **Step 7.4: Run tests**

```bash
docker exec raffle-web python manage.py test campaigns -v 2
```

Expected: full suite green. If any pre-existing access-control test was asserting 403 specifically, change its assertion to 404 (or `assertIn(status, [403, 404])`).

- [ ] **Step 7.5: Commit**

```bash
git add campaigns/views.py campaigns/tests/test_domain_access.py
git commit -m "feat(views): dashboard scoping unions domain + campaign managers"
```

---

## Task 8: System check for ALLOWED_HOSTS sync

**Files:**
- Create: `campaigns/checks.py`
- Modify: `campaigns/apps.py` (import the checks module in `ready()`)
- Test: `campaigns/tests/test_domain_access.py` (append)

- [ ] **Step 8.1: Write the failing test**

```python
from django.core.checks import Warning, run_checks
from django.test import override_settings


class AllowedHostsCheckTests(TestCase):
    def setUp(self):
        Domain.objects.create(hostname="not-in-allowed-hosts.test")

    @override_settings(ALLOWED_HOSTS=["something-else.test"])
    def test_warning_emitted_when_domain_missing(self):
        from campaigns.checks import domains_in_allowed_hosts
        warnings = domains_in_allowed_hosts(app_configs=None)
        self.assertTrue(
            any(w.id == "campaigns.W001" for w in warnings)
        )

    @override_settings(ALLOWED_HOSTS=["*"])
    def test_wildcard_suppresses_warning(self):
        from campaigns.checks import domains_in_allowed_hosts
        warnings = domains_in_allowed_hosts(app_configs=None)
        self.assertEqual(warnings, [])

    @override_settings(ALLOWED_HOSTS=["not-in-allowed-hosts.test"])
    def test_no_warning_when_all_present(self):
        from campaigns.checks import domains_in_allowed_hosts
        warnings = domains_in_allowed_hosts(app_configs=None)
        self.assertEqual(warnings, [])
```

- [ ] **Step 8.2: Verify fail**

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_domain_access.AllowedHostsCheckTests -v 2
```

Expected: `ModuleNotFoundError: No module named 'campaigns.checks'`.

- [ ] **Step 8.3: Create `campaigns/checks.py`**

```python
"""System checks that fail-fast on operator misconfiguration.

Registered via campaigns/apps.py at app-ready time.
"""
from django.conf import settings
from django.core.checks import Warning, register


@register()
def domains_in_allowed_hosts(app_configs, **kwargs):
    """Warn if any Domain.hostname is missing from settings.ALLOWED_HOSTS.

    A Warning (not Error) so dev environments without all hostnames don't
    refuse to start; ``manage.py check --deploy`` and operator-facing log
    aggregators are expected to surface campaigns.W001.
    """
    # Imported lazily because checks load before app-ready in some flows.
    from .models import Domain

    if "*" in settings.ALLOWED_HOSTS:
        return []

    missing = sorted(
        d.hostname for d in Domain.objects.all()
        if d.hostname not in settings.ALLOWED_HOSTS
    )
    if not missing:
        return []
    return [
        Warning(
            f"Domain hostname(s) not in ALLOWED_HOSTS: {', '.join(missing)}. "
            "Add them or the public form will return Bad Request.",
            id="campaigns.W001",
        )
    ]
```

- [ ] **Step 8.4: Wire it into `campaigns/apps.py`**

Inside `class CampaignsConfig(AppConfig)`, add (or update) a `ready` method:

```python
    def ready(self):
        from . import checks  # noqa: F401  -- registers via decorator
```

- [ ] **Step 8.5: Run tests + verify manage.py check picks it up**

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_domain_access.AllowedHostsCheckTests -v 2
docker exec raffle-web python manage.py check
```

Expected: 3 new tests pass; `manage.py check` either reports no issues or surfaces `campaigns.W001` (depending on dev `ALLOWED_HOSTS`). The latter is acceptable in dev.

- [ ] **Step 8.6: Commit**

```bash
git add campaigns/checks.py campaigns/apps.py campaigns/tests/test_domain_access.py
git commit -m "feat(campaigns): system check warns when Domain.hostname is missing from ALLOWED_HOSTS"
```

---

## Task 9: Admin save-model warning on slug/domain change

**Files:**
- Modify: `campaigns/admin.py` (extend `CampaignAdmin.save_model` to add a `messages.warning`)
- Test: `campaigns/tests/test_domain_access.py` (append)

- [ ] **Step 9.1: Write the failing test**

```python
class SlugChangeWarningTests(TestCase):
    def setUp(self):
        self.su = User.objects.create_superuser("root", "r@x.test", "x")
        self.a = Domain.objects.create(hostname="a.test")
        self.c = Campaign.objects.create(
            name="C", slug="old", domain=self.a, is_active=True
        )

    def test_warning_on_slug_change(self):
        self.client.force_login(self.su)
        url = reverse("admin:campaigns_campaign_change", args=[self.c.id])
        # POST a form change. Field set will vary by your CampaignAdmin fieldsets;
        # adjust if necessary.
        r = self.client.post(url, data={
            "name": "C", "slug": "new", "domain": self.a.id,
            "is_active": "on",
        }, follow=True)
        messages = [m.message for m in r.context["messages"]]
        self.assertTrue(any("Public URL changed" in m for m in messages))
```

This test will likely need adjustment because the real CampaignAdmin form has more required fields; expect to add `display_title=""`, `primary_color="#000000"`, etc. depending on the spec. Run once to see what's required, then fill in.

- [ ] **Step 9.2: Verify fail**

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_domain_access.SlugChangeWarningTests -v 2
```

Expected: no warning message present.

- [ ] **Step 9.3: Extend `CampaignAdmin.save_model`**

Replace the `save_model` from Task 6 with:

```python
    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            if obj.domain_id not in Domain.objects.visible_to(
                request.user
            ).values_list("id", flat=True):
                from django.core.exceptions import PermissionDenied
                raise PermissionDenied("You don't manage that domain.")

        if change:
            old = Campaign.objects.get(pk=obj.pk)
            if old.slug != obj.slug or old.domain_id != obj.domain_id:
                from django.contrib import messages
                messages.warning(
                    request,
                    "Public URL changed; previously distributed links no "
                    "longer work.",
                )
        super().save_model(request, obj, form, change)
```

- [ ] **Step 9.4: Run tests**

```bash
docker exec raffle-web python manage.py test campaigns -v 2
```

Expected: full suite green.

- [ ] **Step 9.5: Commit**

```bash
git add campaigns/admin.py campaigns/tests/test_domain_access.py
git commit -m "feat(admin): warn on Campaign slug/domain change"
```

---

## Task 10: Use `public_url` everywhere a campaign URL is shown

**Files (modify):**
- `campaigns/admin.py` — register `Campaign.public_url` as the admin's "View on site" link (override `get_view_on_site_url`)
- `campaigns/templates/campaigns/dashboard.html` — wherever the campaign's public URL is rendered, switch to `{{ campaign.public_url }}`
- `campaigns/templates/campaigns/campaign_detail.html` — same

- [ ] **Step 10.1: Locate every place a public URL is currently constructed**

```bash
grep -rn "submit/{{\\|submit/%(\\|submit/{%\\|reverse.submission_form" campaigns/templates campaigns/admin.py campaigns/views.py
```

Expected: handful of `{% url 'submission_form' campaign.slug %}` template references and possibly an admin `get_absolute_url`. **Make a list before editing**.

- [ ] **Step 10.2: Replace each with `{{ campaign.public_url }}`**

For each match: change `{% url 'submission_form' campaign.slug %}` to `{{ campaign.public_url }}`. The `public_url` is an absolute https URL — operators want to copy/paste it to clients; relative URLs would be wrong.

If a template builds a "copy this URL" UI, also wrap it in display-friendly markup; do not touch other layout.

- [ ] **Step 10.3: In `CampaignAdmin`, add `view_on_site` integration**

```python
    def get_view_on_site_url(self, obj=None):
        if obj is None:
            return None
        return obj.public_url
```

- [ ] **Step 10.4: Manual smoke test**

```bash
docker exec raffle-web python manage.py runserver 0.0.0.0:8000  # already auto-restarts
```

Open `http://localhost:8500/dashboard/` and verify the displayed campaign URLs now point at `https://<domain.hostname>/submit/<slug>/`. The dev container is on `a.test` if you assigned it; the fallback domain otherwise.

- [ ] **Step 10.5: Run tests**

```bash
docker exec raffle-web python manage.py test campaigns -v 2
```

Expected: no regressions. (No new test added in this task; behavior is purely cosmetic / display.)

- [ ] **Step 10.6: Commit**

```bash
git add campaigns/admin.py campaigns/templates/campaigns/dashboard.html campaigns/templates/campaigns/campaign_detail.html
git commit -m "feat(ui): show absolute campaign public_url everywhere it's displayed"
```

---

## Task 11: Operator docs

**Files (modify):**
- `docs/deployment/host-setup.md` — new section "Adding a new tenant domain"
- `docs/deployment/restore-playbook.md` — note about updating Domain rows during DR if hostnames change
- `RUNNING.md` — note that local dev defaults to the fallback Domain `promo-domo.example` and how to add a test domain

- [ ] **Step 11.1: Add "Adding a new tenant domain" section to `host-setup.md`**

Insert before the "Troubleshooting" section (or append if none):

```markdown
## Adding a new tenant domain

When onboarding a new client with their own branded domain:

1. **DNS** — point the hostname at the prod VPS.
2. **Reverse proxy** (Plesk) — add the new hostname to the existing app's vhost (or create a new vhost forwarding to the app container).
3. **ALLOWED_HOSTS** — add the new hostname to `ALLOWED_HOSTS` in `.env.prod`. Restart the web container.
4. **Domain row** — in Django admin → Domains → Add. Set hostname, display_name, and add the client user(s) to managers.
5. **Existing campaigns** — move any relevant campaigns to the new Domain via admin (Campaign change page → Domain dropdown).

After step 3 you can verify with:

\`\`\`bash
docker exec raffle-prod python manage.py check
\`\`\`

Any `campaigns.W001` warning means a Domain row references a hostname not in ALLOWED_HOSTS. Fix and restart.
```

- [ ] **Step 11.2: Add the DR note to `restore-playbook.md`**

Append a one-paragraph section called "Domain hostnames during DR":

```markdown
## Domain hostnames during DR

The `Domain.hostname` rows in the restored DB will reflect whatever was in production at the time of the snapshot. If you're restoring to a different host or temporary URL (e.g., a staging VM with a `*.staging.example` cert), the public submission forms will 404 until you either:

- Edit Domain.hostname rows in the restored DB to match the new host, OR
- Add the new host as an alias in ALLOWED_HOSTS *and* update Domain.hostname accordingly.

The system check (`manage.py check`) surfaces `campaigns.W001` if any Domain.hostname is not in ALLOWED_HOSTS, which is the fastest way to catch this on the restored host.
```

- [ ] **Step 11.3: Update `RUNNING.md`**

Add a section near the end:

```markdown
## Multi-domain dev setup

Local dev runs everything through `localhost:8500`. After running migrations:

- A fallback Domain `promo-domo.example` is auto-created and every existing
  campaign is bound to it.
- The public submission form at `/submit/<slug>/` will 404 unless the request
  Host matches the campaign's domain. To test in a browser, either:
  - Add an entry to `/etc/hosts` mapping the campaign's hostname to 127.0.0.1
    and visit `http://<hostname>:8500/submit/<slug>/`.
  - Or change the campaign's `domain` to `localhost` (or a Domain row whose
    hostname is `localhost`) in the admin.
- Dashboard and admin are not host-gated; you can always log in from
  `localhost:8500/dashboard/`.
```

- [ ] **Step 11.4: Commit**

```bash
git add docs/deployment/host-setup.md docs/deployment/restore-playbook.md RUNNING.md
git commit -m "docs: operator playbook for multi-domain campaigns + DR notes"
```

---

## Task 12: Update memory pointers + open PR

**Files (modify, outside the repo):**
- `/home/elgran/.claude/projects/-home-elgran-Projects-raffle-campaign/memory/MEMORY.md`
- `/home/elgran/.claude/projects/-home-elgran-Projects-raffle-campaign/memory/project_campaign_managers.md` (mark closed-by-this)
- `/home/elgran/.claude/projects/-home-elgran-Projects-raffle-campaign/memory/project_multi_domain_campaigns.md` (new — shipped status)

These edits happen via the assistant's memory write process, not via git. Then open the PR:

- [ ] **Step 12.1: Push the branch and open PR**

```bash
git push -u origin feat/multi-domain-campaigns
gh pr create --title "Multi-domain campaigns + tenant isolation" --body "$(cat <<'EOF'
## Summary
- New `Domain` model owns campaigns; slug uniqueness is now per-domain.
- Public submission forms 404 when the request Host doesn't match the campaign's bound domain.
- Dashboard and admin views scope through `Campaign.objects.visible_to(user)`, closing the cross-tenant ID-guessing hole.
- Fallback domain (`promo-domo.example`) backfilled for all existing campaigns; operators reassign post-deploy.
- Django system check warns if any `Domain.hostname` is missing from `ALLOWED_HOSTS`.

## Test plan
- [ ] Full pytest suite green (`docker exec raffle-web python manage.py test campaigns`)
- [ ] Manual: create two Domain rows + two campaigns with the same slug; verify each loads only from the right host
- [ ] Manual: superuser sees both campaigns in admin; non-superuser scoped correctly
- [ ] Manual: `manage.py check` flags a missing-host Domain

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 12.2: Self-review the PR diff before requesting review**

Walk every changed file; verify no debug prints, no commented-out code, no stale TODOs introduced. Check that `campaigns/views.py` still passes the existing access-control test suite at full strength.

- [ ] **Step 12.3: Squash-merge after approval**

```bash
gh pr merge --squash
git checkout main && git pull
git branch -d feat/multi-domain-campaigns
```

- [ ] **Step 12.4: Verify dev still boots**

```bash
RAFFLE_CAMPAIGN_WEB_PORT=8500 docker compose restart web
docker exec raffle-web python manage.py migrate
docker exec raffle-web python manage.py check
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8500/dashboard/login/   # 200
```

---

## Out-of-scope follow-ups (not in this plan)

- Subdomain wildcards (deferred per spec §3).
- HTML form for managing Campaign.managers / Domain.managers from the dashboard (deferred — admin only for this iteration).
- A dashboard-side "share this URL" copy widget (a frontend polish task).
- Per-domain branding overrides on the login page (interesting interaction with `project_promo_domo_rebrand.md` but out of scope here).

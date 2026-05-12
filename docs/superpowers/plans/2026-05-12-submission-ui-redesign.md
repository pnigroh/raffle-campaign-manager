# Submission UI redesign for the Futboleros campaign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update `campaigns/templates/campaigns/submission_form.html` to match the new "La Nube que te mueve… y te lleva al gol" design (5 mobile + 5 desktop screens), adding a desktop layout and swapping in the designer's image-titulars and BGs.

**Architecture:** Pure template + asset work. Copy 14 PNGs into a new `campaigns/static/campaigns/landing/` subfolder. In-place edit `submission_form.html` to swap the welcome composition, replace text-rendered titulars with `<img>` tags, swap the mobile BGs, and add a `@media (min-width: 768px)` block for the desktop side-by-side layout. No view, model, URL, or migration changes.

**Tech Stack:** Django 4.2 templates + `{% static %}`, vanilla CSS (existing `<style>` block), no new JS.

**Spec:** `docs/superpowers/specs/2026-05-11-submission-ui-redesign.md`

---

## File Structure

**Create (new asset subfolder):**
- `campaigns/static/campaigns/landing/bg_mobile_welcome.png` (from `~/Downloads/Landing_Carpeta/Mobile BG/BG_1.png`)
- `campaigns/static/campaigns/landing/bg_mobile_steps.png` (from `~/Downloads/Landing_Carpeta/Mobile BG/BG_2.png`)
- `campaigns/static/campaigns/landing/bg_desktop.png` (from `~/Downloads/Landing_Carpeta/Desktop BG/BG_1_Desktop.png`)
- `campaigns/static/campaigns/landing/titular_anota_datos.png` (from `~/Downloads/Landing_Carpeta/Pantalla_2_TitularAnotaTusDatos.png`)
- `campaigns/static/campaigns/landing/titular_y_comienza.png` (from `~/Downloads/Landing_Carpeta/Pantalla_2_Titular_Y Comienza a Participar.png`)
- `campaigns/static/campaigns/landing/titular_jugando.png` (from `~/Downloads/Landing_Carpeta/Pantalla_3_Titular.png`)
- `campaigns/static/campaigns/landing/titular_crack.png` (from `~/Downloads/Landing_Carpeta/Pantalla_4A_Titular_EresunCrack.png`)
- `campaigns/static/campaigns/landing/titular_fallaste.png` (from `~/Downloads/Landing_Carpeta/Pantalla_4B_TitularFallaste.png`)
- `campaigns/static/campaigns/landing/btn_empezar.png` (from `~/Downloads/Landing_Carpeta/Pantalla_1_Button Empezar.png`)
- `campaigns/static/campaigns/landing/btn_enviar.png` (from `~/Downloads/Landing_Carpeta/Pantalla_2_Button_Enviar.png`)
- `campaigns/static/campaigns/landing/btn_adivinar.png` (from `~/Downloads/Landing_Carpeta/Pantalla_3_ButtonAdivinar.png`)
- `campaigns/static/campaigns/landing/btn_finalizar_a.png` (from `~/Downloads/Landing_Carpeta/Pantalla_4A_ButtonFinalizar.png`)
- `campaigns/static/campaigns/landing/btn_finalizar_b.png` (from `~/Downloads/Landing_Carpeta/Pantalla_4B_ButtonFinalizar.png`)
- `campaigns/static/campaigns/landing/icon_upload.png` (from `~/Downloads/Landing_Carpeta/Pantalla_2_IconUpload.png`)

**Create (new test file):**
- `campaigns/tests/test_submission_form_redesign.py`

**Modify:**
- `campaigns/templates/campaigns/submission_form.html` — welcome step markup, form/trivia/success/fail titular markup, mobile BG paths, new `.titular`/`.titular-stack`/`.btn-image` CSS rules, and the desktop media query (replaces existing 720px block).

**Out of scope:** views.py, forms.py, models.py, urls.py, admin.py — no changes. Legacy assets in `campaigns/static/campaigns/img/` stay on disk but are no longer referenced.

---

## Task 1: Copy assets + verify served

**Files:**
- Create: 14 PNGs under `campaigns/static/campaigns/landing/`

- [ ] **Step 1: Create the destination directory and copy the assets**

```bash
mkdir -p /home/elgran/Projects/raffle-campaign/campaigns/static/campaigns/landing
cd /home/elgran/Projects/raffle-campaign/campaigns/static/campaigns/landing

cp "/home/elgran/Downloads/Landing_Carpeta/Mobile BG/BG_1.png" bg_mobile_welcome.png
cp "/home/elgran/Downloads/Landing_Carpeta/Mobile BG/BG_2.png" bg_mobile_steps.png
cp "/home/elgran/Downloads/Landing_Carpeta/Desktop BG/BG_1_Desktop.png" bg_desktop.png

cp "/home/elgran/Downloads/Landing_Carpeta/Pantalla_2_TitularAnotaTusDatos.png" titular_anota_datos.png
cp "/home/elgran/Downloads/Landing_Carpeta/Pantalla_2_Titular_Y Comienza a Participar.png" titular_y_comienza.png
cp "/home/elgran/Downloads/Landing_Carpeta/Pantalla_3_Titular.png" titular_jugando.png
cp "/home/elgran/Downloads/Landing_Carpeta/Pantalla_4A_Titular_EresunCrack.png" titular_crack.png
cp "/home/elgran/Downloads/Landing_Carpeta/Pantalla_4B_TitularFallaste.png" titular_fallaste.png

cp "/home/elgran/Downloads/Landing_Carpeta/Pantalla_1_Button Empezar.png" btn_empezar.png
cp "/home/elgran/Downloads/Landing_Carpeta/Pantalla_2_Button_Enviar.png" btn_enviar.png
cp "/home/elgran/Downloads/Landing_Carpeta/Pantalla_3_ButtonAdivinar.png" btn_adivinar.png
cp "/home/elgran/Downloads/Landing_Carpeta/Pantalla_4A_ButtonFinalizar.png" btn_finalizar_a.png
cp "/home/elgran/Downloads/Landing_Carpeta/Pantalla_4B_ButtonFinalizar.png" btn_finalizar_b.png
cp "/home/elgran/Downloads/Landing_Carpeta/Pantalla_2_IconUpload.png" icon_upload.png
```

- [ ] **Step 2: Verify all 14 files landed**

```bash
ls /home/elgran/Projects/raffle-campaign/campaigns/static/campaigns/landing/ | wc -l
```

Expected: `14`

```bash
ls /home/elgran/Projects/raffle-campaign/campaigns/static/campaigns/landing/
```

Expected (alphabetical): `bg_desktop.png  bg_mobile_steps.png  bg_mobile_welcome.png  btn_adivinar.png  btn_empezar.png  btn_enviar.png  btn_finalizar_a.png  btn_finalizar_b.png  icon_upload.png  titular_anota_datos.png  titular_crack.png  titular_fallaste.png  titular_jugando.png  titular_y_comienza.png`

- [ ] **Step 3: Run collectstatic + curl-verify each file is served by the runserver**

```bash
docker exec raffle-web python manage.py collectstatic --noinput 2>&1 | tail -3
```

Expected: ends with `14 static files copied to '/app/staticfiles', N unmodified.` (the 14 new ones plus whatever the prior count was).

```bash
for f in bg_desktop.png bg_mobile_steps.png bg_mobile_welcome.png \
         btn_adivinar.png btn_empezar.png btn_enviar.png \
         btn_finalizar_a.png btn_finalizar_b.png icon_upload.png \
         titular_anota_datos.png titular_crack.png titular_fallaste.png \
         titular_jugando.png titular_y_comienza.png; do
  printf "%-40s " "$f"
  curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8500/static/campaigns/landing/$f"
done
```

Expected: every line ends with `200`.

- [ ] **Step 4: Commit + push**

```bash
cd /home/elgran/Projects/raffle-campaign
git add campaigns/static/campaigns/landing/
git commit -m "feat(landing): add Futboleros redesign assets (14 PNGs)"
git push origin main
```

---

## Task 2: Welcome step rewrite (markup + BG + .btn-image CSS) — TDD

**Files:**
- Create: `campaigns/tests/test_submission_form_redesign.py`
- Modify: `campaigns/templates/campaigns/submission_form.html` (welcome step markup, mobile welcome BG, new `.btn-image` CSS)

- [ ] **Step 1: Write the failing test**

Create `campaigns/tests/test_submission_form_redesign.py`:

```python
"""Smoke tests for the Futboleros submission form redesign.

Spec: docs/superpowers/specs/2026-05-11-submission-ui-redesign.md
Plan: docs/superpowers/plans/2026-05-12-submission-ui-redesign.md

These tests assert that the right asset paths appear in the rendered HTML
of the public submission form. They do NOT exercise the form-submission
flow itself (that is covered by the existing per-campaign UX, untouched
by this redesign).
"""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from campaigns.models import Campaign


def _open_campaign(slug="futboleros"):
    now = timezone.now()
    return Campaign.objects.create(
        name="Futboleros Test",
        slug=slug,
        description="Test campaign for the submission UI redesign tests.",
        start_date=now - timedelta(days=1),
        end_date=now + timedelta(days=7),
        is_active=True,
        validate_submission_code=False,
        allow_multiple_submissions=False,
    )


class SubmissionFormRedesignWelcomeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.campaign = _open_campaign()

    def test_welcome_step_uses_new_bg_and_drops_legacy_composition(self):
        url = reverse("submission_form", kwargs={"campaign_slug": self.campaign.slug})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        # New welcome BG referenced
        self.assertIn("campaigns/landing/bg_mobile_welcome.png", body)
        # New EMPEZAR button asset referenced
        self.assertIn("campaigns/landing/btn_empezar.png", body)
        # Legacy welcome composition assets are gone
        self.assertNotIn("campaigns/img/goool.png", body)
        self.assertNotIn("campaigns/img/con.png", body)
        # And the legacy class names are not in the welcome step markup
        self.assertNotIn('class="welcome-headline"', body)
        self.assertNotIn('class="welcome-pill"', body)
        self.assertNotIn('class="welcome-gol"', body)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_submission_form_redesign.SubmissionFormRedesignWelcomeTests -v 2
```

Expected: FAIL — the new BG path isn't in the response yet (welcome still references `bg_1.webp` and the old composition classes).

- [ ] **Step 3: Swap the mobile welcome BG**

Open `campaigns/templates/campaigns/submission_form.html`. Find around line 65–67:

**Before:**

```django
    .stage[data-step="welcome"] {
      background-image: url("{% static 'campaigns/img/bg_1.webp' %}");
    }
```

**After:**

```django
    .stage[data-step="welcome"] {
      background-image: url("{% static 'campaigns/landing/bg_mobile_welcome.png' %}");
    }
```

- [ ] **Step 4: Replace the welcome step markup**

Still in `campaigns/templates/campaigns/submission_form.html`. Find the welcome `<section>` (lines ~447–459):

**Before:**

```django
  <!-- Step 1: Welcome -->
  <section class="step is-active welcome" data-step="welcome">
    <h1 class="welcome-headline">¡BIENVENIDO!</h1>
    <div class="welcome-pill">ESTÁS A PUNTO DE ANOTAR UN</div>
    <img class="welcome-gol" src="{% static 'campaigns/img/goool.png' %}" alt="GOOOOOL">
    <div class="welcome-con" aria-hidden="true">
      <img src="{% static 'campaigns/img/con.png' %}" alt="CON">
    </div>
    <div class="welcome-spacer"></div>
    <div class="welcome-cta">
      <button type="button" class="btn btn-white btn-wide" data-go="form">EMPEZAR</button>
    </div>
  </section>
```

**After:**

```django
  <!-- Step 1: Welcome -->
  <section class="step is-active welcome" data-step="welcome">
    <div class="welcome-spacer"></div>
    <div class="welcome-cta">
      <button type="button" class="btn-image btn-empezar" data-go="form" aria-label="Empezar">
        <img src="{% static 'campaigns/landing/btn_empezar.png' %}" alt="">
      </button>
    </div>
  </section>
```

The "¡BIENVENIDO!" text and the bike + logo are baked into `bg_mobile_welcome.png`, so no separate DOM elements are needed.

- [ ] **Step 5: Add the `.btn-image` CSS rule**

Still in `campaigns/templates/campaigns/submission_form.html`. The existing `<style>` block contains a `/* === Buttons === */` section starting around line 308. Append this new rule INSIDE the `<style>` block, immediately AFTER the existing `.btn-wide` rule (around line 338, you'll see `.btn-block { display: flex; ... }` and `.btn-wide  { min-width: 180px; }`):

```css
    /* === Image buttons (welcome EMPEZAR uses a designer-exported PNG) === */
    .btn-image {
      background: transparent;
      border: 0;
      padding: 0;
      cursor: pointer;
      display: block;
      margin: 0 auto;
    }

    .btn-image img {
      display: block;
      width: 100%;
      max-width: min(70%, 280px);
      height: auto;
      filter: drop-shadow(0 6px 14px rgba(0,0,0,.18));
      transition: transform 0.15s ease;
    }

    .btn-image:hover img,
    .btn-image:focus img {
      transform: translateY(-1px) scale(1.02);
    }

    .btn-image:active img {
      transform: translateY(0) scale(1);
    }
```

- [ ] **Step 6: Run the welcome test to verify it passes**

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_submission_form_redesign.SubmissionFormRedesignWelcomeTests -v 2
```

Expected: 1 test passes.

Run the full suite to confirm no regressions:

```bash
docker exec raffle-web python manage.py test -v 1
```

Expected: every test passes (108 prior + 1 new = 109).

- [ ] **Step 7: Commit + push**

```bash
git add campaigns/tests/test_submission_form_redesign.py campaigns/templates/campaigns/submission_form.html
git commit -m "feat(landing): rewrite welcome step (new BG, EMPEZAR image button)"
git push origin main
```

---

## Task 3: Step titulars + steps BG + `.titular` CSS — TDD

**Files:**
- Modify: `campaigns/templates/campaigns/submission_form.html`
- Modify: `campaigns/tests/test_submission_form_redesign.py` (append a new test class)

- [ ] **Step 1: Append failing tests for the four step titulars**

Append to `campaigns/tests/test_submission_form_redesign.py`:

```python


class SubmissionFormRedesignTitularsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.campaign = _open_campaign(slug="futboleros-titulars")

    def test_form_step_uses_new_titulars(self):
        url = reverse("submission_form", kwargs={"campaign_slug": self.campaign.slug})
        body = self.client.get(url).content.decode()
        self.assertIn("campaigns/landing/titular_anota_datos.png", body)
        self.assertIn("campaigns/landing/titular_y_comienza.png", body)
        # Legacy CSS-rendered pill headings are gone from the form step
        self.assertNotIn(">ANOTA TUS DATOS<", body)
        self.assertNotIn(">Y COMIENZA A PARTICIPAR<", body)

    def test_trivia_step_uses_new_titular(self):
        url = reverse("submission_form", kwargs={"campaign_slug": self.campaign.slug})
        body = self.client.get(url).content.decode()
        self.assertIn("campaigns/landing/titular_jugando.png", body)
        self.assertNotIn("campaigns/img/title_jugando.png", body)

    def test_success_and_fail_use_new_titulars(self):
        url = reverse("submission_form", kwargs={"campaign_slug": self.campaign.slug})
        body = self.client.get(url).content.decode()
        self.assertIn("campaigns/landing/titular_crack.png", body)
        self.assertIn("campaigns/landing/titular_fallaste.png", body)
        self.assertNotIn("campaigns/img/title_crack.png", body)
        self.assertNotIn("campaigns/img/title_fallaste.png", body)

    def test_steps_use_new_blurred_stadium_bg(self):
        url = reverse("submission_form", kwargs={"campaign_slug": self.campaign.slug})
        body = self.client.get(url).content.decode()
        self.assertIn("campaigns/landing/bg_mobile_steps.png", body)
        self.assertNotIn("campaigns/img/bg_2.webp", body)
```

- [ ] **Step 2: Run the new tests to verify they fail**

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_submission_form_redesign.SubmissionFormRedesignTitularsTests -v 2
```

Expected: 4 failures — none of the new asset paths are wired in yet; legacy pill headings and `bg_2.webp` still render.

- [ ] **Step 3: Swap the mobile steps BG**

In `campaigns/templates/campaigns/submission_form.html`, find around line 70–75:

**Before:**

```django
    .stage[data-step="form"],
    .stage[data-step="trivia"],
    .stage[data-step="success"],
    .stage[data-step="fail"] {
      background-image: url("{% static 'campaigns/img/bg_2.webp' %}");
    }
```

**After:**

```django
    .stage[data-step="form"],
    .stage[data-step="trivia"],
    .stage[data-step="success"],
    .stage[data-step="fail"] {
      background-image: url("{% static 'campaigns/landing/bg_mobile_steps.png' %}");
    }
```

- [ ] **Step 4: Add the `.titular` and `.titular-stack` CSS rules**

In `campaigns/templates/campaigns/submission_form.html`, find the existing `.title-img` rule (lines ~187–193). REPLACE it with the new rules:

**Before:**

```css
    /* === Title images used on slides 3 / 4 / 5 === */
    .title-img {
      display: block;
      width: 100%;
      max-width: min(96%, 420px);
      height: auto;
      margin: 7% auto 0;
      filter: drop-shadow(0 6px 14px var(--red-shadow));
    }
```

**After:**

```css
    /* === Designer-exported titulars (form / trivia / success / fail) === */
    .titular {
      display: block;
      width: 100%;
      max-width: min(96%, 420px);
      height: auto;
      margin: 7% auto 0;
      filter: drop-shadow(0 6px 14px var(--red-shadow));
    }

    .titular-stack {
      display: flex;
      flex-direction: column;
      gap: 6px;
      align-items: center;
      margin-top: 7%;
    }

    .titular-stack .titular {
      margin-top: 0;
      max-width: min(96%, 360px);
    }
```

- [ ] **Step 5: Replace the form step's titular markup**

In `campaigns/templates/campaigns/submission_form.html`, find lines ~462–464 (the form step's two pill-heading elements):

**Before:**

```django
  <!-- Step 2: Form -->
  <section class="step" data-step="form">
    <h1 class="pill-heading">ANOTA TUS DATOS</h1>
    <h2 class="pill-heading">Y COMIENZA A PARTICIPAR</h2>
```

**After:**

```django
  <!-- Step 2: Form -->
  <section class="step" data-step="form">
    <div class="titular-stack">
      <img class="titular" src="{% static 'campaigns/landing/titular_anota_datos.png' %}" alt="Anota tus datos">
      <img class="titular" src="{% static 'campaigns/landing/titular_y_comienza.png' %}" alt="Y comienza a participar">
    </div>
```

- [ ] **Step 6: Replace the trivia step's titular**

In `campaigns/templates/campaigns/submission_form.html`, find line ~538:

**Before:**

```django
    <img class="title-img" src="{% static 'campaigns/img/title_jugando.png' %}" alt="¡Ya estás jugando!">
```

**After:**

```django
    <img class="titular" src="{% static 'campaigns/landing/titular_jugando.png' %}" alt="¡Ya estás jugando!">
```

- [ ] **Step 7: Replace the success and fail step titulars**

Find lines ~574 and ~583:

**Before (success step, line ~574):**

```django
    <img class="title-img" src="{% static 'campaigns/img/title_crack.png' %}" alt="¡Eres un crack!">
```

**After:**

```django
    <img class="titular" src="{% static 'campaigns/landing/titular_crack.png' %}" alt="¡Eres un crack!">
```

**Before (fail step, line ~583):**

```django
    <img class="title-img" src="{% static 'campaigns/img/title_fallaste.png' %}" alt="¡Fallaste!">
```

**After:**

```django
    <img class="titular" src="{% static 'campaigns/landing/titular_fallaste.png' %}" alt="¡Fallaste!">
```

- [ ] **Step 8: Run the titular tests to verify they pass**

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_submission_form_redesign.SubmissionFormRedesignTitularsTests -v 2
```

Expected: 4 tests pass.

Full suite:

```bash
docker exec raffle-web python manage.py test -v 1
```

Expected: every test passes (109 prior + 4 new = 113).

- [ ] **Step 9: Commit + push**

```bash
git add campaigns/tests/test_submission_form_redesign.py campaigns/templates/campaigns/submission_form.html
git commit -m "feat(landing): swap step titulars + steps BG to new designer assets"
git push origin main
```

---

## Task 4: Desktop layout media query — TDD

**Files:**
- Modify: `campaigns/templates/campaigns/submission_form.html`
- Modify: `campaigns/tests/test_submission_form_redesign.py`

- [ ] **Step 1: Append the failing test for the desktop layout**

Append to `campaigns/tests/test_submission_form_redesign.py`:

```python


class SubmissionFormRedesignDesktopTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.campaign = _open_campaign(slug="futboleros-desktop")

    def test_desktop_bg_referenced_in_response(self):
        # The inline <style> block contains the desktop media query that
        # references bg_desktop.png as the body background.
        url = reverse("submission_form", kwargs={"campaign_slug": self.campaign.slug})
        body = self.client.get(url).content.decode()
        self.assertIn("campaigns/landing/bg_desktop.png", body)
        # And the desktop breakpoint is at 768px
        self.assertIn("min-width: 768px", body)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_submission_form_redesign.SubmissionFormRedesignDesktopTests -v 2
```

Expected: FAIL — `bg_desktop.png` is not referenced; the existing `@media` block uses `min-width: 720px`.

- [ ] **Step 3: Replace the existing 720px media query with the new 768px desktop layout**

In `campaigns/templates/campaigns/submission_form.html`, find the existing media query block around lines 77–89:

**Before:**

```css
    @media (min-width: 720px) {
      body {
        display: grid;
        place-items: center;
        padding: 24px 0;
      }
      .stage {
        min-height: min(900px, calc(100dvh - 48px));
        border-radius: 32px;
        overflow: hidden;
        box-shadow: 0 30px 80px rgba(0,0,0,.35);
      }
    }
```

**After:**

```css
    @media (min-width: 768px) {
      body {
        background: #0e6dc2 url("{% static 'campaigns/landing/bg_desktop.png' %}") center center / cover no-repeat fixed;
        overflow-x: hidden;
        padding: 0;
        display: block;
      }

      .stage,
      .stage[data-step="welcome"],
      .stage[data-step="form"],
      .stage[data-step="trivia"],
      .stage[data-step="success"],
      .stage[data-step="fail"] {
        background: transparent;
        background-image: none;
        box-shadow: none;
        border-radius: 0;
        max-width: none;
        min-height: 100dvh;
        margin: 0;
        padding: 0;
        display: flex;
        align-items: center;
        justify-content: flex-end;
      }

      .step {
        width: 100%;
        max-width: 480px;
        margin-right: clamp(24px, 6vw, 96px);
        padding: 24px;
        flex: 0 1 auto;
      }

      .welcome {
        align-items: center;
        justify-content: center;
      }

      .welcome .welcome-spacer { display: none; }

      .titular {
        margin-top: 0;
      }

      .titular-stack {
        margin-top: 0;
      }

      .card {
        margin-top: 18px;
      }
    }
```

Key behaviors of this block:
- The body's background becomes `bg_desktop.png` covering the full viewport (`background-attachment: fixed` so it doesn't scroll inside the form card).
- Each `.stage` becomes transparent and uses `flex` to push the active step's content to the right side of the viewport.
- Each `.step` is capped at 480px wide with right-side margin clamped between 24px and 96px depending on viewport width.
- The welcome step's spacer is hidden (no longer needed; flex centering replaces it).
- The titular's `margin-top: 7%` (mobile-relative) is reset so the titular sits at the top of the right column.
- The mobile `bg_mobile_welcome.png` and `bg_mobile_steps.png` assignments at the `.stage[data-step="…"]` selectors are explicitly set to `none` here so the mobile BGs don't conflict with the desktop BG.

- [ ] **Step 4: Restart the container so the template change is picked up**

```bash
RAFFLE_CAMPAIGN_WEB_PORT=8500 docker compose restart web
sleep 4
```

- [ ] **Step 5: Run the desktop test to verify it passes**

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_submission_form_redesign.SubmissionFormRedesignDesktopTests -v 2
```

Expected: 1 test passes.

Full suite:

```bash
docker exec raffle-web python manage.py test -v 1
```

Expected: every test passes (113 prior + 1 new = 114).

- [ ] **Step 6: Commit + push**

```bash
git add campaigns/tests/test_submission_form_redesign.py campaigns/templates/campaigns/submission_form.html
git commit -m "feat(landing): add desktop layout (>=768px, bike+logo BG with right-column form)"
git push origin main
```

---

## Task 5: Manual visual smoke + final verification

**Files:**
- (verification only)

- [ ] **Step 1: Confirm clean test run**

```bash
docker exec raffle-web python manage.py test -v 1
```

Expected: every test passes (~114 total).

- [ ] **Step 2: Restart the container and confirm the live submission page returns 200**

```bash
RAFFLE_CAMPAIGN_WEB_PORT=8500 docker compose restart web
sleep 4
curl -s -o /dev/null -w "submission_form: %{http_code}\n" http://localhost:8500/submit/futboleros-bn-hn/
```

Expected: `submission_form: 200`.

Confirm the new asset paths actually appear in the rendered HTML:

```bash
curl -s http://localhost:8500/submit/futboleros-bn-hn/ | grep -oE "campaigns/landing/[a-z_]+\.png" | sort -u
```

Expected (alphabetical, all 7 referenced files):

```
campaigns/landing/bg_desktop.png
campaigns/landing/bg_mobile_steps.png
campaigns/landing/bg_mobile_welcome.png
campaigns/landing/btn_empezar.png
campaigns/landing/titular_anota_datos.png
campaigns/landing/titular_crack.png
campaigns/landing/titular_fallaste.png
campaigns/landing/titular_jugando.png
campaigns/landing/titular_y_comienza.png
```

(9 unique files; the button assets `btn_enviar`, `btn_adivinar`, `btn_finalizar_*`, and `icon_upload` are imported into the asset folder but not yet referenced by the template — kept for future use per the spec.)

Confirm none of the legacy paths render anymore:

```bash
curl -s http://localhost:8500/submit/futboleros-bn-hn/ | grep -oE "campaigns/img/(bg_[12]\.webp|goool|con|title_[a-z]+)\.[a-z]+" || echo "✓ No legacy asset references"
```

Expected: `✓ No legacy asset references`.

- [ ] **Step 3: Manual visual smoke check in a browser**

Open these URLs in a real browser and visually confirm:

**Mobile viewport (iPhone 13 Pro: 390×844 in DevTools):**
- `http://localhost:8500/submit/futboleros-bn-hn/` — bike + logo + sky + "¡BIENVENIDO!" all baked into the BG, white pill EMPEZAR button at the bottom. Tap it.
- The form step appears with the blurred stadium BG, red `ANOTA TUS DATOS` and `Y COMIENZA A PARTICIPAR` image titulars stacked, white form card with all six fields (Nombre, Apellidos, Teléfono, Correo, Lugar dropdown, Suba aquí una foto upload area). Submit a test entry.
- Trivia step shows red `¡YA ESTÁS JUGANDO!` titular over the same blurred BG, three radio options, red ADIVINAR button. Pick the third option (correct: "Canadá / Estados Unidos / México") and tap.
- Success step shows red `¡ERES UN CRACK!` titular + small white card "Esperamos que pronto cantes tu gol." + red FINALIZAR button.
- Optional: re-do the entry and pick a wrong answer to see the fail step (red `¡FALLASTE!` titular + small white card + red FINALIZAR).

**Desktop viewport (1440×900):**
- Same URL — full-viewport panoramic stadium with bike on the left half, "La Nube..." logo top-left, all part of `bg_desktop.png`. The right column shows the EMPEZAR image button vertically centered.
- Click EMPEZAR — the bike + logo BG stays constant, the right column swaps to the form titular + white card.
- Walk through trivia + result — BG never changes, only the right column content.

If any visual surprise appears (squashed BG, oversized titulars, button not clickable), document the issue and pause before Step 4.

- [ ] **Step 4: Confirm all commits pushed**

```bash
cd /home/elgran/Projects/raffle-campaign
git status
git log --oneline origin/main..HEAD || echo "All pushed"
```

Expected: nothing to commit, no unpushed commits.

- [ ] **Step 5: Update project memory**

Append a new line to `/home/elgran/.claude/projects/-home-elgran-Projects-raffle-campaign/memory/MEMORY.md`:

```markdown
- [Submission UI redesign (Futboleros)](project_submission_ui_redesign.md) — new bike+logo BG, image titulars, desktop layout at 768px (shipped 2026-05-12)
```

Create `/home/elgran/.claude/projects/-home-elgran-Projects-raffle-campaign/memory/project_submission_ui_redesign.md`:

```markdown
---
name: Submission UI redesign (Futboleros campaign)
description: Status of the "La Nube que te mueve... y te lleva al gol" landing redesign for the existing per-campaign submission form
type: project
---
**Status as of 2026-05-12: SHIPPED to `main`.**

**What's in place:**
- 14 designer-exported PNGs at `campaigns/static/campaigns/landing/` (bg_mobile_welcome, bg_mobile_steps, bg_desktop, 5 titulars, 5 buttons, icon_upload).
- `submission_form.html` welcome step now shows the full-bleed bike+logo BG + a single EMPEZAR image button (no separate ¡BIENVENIDO!/GOOOOL composition).
- Form/trivia/success/fail steps use designer-exported `<img>` titulars (`titular_anota_datos.png`, `titular_y_comienza.png`, `titular_jugando.png`, `titular_crack.png`, `titular_fallaste.png`) instead of CSS-rendered Andreas-font text.
- New `@media (min-width: 768px)` block: full-viewport `bg_desktop.png` (bike + logo baked in on the left), right column with the active step's content. Mobile layout untouched below 768px.
- 6 substring tests in `campaigns/tests/test_submission_form_redesign.py` lock down which assets are referenced.

**Why:** The customer (Nube Blanca y Rosal Honduras) approved a new design for their motorcycle giveaway landing. The old composition (multi-element welcome with GOOOOL + CON elements + Andreas-font pill titulars) no longer matches their brief.

**Spec:** `docs/superpowers/specs/2026-05-11-submission-ui-redesign.md`
**Plan:** `docs/superpowers/plans/2026-05-12-submission-ui-redesign.md`

**Deferred (in the spec's Out of Scope):**
- Per-campaign template management system (today this template is still hand-edited; the project_per_campaign_templates.md workstream tracks the future system).
- Removal of the now-unreferenced legacy assets in `campaigns/static/campaigns/img/` (bg_1.webp, bg_2.webp, goool.png, con.png, title_jugando.png, title_crack.png, title_fallaste.png) — kept for safety, can be deleted in a follow-up sweep.
- Image button assets (btn_enviar.png, btn_adivinar.png, btn_finalizar_*.png) are in the asset folder but unused by the live template; the existing CSS buttons handle disabled / loading states better than static images.
- Animations between steps.
- WebP/AVIF re-encoding of the new PNGs.
```

The memory directory already exists. Write directly. No git commit needed (memory is outside the project repo).

---

## Verification Summary

After all 5 tasks:

| Surface | Behavior |
|---|---|
| `/submit/futboleros-bn-hn/` (mobile, < 768px) | Welcome step shows new bike+logo BG with EMPEZAR image button. Form/trivia/result steps show new image titulars over the new blurred stadium BG. |
| `/submit/futboleros-bn-hn/` (desktop, ≥ 768px) | Single panoramic `bg_desktop.png` covers the viewport. Right column shows the active step's content with no left-column changes between steps. |
| Form submission flow | Unchanged — view, fields, AJAX submit, success redirect all work identically. |
| Trivia logic | Unchanged — same correct answer (option index 2). |
| Legacy assets | `campaigns/static/campaigns/img/` files (bg_1.webp, bg_2.webp, goool.png, con.png, title_*.png) stay on disk but are no longer referenced. |

Tests: 6 new in `campaigns/tests/test_submission_form_redesign.py` covering welcome / form titulars / trivia titular / success+fail titulars / steps BG / desktop BG.

No model, view, URL, form, or admin changes. Plan touches one template + one new test file + one new asset folder.

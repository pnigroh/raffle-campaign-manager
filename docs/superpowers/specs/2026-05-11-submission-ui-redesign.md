# Submission UI redesign for the Futboleros campaign — Design Spec

**Status:** approved 2026-05-11
**Scope:** update `campaigns/templates/campaigns/submission_form.html` to match the new "La Nube que te mueve… y te lleva al gol" landing design (10-page Illustrator file, 5 mobile + 5 desktop screens). Add a desktop layout (current code is mobile-only). Swap legacy welcome composition for the new bike-baked BG and image titulars.
**Out of scope (deferred):** per-campaign template management system, brand-token integration, step transition animations, alternate success/fail backgrounds, removal of legacy assets in `campaigns/static/campaigns/img/`.

---

## Summary

The current public submission form (`campaigns/templates/campaigns/submission_form.html`) is a mobile-only 5-step state machine themed for an earlier draft of the Futboleros giveaway. The customer has delivered an updated 10-page design (mobile + desktop) that:

1. Replaces the welcome composition (multiple stacked text/image elements) with a single bike-and-logo background plus an `EMPEZAR` button overlay.
2. Adds a desktop layout (>= 768px) where the bike fills the left half and the form/trivia/result content sits in a fixed-width right column.
3. Switches in-text titulars (`ANOTA TUS DATOS / Y COMIENZA A PARTICIPAR`, `¡YA ESTÁS JUGANDO!`, `¡ERES UN CRACK!`, `¡FALLASTE!`) from CSS-rendered Andreas-font text to designer-exported PNG images so the result is byte-faithful to the source file.

The 5-step state machine (welcome → form → trivia → success / fail), the form fields (`first_name, last_name, phone, email, store, image_1`), and the AJAX submit flow are unchanged because they already match the design's interaction model exactly. No view, model, URL, or migration changes are needed.

## User Story

As Marta, an entrant on a phone:
- I open `/submit/futboleros-bn-hn/`. The full screen is a vivid sky-and-stadium photo with the motorbike on the grass and the "La Nube que te mueve… y te lleva al gol" logo at the top — all baked into a single BG image. A single white-pill `EMPEZAR` button floats at the bottom. I tap it.
- The screen swaps to a blurred-stadium background. A red "ANOTA TUS DATOS / Y COMIENZA A PARTICIPAR" image-titular sits at the top; below it is a white card with the same fields I'd see today (Nombre, Apellidos, Teléfono, Correo, Lugar, Suba aquí una foto). I fill it out and tap the red `ENVIAR` button.
- The trivia step appears with the red `¡YA ESTÁS JUGANDO!` image-titular and the multiple-choice question. I pick an answer and tap `ADIVINAR`.
- I see either `¡ERES UN CRACK!` (success) or `¡FALLASTE!` (fail), each with a red `FINALIZAR` button.

As Mariano, an entrant on a 1920×1080 laptop:
- The same URL renders a panoramic stadium scene with the motorbike on the left half and the logo top-left — all baked into a single desktop BG image. The right third of the viewport holds the active step's content (welcome → form → trivia → result), styled as a vertically-centered column with the same titular pill + white card pattern from mobile, just narrower (~480px max).
- The bike + logo stay constant across all five steps; only the right-column content changes.

## Architecture

### Asset placement

Add a new subfolder so the redesign assets are clearly separated from the legacy mobile-only assets, which stay in place but become unreferenced:

```
campaigns/static/campaigns/landing/
  bg_mobile_welcome.png       (1125x2436, source: Mobile BG/BG_1.png)
  bg_mobile_steps.png         (1125x2436, source: Mobile BG/BG_2.png)
  bg_desktop.png              (1920x1080, source: Desktop BG/BG_1_Desktop.png)
  titular_anota_datos.png     (518x94,    source: Pantalla_2_TitularAnotaTusDatos.png)
  titular_y_comienza.png      (720x93,    source: Pantalla_2_Titular_Y Comienza a Participar.png)
  titular_jugando.png         (958x182,   source: Pantalla_3_Titular.png)
  titular_crack.png           (959x149,   source: Pantalla_4A_Titular_EresunCrack.png)
  titular_fallaste.png        (958x149,   source: Pantalla_4B_TitularFallaste.png)
  btn_empezar.png             (495x118,   source: Pantalla_1_Button Empezar.png)
  btn_enviar.png              (495x118,   source: Pantalla_2_Button_Enviar.png)
  btn_adivinar.png            (494x118,   source: Pantalla_3_ButtonAdivinar.png)
  btn_finalizar_a.png         (495x118,   source: Pantalla_4A_ButtonFinalizar.png)
  btn_finalizar_b.png         (494x118,   source: Pantalla_4B_ButtonFinalizar.png)
  icon_upload.png             (236x204,   source: Pantalla_2_IconUpload.png)
```

Source paths are inside `~/Downloads/Landing_Carpeta/` and its `Mobile BG/` and `Desktop BG/` subfolders. Files are copied verbatim — no resizing, no recompression. Filenames are normalized (lowercase, snake_case, no spaces) for safer URL handling.

The legacy assets in `campaigns/static/campaigns/img/` (`bg_1.webp`, `bg_2.webp`, `goool.png`, `con.png`, `title_jugando.png`, `title_crack.png`, `title_fallaste.png`) remain in place but are no longer referenced. Removing them is a separate cleanup task.

### Template changes

In-place edit of `campaigns/templates/campaigns/submission_form.html`. The file already has `{% load static %}` at the top.

#### Welcome step (lines ~447–459 today)

**Today:**

```django
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
<section class="step is-active welcome" data-step="welcome">
  <div class="welcome-spacer"></div>
  <div class="welcome-cta">
    <button type="button" class="btn-image btn-empezar" data-go="form" aria-label="Empezar">
      <img src="{% static 'campaigns/landing/btn_empezar.png' %}" alt="">
    </button>
  </div>
</section>
```

The "¡BIENVENIDO!" text and the bike + logo are part of `bg_mobile_welcome.png` — no separate DOM elements needed. The `.welcome-spacer` is preserved so the EMPEZAR button stays anchored near the bottom; `flex: 1` already drives the layout.

#### Form step titular (lines ~462–464 today)

**Today:**

```django
<section class="step" data-step="form">
  <h1 class="pill-heading">ANOTA TUS DATOS</h1>
  <h2 class="pill-heading">Y COMIENZA A PARTICIPAR</h2>
```

**After:**

```django
<section class="step" data-step="form">
  <div class="titular-stack">
    <img class="titular" src="{% static 'campaigns/landing/titular_anota_datos.png' %}" alt="Anota tus datos">
    <img class="titular" src="{% static 'campaigns/landing/titular_y_comienza.png' %}" alt="Y comienza a participar">
  </div>
```

#### Trivia step titular (line ~538 today)

**Today:**

```django
<img class="title-img" src="{% static 'campaigns/img/title_jugando.png' %}" alt="¡Ya estás jugando!">
```

**After:**

```django
<img class="titular" src="{% static 'campaigns/landing/titular_jugando.png' %}" alt="¡Ya estás jugando!">
```

#### Success/Fail titulars (lines ~574, ~583 today)

**Today:**

```django
<img class="title-img" src="{% static 'campaigns/img/title_crack.png' %}" alt="¡Eres un crack!">
...
<img class="title-img" src="{% static 'campaigns/img/title_fallaste.png' %}" alt="¡Fallaste!">
```

**After:**

```django
<img class="titular" src="{% static 'campaigns/landing/titular_crack.png' %}" alt="¡Eres un crack!">
...
<img class="titular" src="{% static 'campaigns/landing/titular_fallaste.png' %}" alt="¡Fallaste!">
```

#### Buttons

The CSS-rendered text buttons (`<button class="btn">…</button>`) stay as-is — they handle disabled states, loading spinners, and form submission semantics that PNG buttons can't. The PNG button assets (`btn_enviar.png`, `btn_adivinar.png`, etc.) are imported into the asset folder but are unused by the live template. They are kept for future use (e.g. if a marketing variant needs to swap in pixel-faithful buttons). The EMPEZAR button is the one exception — it's a static "next step" trigger with no form semantics, so an `<img>`-inside-`<button>` works cleanly.

### CSS changes

#### Welcome BG swap

**Today** (lines ~65–67):

```css
.stage[data-step="welcome"] {
  background-image: url("{% static 'campaigns/img/bg_1.webp' %}");
}
```

**After:**

```css
.stage[data-step="welcome"] {
  background-image: url("{% static 'campaigns/landing/bg_mobile_welcome.png' %}");
}
```

#### Steps BG swap

**Today** (lines ~70–75):

```css
.stage[data-step="form"],
.stage[data-step="trivia"],
.stage[data-step="success"],
.stage[data-step="fail"] {
  background-image: url("{% static 'campaigns/img/bg_2.webp' %}");
}
```

**After:**

```css
.stage[data-step="form"],
.stage[data-step="trivia"],
.stage[data-step="success"],
.stage[data-step="fail"] {
  background-image: url("{% static 'campaigns/landing/bg_mobile_steps.png' %}");
}
```

#### New `.titular` and `.titular-stack` rules

Added to the `<style>` block. Replace the existing `.title-img` rule (lines ~187–193) with:

```css
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
}
```

The legacy `.title-img` and `.pill-heading` rules can stay in the file (zero references after this change) and be removed in a follow-up cleanup.

#### New `.btn-image` rule

For the welcome EMPEZAR `<button>` wrapper:

```css
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

#### Desktop layout (>= 768px)

Append a new media query block at the end of the existing `<style>` section, just before the closing `</style>` tag. The existing 720px media query is upgraded to 768px and replaced with the new desktop layout:

**Replace** the existing block (lines ~77–89):

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

**With:**

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

  .card {
    margin-top: 18px;
  }
}
```

Key behaviors:
- The body's BG becomes `bg_desktop.png` covering the full viewport (with `background-attachment: fixed` so it doesn't scroll inside the form card).
- Each `.stage` becomes transparent and uses `flex` to push the active step's content to the right side of the viewport.
- Each `.step` is capped at 480px wide with right-side margin clamped between 24px and 96px depending on viewport width.
- The welcome step's spacer is hidden (no longer needed; flex centering replaces it).
- The titular's `margin-top: 7%` (which is mobile-relative) is reset so the titular sits at the top of the right column.
- The mobile `bg_mobile_welcome.png` and `bg_mobile_steps.png` assignments at the `.stage[data-step="…"]` selectors are explicitly set to `none` here so the mobile BGs don't conflict with the desktop BG.

### Image accessibility

- All `<img>` titulars have non-empty Spanish `alt` text matching the visible content.
- The EMPEZAR button uses `aria-label="Empezar"` on the wrapping `<button>` and `alt=""` on the inner `<img>` (the image is decorative since the button itself carries the accessible name).

### Browser support

Bootstrap 5.3.2 already targets the same matrix (Chrome/Firefox/Edge/Safari last-2). No new CSS features are introduced beyond `clamp()`, `dvh`, and `flex` which are all already used by the existing template. PNG support is universal.

## Error handling

No new error paths. The form's existing AJAX submit handler, error display in `#formErrors`, and `is-invalid` field highlighting all continue to work — none of those code paths is touched.

If a PNG asset fails to load (404, network), the `<img>` shows its `alt` text. The button-image fallback would render the empty `aria-label` — a future hardening might add a CSS background-color fallback. Out of scope for this task.

## Testing

The submission_form is per-campaign-customized and is excluded from the platform's smoke test suite (per the existing `project_per_campaign_templates.md` memo). However, this redesign deserves its own targeted regression coverage:

**`campaigns/tests/test_submission_form_redesign.py`** (new file, ~5 tests):

1. `test_welcome_step_uses_new_bg_and_empezar_button` — GET the form page, assert `bg_mobile_welcome.png` is in the response and `goool.png` / `con.png` are NOT.
2. `test_form_step_renders_new_titulars` — assert `titular_anota_datos.png` and `titular_y_comienza.png` are referenced in the response.
3. `test_trivia_step_renders_new_titular` — assert `titular_jugando.png` is referenced.
4. `test_success_and_fail_titulars_present` — both `titular_crack.png` and `titular_fallaste.png` are referenced.
5. `test_desktop_bg_referenced_in_media_query` — assert `bg_desktop.png` substring appears in the response (the inline style block contains the media query).

These are HTML-substring tests — they cover "did the right files get wired in" without asserting anything about visual rendering. The existing form-submission test in `submission_form` view tests (if any) is unchanged.

Smoke test in browser is required as a final step before declaring done:
- Mobile viewport (375×812 iPhone): all 5 steps render with new BGs and titulars; EMPEZAR button image is centered at bottom of the welcome step; tapping it advances to form; form submits via AJAX; trivia and result screens look correct.
- Desktop viewport (1440×900): the `bg_desktop.png` covers the viewport with bike + logo on the left; right column shows the active step's titular + card; advancing through all 5 steps keeps the BG constant.

## File diff summary

**Add (15 PNG files):**
- `campaigns/static/campaigns/landing/bg_mobile_welcome.png`
- `campaigns/static/campaigns/landing/bg_mobile_steps.png`
- `campaigns/static/campaigns/landing/bg_desktop.png`
- `campaigns/static/campaigns/landing/titular_anota_datos.png`
- `campaigns/static/campaigns/landing/titular_y_comienza.png`
- `campaigns/static/campaigns/landing/titular_jugando.png`
- `campaigns/static/campaigns/landing/titular_crack.png`
- `campaigns/static/campaigns/landing/titular_fallaste.png`
- `campaigns/static/campaigns/landing/btn_empezar.png`
- `campaigns/static/campaigns/landing/btn_enviar.png`
- `campaigns/static/campaigns/landing/btn_adivinar.png`
- `campaigns/static/campaigns/landing/btn_finalizar_a.png`
- `campaigns/static/campaigns/landing/btn_finalizar_b.png`
- `campaigns/static/campaigns/landing/icon_upload.png`

**Add (1 test file):**
- `campaigns/tests/test_submission_form_redesign.py`

**Modify (1 template):**
- `campaigns/templates/campaigns/submission_form.html` — welcome step markup; form/trivia/success/fail titular markup; CSS for `.titular`, `.btn-image`, the mobile BG swaps, and the new desktop media query.

**Unchanged:**
- `campaigns/views.py` — `submission_form` view processes the form identically.
- `campaigns/forms.py` — `SubmissionForm` field set unchanged.
- `campaigns/models.py` — no schema changes.
- `campaigns/urls.py` — no route changes.
- All admin / dashboard / audit / prize-CRUD code — completely unrelated.

## Migration / backward compatibility

No DB migration. No view changes. Existing in-flight submissions are unaffected. Browser caches may show the old form briefly until the new CSS loads — acceptable since the form fields and submit URL are identical and would still process correctly.

The legacy assets in `campaigns/static/campaigns/img/` stay on disk; removing them is a follow-up. They are reachable at their old URLs (`/static/campaigns/img/bg_1.webp` etc.) but no template references them after this change.

## Out of scope (deferred)

- **Per-campaign template management** — this template remains a hand-edited customer-specific file. The `project_per_campaign_templates.md` workstream will eventually let admins upload these assets via the dashboard.
- **Brand-token integration** — this template intentionally bypasses the Promo-Domo brand tokens because it's a customer-themed customer landing.
- **Step transition animations** — the design doesn't specify any. Steps still snap-swap via the existing `is-active` toggle.
- **Removing the legacy `campaigns/static/campaigns/img/` files** — kept for safety; remove in a follow-up sweep.
- **Webp re-encoding of the new PNGs** — PNGs are ~7 MB total uncompressed, ~2 MB compressed. Acceptable for a marketing landing. A future optimization pass could convert to WebP/AVIF for ~70% size reduction.
- **Server-side validation message overhaul** — the AJAX submit's error UI stays the same.

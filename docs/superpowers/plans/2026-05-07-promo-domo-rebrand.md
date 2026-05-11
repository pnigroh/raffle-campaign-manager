# Promo-Domo Rebrand Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebrand the application from "RaffleManager / Raffle Campaign Manager" to "Promo-Domo" — applying the approved dodo mascot, palette, type system, and naming changes across every customer-visible surface.

**Architecture:** A single brand stylesheet (`campaigns/static/css/brand.css`) defines palette and type tokens at `:root`. A reusable Django template partial (`_brand_assets.html`) injects fonts, brand CSS, favicon, and the dodo `<symbol>` into every top-level template; consumers reference the dodo via `<use href="#pd-dodo">`. The existing sidebar+topbar layout is preserved — brand tokens replace the legacy navy/blue palette by re-pointing the existing `--sidebar-*` / `--accent` variables to brand tokens, so most cascade work is automatic.

**Tech Stack:** Django 4.2 + Django templates, Bootstrap 5.3.2 (CDN), Bootstrap Icons (kept for non-brand icons), Google Fonts (Fraunces + Inter), inline SVG for the mascot, django-unfold for admin theming.

**Spec:** `docs/superpowers/specs/2026-05-07-promo-domo-rebrand-design.md`

---

## File Structure

**Create:**
- `campaigns/static/brand/dodo.svg` — canonical mascot, used as a downloadable asset and `<img>` fallback
- `campaigns/static/brand/dodo-light.svg` — light-fill variant for dark surfaces (Apple/Android home-screen icons, possible dark-mode follow-up)
- `campaigns/static/brand/favicon.svg` — single-file SVG favicon (modern browsers; falls back gracefully)
- `campaigns/static/css/brand.css` — palette + type tokens at `:root`, Google Fonts `@import`, base typography rules, branded utility classes (`.pd-name`, `.pd-hyphen`)
- `campaigns/templates/campaigns/_brand_assets.html` — head links partial (fonts, brand.css, favicon) + hidden inline SVG containing `<symbol id="pd-dodo">` and `<symbol id="pd-dodo-light">`. Included once per top-level template.
- `campaigns/tests/__init__.py` — empty, makes `tests` a Python package
- `campaigns/tests/test_branding.py` — Django integration smoke tests asserting brand strings on each surface

**Modify:**
- `campaigns/templates/campaigns/base.html` — head, sidebar brand area, topbar, restyled stat-cards via brand tokens
- `campaigns/templates/campaigns/login.html` — full restyle (yellow art panel + stacked lockup left, white form right) per spec
- `campaigns/templates/campaigns/submission_form.html` — public header, hero, form-card restyled with brand tokens; preserve all field names + `is-invalid` pattern
- `campaigns/templates/campaigns/dashboard.html` — only the page-header heading icon color/text; stat-card classes already cascade from base.html
- `campaigns/admin.py` — add `admin.site.site_header` / `site_title` / `index_title` after the imports
- `README.md` — replace H1 and intro paragraph

**Out of scope (per spec):**
- Renaming the Python package `campaigns/` or Django project `raffle_project/`
- The three form-design proposals in `_proposals/` (separate workstream; will adopt tokens once shipped)
- Marketing site, animated mascot, localization

---

## Task 1: Brand assets, CSS, and template partial

**Files:**
- Create: `campaigns/static/brand/dodo.svg`
- Create: `campaigns/static/brand/dodo-light.svg`
- Create: `campaigns/static/brand/favicon.svg`
- Create: `campaigns/static/css/brand.css`
- Create: `campaigns/templates/campaigns/_brand_assets.html`

- [ ] **Step 1: Create the canonical dodo SVG**

Create `campaigns/static/brand/dodo.svg` with the exact content from the spec (Storybook · Squint variant):

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" role="img" aria-label="Promo-Domo dodo mascot">
  <ellipse cx="60" cy="112" rx="32" ry="3" fill="#1F2937" opacity=".15"/>
  <ellipse cx="58" cy="80" rx="32" ry="26" fill="#374151"/>
  <ellipse cx="58" cy="86" rx="22" ry="16" fill="#6B7280"/>
  <path d="M40 70 Q 30 78 36 92 Q 46 92 50 80 Z" fill="#1F2937"/>
  <path d="M28 62 Q 18 56 16 48 Q 24 50 30 58 Z" fill="#FCD34D"/>
  <path d="M26 70 Q 12 70 10 62 Q 22 60 28 66 Z" fill="#FB7185"/>
  <path d="M28 78 Q 14 82 14 74 Q 22 70 30 74 Z" fill="#14B8A6"/>
  <rect x="50" y="102" width="5" height="10" fill="#FB7185"/>
  <rect x="66" y="102" width="5" height="10" fill="#FB7185"/>
  <path d="M46 112 L 58 112 L 56 114 L 48 114 Z" fill="#FB7185"/>
  <path d="M62 112 L 74 112 L 72 114 L 64 114 Z" fill="#FB7185"/>
  <ellipse cx="80" cy="50" rx="20" ry="22" fill="#374151"/>
  <circle cx="76" cy="30" r="3" fill="#FCD34D"/>
  <circle cx="82" cy="28" r="3" fill="#FCD34D"/>
  <circle cx="88" cy="32" r="2.5" fill="#FCD34D"/>
  <path d="M79 47 Q 84 41 89 47" stroke="#1F2937" stroke-width="2.4" fill="none" stroke-linecap="round"/>
  <path d="M80 44 Q 84 40 88 44" stroke="#1F2937" stroke-width="1" fill="none" stroke-linecap="round" opacity=".4"/>
  <ellipse cx="74" cy="58" rx="5.5" ry="3" fill="#FB7185" opacity=".7"/>
  <path d="M96 49 Q 118 50 113 68 Q 104 71 92 60 Z" fill="#FCD34D" stroke="#1F2937" stroke-width="1.5"/>
  <path d="M91 61 Q 96 67 101 61" stroke="#1F2937" stroke-width="1.6" fill="none" stroke-linecap="round"/>
  <circle cx="106" cy="55" r="0.8" fill="#1F2937"/>
</svg>
```

- [ ] **Step 2: Create the light-fill dodo variant**

Create `campaigns/static/brand/dodo-light.svg`. Identical to `dodo.svg` except the dark body fills (`#374151`) become cream (`#FEF3C7`) and the belly highlight becomes `#FFFBEB`:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" role="img" aria-label="Promo-Domo dodo mascot (light)">
  <ellipse cx="60" cy="112" rx="32" ry="3" fill="#FCD34D" opacity=".25"/>
  <ellipse cx="58" cy="80" rx="32" ry="26" fill="#FEF3C7"/>
  <ellipse cx="58" cy="86" rx="22" ry="16" fill="#FFFBEB"/>
  <path d="M40 70 Q 30 78 36 92 Q 46 92 50 80 Z" fill="#FCD34D"/>
  <path d="M28 62 Q 18 56 16 48 Q 24 50 30 58 Z" fill="#FCD34D"/>
  <path d="M26 70 Q 12 70 10 62 Q 22 60 28 66 Z" fill="#FB7185"/>
  <path d="M28 78 Q 14 82 14 74 Q 22 70 30 74 Z" fill="#14B8A6"/>
  <rect x="50" y="102" width="5" height="10" fill="#FB7185"/>
  <rect x="66" y="102" width="5" height="10" fill="#FB7185"/>
  <ellipse cx="80" cy="50" rx="20" ry="22" fill="#FEF3C7"/>
  <circle cx="76" cy="30" r="3" fill="#FCD34D"/>
  <circle cx="82" cy="28" r="3" fill="#FCD34D"/>
  <circle cx="88" cy="32" r="2.5" fill="#FCD34D"/>
  <path d="M79 47 Q 84 41 89 47" stroke="#1F2937" stroke-width="2.4" fill="none" stroke-linecap="round"/>
  <ellipse cx="74" cy="58" rx="5.5" ry="3" fill="#FB7185" opacity=".7"/>
  <path d="M96 49 Q 118 50 113 68 Q 104 71 92 60 Z" fill="#FCD34D" stroke="#1F2937" stroke-width="1.5"/>
  <path d="M91 61 Q 96 67 101 61" stroke="#1F2937" stroke-width="1.6" fill="none" stroke-linecap="round"/>
</svg>
```

- [ ] **Step 3: Create the favicon SVG**

Create `campaigns/static/brand/favicon.svg`. This is the same as `dodo.svg` but with a cream-tinted background rect so the dodo doesn't get lost on a white browser tab:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">
  <rect width="120" height="120" rx="20" fill="#FCD34D"/>
  <ellipse cx="60" cy="112" rx="32" ry="3" fill="#1F2937" opacity=".18"/>
  <ellipse cx="58" cy="80" rx="32" ry="26" fill="#374151"/>
  <ellipse cx="58" cy="86" rx="22" ry="16" fill="#6B7280"/>
  <path d="M40 70 Q 30 78 36 92 Q 46 92 50 80 Z" fill="#1F2937"/>
  <path d="M28 62 Q 18 56 16 48 Q 24 50 30 58 Z" fill="#FFFBEB"/>
  <path d="M26 70 Q 12 70 10 62 Q 22 60 28 66 Z" fill="#FB7185"/>
  <path d="M28 78 Q 14 82 14 74 Q 22 70 30 74 Z" fill="#14B8A6"/>
  <rect x="50" y="102" width="5" height="10" fill="#FB7185"/>
  <rect x="66" y="102" width="5" height="10" fill="#FB7185"/>
  <ellipse cx="80" cy="50" rx="20" ry="22" fill="#374151"/>
  <path d="M79 47 Q 84 41 89 47" stroke="#1F2937" stroke-width="2.6" fill="none" stroke-linecap="round"/>
  <ellipse cx="74" cy="58" rx="5.5" ry="3" fill="#FB7185" opacity=".7"/>
  <path d="M96 49 Q 118 50 113 68 Q 104 71 92 60 Z" fill="#FCD34D" stroke="#1F2937" stroke-width="1.6"/>
  <path d="M91 61 Q 96 67 101 61" stroke="#1F2937" stroke-width="1.6" fill="none" stroke-linecap="round"/>
</svg>
```

- [ ] **Step 4: Create the brand stylesheet**

Create `campaigns/static/css/brand.css`:

```css
/* ============================================================
   Promo-Domo brand tokens & base typography
   Source of truth for palette + type. Loaded before page CSS
   so existing :root variables in templates can reference --pd-*.
   ============================================================ */

@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,800;9..144,900&family=Inter:wght@400;500;600;700&display=swap');

:root {
  /* Palette */
  --pd-yellow: #FCD34D;
  --pd-coral: #FB7185;
  --pd-coral-deep: #E11D48;
  --pd-teal: #14B8A6;
  --pd-cream: #FEF3C7;
  --pd-cream-soft: #FFFBEB;
  --pd-ink: #1F2937;
  --pd-ink-soft: #4B5563;
  --pd-gray: #9CA3AF;
  --pd-line: #FDE68A;

  /* Type */
  --pd-font-display: 'Fraunces', Georgia, 'Times New Roman', serif;
  --pd-font-body: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
}

/* Body baseline — overridden by page-specific rules where needed */
body {
  font-family: var(--pd-font-body);
}

/* Branded wordmark utility — apply to <span> wrapping "Promo-Domo" */
.pd-name {
  font-family: var(--pd-font-display);
  font-weight: 800;
  letter-spacing: -0.025em;
  color: var(--pd-ink);
  line-height: 1;
}

.pd-hyphen {
  color: var(--pd-coral);
}

/* Display headings (Fraunces) */
.pd-display {
  font-family: var(--pd-font-display);
  font-weight: 800;
  letter-spacing: -0.02em;
}

/* Hide-but-keep-in-DOM helper for the inline SVG <symbol> defs block */
.pd-svg-defs {
  position: absolute;
  width: 0;
  height: 0;
  overflow: hidden;
}
```

- [ ] **Step 5: Create the brand assets template partial**

Create `campaigns/templates/campaigns/_brand_assets.html`. This is included in `<head>` of every top-level template (base.html, login.html, submission_form.html). Two responsibilities: (1) link brand CSS + favicon, (2) define inline `<symbol>` for the dodo. The `<symbol>` block uses `class="pd-svg-defs"` so it doesn't render, but `<use href="#pd-dodo">` works anywhere on the page.

```django
{% load static %}

{# Brand stylesheet (loads Google Fonts + tokens) #}
<link rel="stylesheet" href="{% static 'css/brand.css' %}">

{# Favicon — modern browsers use SVG, others fall back to nothing (acceptable) #}
<link rel="icon" type="image/svg+xml" href="{% static 'brand/favicon.svg' %}">
<link rel="apple-touch-icon" href="{% static 'brand/favicon.svg' %}">

{# Inline SVG <symbol> defs — reference with <svg><use href="#pd-dodo"/></svg> #}
<svg xmlns="http://www.w3.org/2000/svg" class="pd-svg-defs" aria-hidden="true">
  <defs>
    <symbol id="pd-dodo" viewBox="0 0 120 120">
      <ellipse cx="60" cy="112" rx="32" ry="3" fill="#1F2937" opacity=".15"/>
      <ellipse cx="58" cy="80" rx="32" ry="26" fill="#374151"/>
      <ellipse cx="58" cy="86" rx="22" ry="16" fill="#6B7280"/>
      <path d="M40 70 Q 30 78 36 92 Q 46 92 50 80 Z" fill="#1F2937"/>
      <path d="M28 62 Q 18 56 16 48 Q 24 50 30 58 Z" fill="#FCD34D"/>
      <path d="M26 70 Q 12 70 10 62 Q 22 60 28 66 Z" fill="#FB7185"/>
      <path d="M28 78 Q 14 82 14 74 Q 22 70 30 74 Z" fill="#14B8A6"/>
      <rect x="50" y="102" width="5" height="10" fill="#FB7185"/>
      <rect x="66" y="102" width="5" height="10" fill="#FB7185"/>
      <path d="M46 112 L 58 112 L 56 114 L 48 114 Z" fill="#FB7185"/>
      <path d="M62 112 L 74 112 L 72 114 L 64 114 Z" fill="#FB7185"/>
      <ellipse cx="80" cy="50" rx="20" ry="22" fill="#374151"/>
      <circle cx="76" cy="30" r="3" fill="#FCD34D"/>
      <circle cx="82" cy="28" r="3" fill="#FCD34D"/>
      <circle cx="88" cy="32" r="2.5" fill="#FCD34D"/>
      <path d="M79 47 Q 84 41 89 47" stroke="#1F2937" stroke-width="2.4" fill="none" stroke-linecap="round"/>
      <path d="M80 44 Q 84 40 88 44" stroke="#1F2937" stroke-width="1" fill="none" stroke-linecap="round" opacity=".4"/>
      <ellipse cx="74" cy="58" rx="5.5" ry="3" fill="#FB7185" opacity=".7"/>
      <path d="M96 49 Q 118 50 113 68 Q 104 71 92 60 Z" fill="#FCD34D" stroke="#1F2937" stroke-width="1.5"/>
      <path d="M91 61 Q 96 67 101 61" stroke="#1F2937" stroke-width="1.6" fill="none" stroke-linecap="round"/>
      <circle cx="106" cy="55" r="0.8" fill="#1F2937"/>
    </symbol>
  </defs>
</svg>
```

- [ ] **Step 6: Verify static files load**

Run inside the container so the live runserver picks them up:

```bash
docker exec raffle-web python manage.py collectstatic --noinput
curl -s -o /dev/null -w "brand.css: %{http_code}\n" http://localhost:8500/static/css/brand.css
curl -s -o /dev/null -w "dodo.svg: %{http_code}\n" http://localhost:8500/static/brand/dodo.svg
curl -s -o /dev/null -w "favicon.svg: %{http_code}\n" http://localhost:8500/static/brand/favicon.svg
```

Expected: all three return `200`.

- [ ] **Step 7: Commit**

```bash
git add campaigns/static/brand/dodo.svg \
        campaigns/static/brand/dodo-light.svg \
        campaigns/static/brand/favicon.svg \
        campaigns/static/css/brand.css \
        campaigns/templates/campaigns/_brand_assets.html
git commit -m "feat(brand): add Promo-Domo brand assets, tokens, and template partial"
```

---

## Task 2: Apply brand to base.html (head, sidebar, topbar, stat cards)

**Files:**
- Modify: `campaigns/templates/campaigns/base.html`

This is the single largest change. The strategy is to (a) include `_brand_assets`, (b) re-point the existing `:root` variables to brand tokens (which cascades to sidebar, topbar, buttons automatically), (c) replace the sidebar brand HTML with the dodo lockup, (d) restyle the stat-card color variants. Everything else (cards, tables, badges) inherits the new palette via tokens.

- [ ] **Step 1: Replace `<title>` default and include brand assets in `<head>`**

Open `campaigns/templates/campaigns/base.html`. Replace lines 6–8 (currently the `<title>` + Bootstrap CSS + Bootstrap Icons CSS):

**Before** (lines 6–8):
```django
  <title>{% block title %}RaffleManager{% endblock %}</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css" rel="stylesheet">
```

**After:**
```django
  <title>{% block title %}Promo-Domo{% endblock %}</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css" rel="stylesheet">
  {% include "campaigns/_brand_assets.html" %}
```

- [ ] **Step 2: Re-point `:root` variables to brand tokens**

Replace the entire `:root` block (lines 10–24 in `campaigns/templates/campaigns/base.html`):

**Before:**
```css
:root {
  --sidebar-bg: #1a2035;
  --sidebar-width: 260px;
  --sidebar-link: #a0aec0;
  --sidebar-link-hover: #ffffff;
  --sidebar-active: #4f8ef7;
  --topbar-bg: #ffffff;
  --content-bg: #f4f6fb;
  --card-radius: 12px;
  --accent: #4f8ef7;
  --accent-dark: #2563eb;
  --success-color: #22c55e;
  --danger-color: #ef4444;
  --warning-color: #f59e0b;
}
```

**After:**
```css
:root {
  --sidebar-bg: var(--pd-cream-soft);
  --sidebar-width: 260px;
  --sidebar-link: var(--pd-ink-soft);
  --sidebar-link-hover: var(--pd-ink);
  --sidebar-active: var(--pd-coral);
  --topbar-bg: #ffffff;
  --content-bg: var(--pd-cream);
  --card-radius: 12px;
  --accent: var(--pd-coral);
  --accent-dark: var(--pd-coral-deep);
  --success-color: #22c55e;
  --danger-color: #ef4444;
  --warning-color: #f59e0b;
}
```

- [ ] **Step 3: Replace `body` font and sidebar-brand styles to use display font**

Find the `body` rule (lines 26–30) and update font-family:

**Before:**
```css
body {
  background: var(--content-bg);
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  min-height: 100vh;
}
```

**After:**
```css
body {
  background: var(--content-bg);
  font-family: var(--pd-font-body);
  min-height: 100vh;
}
```

Then update `.sidebar-brand` (line 46–49) to add a bottom border that matches the cream sidebar:

**Before:**
```css
.sidebar-brand {
  padding: 1.5rem 1.5rem 1rem;
  border-bottom: 1px solid rgba(255,255,255,0.08);
}
```

**After:**
```css
.sidebar-brand {
  padding: 1.5rem 1.5rem 1rem;
  border-bottom: 1px solid var(--pd-line);
}
```

Update `.sidebar-brand .brand-text` (lines 64–69) for Fraunces + ink:

**Before:**
```css
.sidebar-brand .brand-text {
  font-size: 1.15rem;
  font-weight: 700;
  color: #ffffff;
  letter-spacing: -0.3px;
}
```

**After:**
```css
.sidebar-brand .brand-text {
  font-family: var(--pd-font-display);
  font-size: 1.25rem;
  font-weight: 800;
  color: var(--pd-ink);
  letter-spacing: -0.025em;
  line-height: 1;
}
```

Update `.sidebar-brand .brand-sub` (lines 71–76):

**Before:**
```css
.sidebar-brand .brand-sub {
  font-size: 0.7rem;
  color: var(--sidebar-link);
  text-transform: uppercase;
  letter-spacing: 1px;
}
```

**After:**
```css
.sidebar-brand .brand-sub {
  font-size: 0.65rem;
  color: var(--pd-ink-soft);
  text-transform: uppercase;
  letter-spacing: 1.4px;
  margin-top: 4px;
}
```

- [ ] **Step 4: Update sidebar-nav active state to coral wash**

Find the `.sidebar-nav .nav-link:hover` rule (lines 104–108) and `.sidebar-nav .nav-link.active` rule (lines 110–115). The hover rgba currently uses blue (`rgba(79, 142, 247, 0.5)` and `rgba(79, 142, 247, 0.12)`). Replace with coral.

**Before (hover, lines 104–108):**
```css
.sidebar-nav .nav-link:hover {
  color: var(--sidebar-link-hover);
  background: rgba(255,255,255,0.06);
  border-left-color: rgba(79, 142, 247, 0.5);
}
```

**After:**
```css
.sidebar-nav .nav-link:hover {
  color: var(--sidebar-link-hover);
  background: rgba(251, 113, 133, 0.06);
  border-left-color: rgba(251, 113, 133, 0.5);
}
```

**Before (active, lines 110–115):**
```css
.sidebar-nav .nav-link.active {
  color: var(--sidebar-link-hover);
  background: rgba(79, 142, 247, 0.12);
  border-left-color: var(--accent);
  font-weight: 600;
}
```

**After:**
```css
.sidebar-nav .nav-link.active {
  color: var(--sidebar-link-hover);
  background: rgba(251, 113, 133, 0.12);
  border-left-color: var(--accent);
  font-weight: 600;
}
```

Also update the `sidebar-section-label` color (lines 78–85) so labels are readable on cream:

**Before:**
```css
.sidebar-section-label {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 1.5px;
  color: rgba(160, 174, 192, 0.5);
  padding: 1.2rem 1.5rem 0.4rem;
  font-weight: 600;
}
```

**After:**
```css
.sidebar-section-label {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 1.5px;
  color: var(--pd-gray);
  padding: 1.2rem 1.5rem 0.4rem;
  font-weight: 700;
}
```

And `.sidebar-footer` (lines 124–129):

**Before:**
```css
.sidebar-footer {
  padding: 1rem 1.5rem;
  border-top: 1px solid rgba(255,255,255,0.08);
  font-size: 0.78rem;
  color: rgba(160,174,192,0.6);
}
```

**After:**
```css
.sidebar-footer {
  padding: 1rem 1.5rem;
  border-top: 1px solid var(--pd-line);
  font-size: 0.78rem;
  color: var(--pd-ink-soft);
}
```

- [ ] **Step 5: Restyle stat-card color variants to brand palette**

Find lines 265–269 (the five `.stat-card` color variants). Replace the entire block:

**Before:**
```css
.stat-card.blue { background: linear-gradient(135deg, #4f8ef7, #2563eb); color: #fff; }
.stat-card.green { background: linear-gradient(135deg, #22c55e, #16a34a); color: #fff; }
.stat-card.purple { background: linear-gradient(135deg, #a855f7, #7c3aed); color: #fff; }
.stat-card.orange { background: linear-gradient(135deg, #f59e0b, #d97706); color: #fff; }
.stat-card.teal { background: linear-gradient(135deg, #14b8a6, #0d9488); color: #fff; }
```

**After:**
```css
.stat-card.blue   { background: var(--pd-yellow); color: var(--pd-ink); }
.stat-card.green  { background: var(--pd-teal); color: #fff; }
.stat-card.purple { background: var(--pd-coral); color: #fff; }
.stat-card.orange { background: var(--pd-cream); color: var(--pd-ink); }
.stat-card.teal   { background: var(--pd-teal); color: #fff; }

.stat-card .stat-value {
  font-family: var(--pd-font-display);
  font-size: 2.2rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  line-height: 1;
  margin-bottom: 0.25rem;
}
```

(The `.stat-value` rule already exists at lines 250–255 — replace it with the new one above. Move the new `.stat-value` rule to immediately follow the color variants for clarity.)

- [ ] **Step 6: Replace the sidebar brand HTML**

Find the `<div class="sidebar-brand">` block (lines 402–410). Replace its entire content:

**Before:**
```django
<div class="sidebar-brand">
  <div class="d-flex align-items-center">
    <span class="brand-icon"><i class="bi bi-ticket-perforated-fill"></i></span>
    <div>
      <div class="brand-text">RaffleManager</div>
      <div class="brand-sub">Campaign Platform</div>
    </div>
  </div>
</div>
```

**After:**
```django
<div class="sidebar-brand">
  <div class="d-flex align-items-center" style="gap: 10px;">
    <svg width="36" height="36" viewBox="0 0 120 120" aria-hidden="true">
      <use href="#pd-dodo"/>
    </svg>
    <div>
      <div class="brand-text">Promo<span class="pd-hyphen">-</span>Domo</div>
      <div class="brand-sub">Campaign Platform</div>
    </div>
  </div>
</div>
```

The legacy `.brand-icon` CSS rule (lines 51–62) is now unused. Delete it to keep the stylesheet clean.

- [ ] **Step 7: Update topbar avatar color so initials read on yellow**

Find `.user-badge .avatar` (lines 176–187) and update background + text contrast:

**Before:**
```css
.user-badge .avatar {
  width: 28px;
  height: 28px;
  background: var(--accent);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 0.75rem;
  font-weight: 700;
}
```

**After:**
```css
.user-badge .avatar {
  width: 28px;
  height: 28px;
  background: var(--pd-yellow);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--pd-ink);
  font-size: 0.75rem;
  font-weight: 700;
}
```

- [ ] **Step 8: Update form-control focus color**

Find `.form-control:focus, .form-select:focus` (lines 359–362):

**Before:**
```css
.form-control:focus, .form-select:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(79, 142, 247, 0.15);
}
```

**After:**
```css
.form-control:focus, .form-select:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(251, 113, 133, 0.18);
}
```

- [ ] **Step 9: Update btn-primary hover focus shadow**

Find `.btn-primary` and `.btn-primary:hover` (lines 334–342). Add a focus shadow override to use coral:

**Before:**
```css
.btn-primary {
  background: var(--accent);
  border-color: var(--accent);
}

.btn-primary:hover {
  background: var(--accent-dark);
  border-color: var(--accent-dark);
}
```

**After:**
```css
.btn-primary {
  background: var(--accent);
  border-color: var(--accent);
}

.btn-primary:hover,
.btn-primary:focus,
.btn-primary:active {
  background: var(--accent-dark) !important;
  border-color: var(--accent-dark) !important;
  box-shadow: 0 0 0 3px rgba(251, 113, 133, 0.25) !important;
}
```

- [ ] **Step 10: Verify in the browser**

Restart the container so collectstatic runs:

```bash
docker compose restart web
sleep 4
curl -s -o /dev/null -w "dashboard: %{http_code}\n" http://localhost:8500/dashboard/
curl -s http://localhost:8500/dashboard/ | grep -E "(Promo-Domo|<title>)" | head -3
```

Expected: `dashboard: 302` (redirects to login, since unauth — that's fine for the smoke check). Title contains `Promo-Domo`. Open `http://localhost:8500/dashboard/` in a browser, sign in (`admin` / `admin123`) and visually confirm: cream sidebar, dodo + "Promo-Domo" wordmark with coral hyphen, coral active nav, yellow avatar.

- [ ] **Step 11: Commit**

```bash
git add campaigns/templates/campaigns/base.html
git commit -m "feat(brand): apply Promo-Domo brand to base.html (sidebar, topbar, stat cards)"
```

---

## Task 3: Restyle login.html

**Files:**
- Modify: `campaigns/templates/campaigns/login.html`

The login page is standalone (does not extend base.html). It's a full rewrite of the inline `<style>` and the body markup to match the spec's split layout (yellow art panel left, white form right) using the brand tokens.

- [ ] **Step 1: Replace the entire login.html file**

Open `campaigns/templates/campaigns/login.html` and replace its entire contents with:

```django
{% load static %}
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Sign in · Promo-Domo</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css" rel="stylesheet">
  {% include "campaigns/_brand_assets.html" %}
  <style>
    body {
      background: var(--pd-cream);
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      font-family: var(--pd-font-body);
      padding: 24px;
    }

    .login-shell {
      width: 100%;
      max-width: 880px;
      background: #fff;
      border-radius: 22px;
      overflow: hidden;
      box-shadow: 0 30px 80px rgba(31, 41, 55, 0.18);
      display: grid;
      grid-template-columns: 1.1fr 1fr;
      min-height: 480px;
    }

    @media (max-width: 760px) {
      .login-shell { grid-template-columns: 1fr; min-height: 0; }
    }

    .login-art {
      background: var(--pd-yellow);
      padding: 40px 32px;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      text-align: center;
      position: relative;
      overflow: hidden;
    }

    .login-art::before {
      content: "";
      position: absolute;
      inset: 0;
      background:
        radial-gradient(circle at 25% 25%, rgba(255,255,255,0.35), transparent 45%),
        radial-gradient(circle at 75% 80%, rgba(20, 184, 166, 0.18), transparent 50%);
      pointer-events: none;
    }

    .login-art > * { position: relative; }

    .login-art .name-stacked {
      font-family: var(--pd-font-display);
      font-weight: 800;
      font-size: 2rem;
      color: var(--pd-ink);
      letter-spacing: -0.025em;
      margin: 14px 0 0;
      line-height: 1;
    }

    .login-art .tagline {
      font-family: var(--pd-font-display);
      font-style: italic;
      font-size: 1.05rem;
      color: var(--pd-ink);
      margin-top: 18px;
      max-width: 240px;
      line-height: 1.4;
    }

    .login-form {
      padding: 44px 40px;
      display: flex;
      flex-direction: column;
      justify-content: center;
      gap: 14px;
    }

    .login-form h2 {
      font-family: var(--pd-font-display);
      font-size: 1.6rem;
      font-weight: 800;
      color: var(--pd-ink);
      margin: 0 0 4px;
      letter-spacing: -0.02em;
    }

    .login-form .lead {
      font-size: 0.9rem;
      color: var(--pd-ink-soft);
      margin: 0 0 12px;
    }

    .form-floating label {
      color: var(--pd-ink-soft);
      font-size: 0.9rem;
    }

    .form-floating .form-control {
      border-radius: 10px;
      border: 1.5px solid #E5E7EB;
      padding-top: 1.6rem;
    }

    .form-floating .form-control:focus {
      border-color: var(--pd-coral);
      box-shadow: 0 0 0 3px rgba(251, 113, 133, 0.18);
    }

    .btn-login {
      background: var(--pd-coral);
      border: 0;
      border-radius: 10px;
      padding: 0.85rem;
      font-size: 1rem;
      font-weight: 700;
      width: 100%;
      color: #fff;
      transition: background 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease;
      margin-top: 6px;
    }

    .btn-login:hover {
      background: var(--pd-coral-deep);
      transform: translateY(-1px);
      box-shadow: 0 8px 20px rgba(251, 113, 133, 0.35);
      color: #fff;
    }

    .error-list {
      background: #FEF2F2;
      border-radius: 10px;
      padding: 0.75rem 1rem;
      margin-bottom: 1rem;
      border-left: 3px solid #EF4444;
    }

    .error-list p {
      color: #DC2626;
      font-size: 0.875rem;
      margin: 0;
    }

    .login-footer {
      grid-column: 1 / -1;
      text-align: center;
      padding: 14px;
      font-size: 0.75rem;
      color: var(--pd-ink-soft);
      background: var(--pd-cream-soft);
      border-top: 1px solid var(--pd-line);
    }
  </style>
</head>
<body>

<div class="login-shell">

  <div class="login-art">
    <svg width="120" height="120" viewBox="0 0 120 120" aria-hidden="true">
      <use href="#pd-dodo"/>
    </svg>
    <div class="name-stacked">Promo<span class="pd-hyphen">-</span>Domo</div>
    <p class="tagline">Run delightful giveaways your audience actually wants to enter.</p>
  </div>

  <form method="post" class="login-form">
    {% csrf_token %}
    <h2>Welcome back</h2>
    <p class="lead">Sign in to manage your campaigns.</p>

    {% if form.errors %}
      <div class="error-list">
        <p><i class="bi bi-exclamation-circle-fill me-1"></i>
          Invalid username or password. Please try again.
        </p>
      </div>
    {% endif %}

    <div class="form-floating mb-2">
      <input
        type="text"
        name="username"
        id="id_username"
        class="form-control {% if form.username.errors %}is-invalid{% endif %}"
        placeholder="Username"
        autocomplete="username"
        autofocus
        value="{{ form.username.value|default:'' }}"
      >
      <label for="id_username"><i class="bi bi-person me-1"></i>Username</label>
    </div>

    <div class="form-floating mb-2">
      <input
        type="password"
        name="password"
        id="id_password"
        class="form-control {% if form.password.errors %}is-invalid{% endif %}"
        placeholder="Password"
        autocomplete="current-password"
      >
      <label for="id_password"><i class="bi bi-lock me-1"></i>Password</label>
    </div>

    {% if next %}
      <input type="hidden" name="next" value="{{ next }}">
    {% endif %}

    <button type="submit" class="btn-login">
      <i class="bi bi-box-arrow-in-right me-2"></i>Sign in
    </button>
  </form>

  <div class="login-footer">
    &copy; Promo-Domo &mdash; Secure admin access
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
```

Note: every `is-invalid` / `invalid-feedback` class pattern is preserved, the form fields keep the same `name` attributes, and the CSRF token + `next` hidden input behavior is unchanged — view code does not need changes.

- [ ] **Step 2: Verify**

```bash
docker compose restart web
sleep 4
curl -s -o /dev/null -w "login: %{http_code}\n" http://localhost:8500/login/
curl -s http://localhost:8500/login/ | grep -E "(Promo-Domo|pd-dodo|pd-hyphen)" | head -5
```

Expected: `login: 200`. Three matching lines: title contains `Promo-Domo`, `<use href="#pd-dodo"/>` is present, `<span class="pd-hyphen">-</span>` is present. Open in a browser to visually confirm split layout, dodo + stacked wordmark on yellow, coral submit button.

- [ ] **Step 3: Commit**

```bash
git add campaigns/templates/campaigns/login.html
git commit -m "feat(brand): restyle login with stacked dodo lockup on yellow art panel"
```

---

## Task 4: Restyle submission_form.html (public form)

**Files:**
- Modify: `campaigns/templates/campaigns/submission_form.html`

This is the entrant-facing public form. The brand application is: yellow→coral gradient backdrop, white form card, horizontal lockup at the top, coral submit button. All field names and `is-invalid` patterns must be preserved (per spec constraints inherited from RESUME_NOTES).

- [ ] **Step 1: Replace the `<head>` style block and brand assets**

Open `campaigns/templates/campaigns/submission_form.html`. Replace lines 1–9 (the head opening through the `<style>` tag start):

**Before (lines 1–9):**
```django
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{ campaign.name }} - Enter to Win</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css" rel="stylesheet">
  <style>
```

**After:**
```django
{% load static %}
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{ campaign.name }} · Promo-Domo</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css" rel="stylesheet">
  {% include "campaigns/_brand_assets.html" %}
  <style>
```

- [ ] **Step 2: Replace the entire inline stylesheet**

Replace everything between `<style>` (now line 11) and `</style>` (currently around line 254) with:

```css
:root {
  --accent: var(--pd-coral);
  --accent-dark: var(--pd-coral-deep);
}

body {
  background: var(--pd-cream);
  min-height: 100vh;
  font-family: var(--pd-font-body);
}

.public-header {
  background: #fff;
  padding: 14px 0;
  box-shadow: 0 2px 10px rgba(31, 41, 55, 0.06);
}

.public-header .brand {
  color: var(--pd-ink);
  font-family: var(--pd-font-display);
  font-weight: 800;
  font-size: 1.25rem;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  letter-spacing: -0.025em;
}

.campaign-hero {
  background: linear-gradient(135deg, var(--pd-yellow) 0%, var(--pd-coral) 100%);
  color: var(--pd-ink);
  padding: 3.5rem 0 4.5rem;
  text-align: center;
  position: relative;
  overflow: hidden;
}

.campaign-hero::before {
  content: '';
  position: absolute;
  inset: -50%;
  background: radial-gradient(circle at 70% 30%, rgba(255,255,255,0.45) 0%, transparent 55%);
  pointer-events: none;
}

.campaign-hero h1 {
  font-family: var(--pd-font-display);
  font-size: clamp(1.85rem, 5vw, 2.85rem);
  font-weight: 800;
  margin-bottom: 0.6rem;
  position: relative;
  letter-spacing: -0.025em;
  color: var(--pd-ink);
}

.campaign-hero .lead {
  font-size: 1.05rem;
  color: var(--pd-ink);
  opacity: 0.85;
  max-width: 600px;
  margin: 0 auto 1.5rem;
  position: relative;
}

.campaign-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: rgba(31, 41, 55, 0.85);
  border: 0;
  color: #DCFCE7;
  border-radius: 999px;
  padding: 0.4rem 1rem;
  font-size: 0.8rem;
  font-weight: 600;
  position: relative;
}

.campaign-badge.closed {
  color: #FCA5A5;
}

.form-card {
  background: #fff;
  border-radius: 20px;
  box-shadow: 0 24px 60px rgba(31, 41, 55, 0.15);
  padding: 2.5rem;
  margin-top: -2.25rem;
  position: relative;
  z-index: 10;
}

.form-card h2 {
  font-family: var(--pd-font-display);
  font-size: 1.5rem;
  font-weight: 800;
  color: var(--pd-ink);
  margin-bottom: 0.25rem;
  letter-spacing: -0.02em;
}

.form-card .subtitle {
  color: var(--pd-ink-soft);
  font-size: 0.9rem;
  margin-bottom: 1.75rem;
}

.form-section-title {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 1.5px;
  color: var(--pd-gray);
  font-weight: 700;
  margin-bottom: 0.75rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid var(--pd-line);
}

.form-control, .form-select {
  border-radius: 10px;
  border: 1.5px solid #E5E7EB;
  padding: 0.6rem 0.9rem;
  font-size: 0.9rem;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.form-control:focus, .form-select:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(251, 113, 133, 0.18);
}

.form-control.is-invalid {
  border-color: #EF4444;
}

.form-label {
  font-weight: 600;
  font-size: 0.78rem;
  color: var(--pd-ink-soft);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 0.35rem;
}

.code-section {
  background: var(--pd-cream-soft);
  border: 2px dashed var(--pd-line);
  border-radius: 14px;
  padding: 1.5rem;
  margin-top: 1.5rem;
}

.code-section.required {
  border-color: var(--pd-coral);
  background: linear-gradient(135deg, var(--pd-cream-soft), #FFF1F2);
}

.code-icon {
  width: 40px;
  height: 40px;
  background: var(--pd-coral);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 1.1rem;
  flex-shrink: 0;
}

.btn-submit {
  background: var(--pd-coral);
  border: 0;
  border-radius: 12px;
  padding: 0.95rem 2rem;
  font-size: 1rem;
  font-weight: 700;
  color: #fff;
  width: 100%;
  transition: background 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease;
  letter-spacing: 0.3px;
}

.btn-submit:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 10px 22px rgba(251, 113, 133, 0.4);
  background: var(--pd-coral-deep);
  color: #fff;
}

.btn-submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.privacy-note {
  font-size: 0.78rem;
  color: var(--pd-ink-soft);
  text-align: center;
  margin-top: 1rem;
}

.closed-overlay {
  text-align: center;
  padding: 3rem 1.5rem;
}

.closed-overlay .closed-icon {
  width: 80px;
  height: 80px;
  background: #FEF2F2;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 2.5rem;
  color: #EF4444;
  margin: 0 auto 1.5rem;
}

.closed-overlay h3 {
  font-family: var(--pd-font-display);
  font-weight: 800;
  color: var(--pd-ink);
}

.public-footer {
  text-align: center;
  padding: 2.5rem 1rem 1.5rem;
  font-size: 0.78rem;
  color: var(--pd-ink-soft);
}

.alert {
  border-radius: 10px;
  font-size: 0.875rem;
}

.invalid-feedback {
  font-size: 0.8rem;
}
```

- [ ] **Step 3: Replace the public-header markup**

Find the `<!-- Header -->` block (currently lines 258–266) and replace:

**Before:**
```django
<!-- Header -->
<div class="public-header">
  <div class="container">
    <a href="#" class="brand">
      <div class="brand-icon"><i class="bi bi-ticket-perforated-fill text-white"></i></div>
      RaffleManager
    </a>
  </div>
</div>
```

**After:**
```django
<!-- Header -->
<div class="public-header">
  <div class="container">
    <a href="#" class="brand">
      <svg width="32" height="32" viewBox="0 0 120 120" aria-hidden="true">
        <use href="#pd-dodo"/>
      </svg>
      <span>Promo<span class="pd-hyphen">-</span>Domo</span>
    </a>
  </div>
</div>
```

- [ ] **Step 4: Update public-footer markup**

Find the `<div class="public-footer">` block (currently around line 486–488) and replace its inner text:

**Before:**
```django
<div class="public-footer">
  &copy; {{ campaign.name }} &mdash; Powered by RaffleManager
</div>
```

**After:**
```django
<div class="public-footer">
  &copy; {{ campaign.name }} &mdash; Powered by Promo-Domo
</div>
```

- [ ] **Step 5: Verify**

```bash
docker compose restart web
sleep 4
curl -s -o /dev/null -w "form: %{http_code}\n" http://localhost:8500/submit/sample-motorbike-giveaway/
curl -s http://localhost:8500/submit/sample-motorbike-giveaway/ | grep -E "(Promo-Domo|pd-dodo|RaffleManager)" | head -5
```

Expected: `form: 200`. Lines matching `Promo-Domo` and `pd-dodo`. **Zero matches** for `RaffleManager`. Open in browser, confirm yellow→coral hero, white form card, horizontal lockup, coral submit button. Submit a test entry to confirm form still validates and saves (field names unchanged).

- [ ] **Step 6: Commit**

```bash
git add campaigns/templates/campaigns/submission_form.html
git commit -m "feat(brand): restyle public submission form with yellow→coral hero and brand lockup"
```

---

## Task 5: Restyle dashboard.html page header

**Files:**
- Modify: `campaigns/templates/campaigns/dashboard.html`

The dashboard inherits all brand styling from base.html via cascading tokens. Only the `<title>` block, page-header heading icon color, and (optional) New Campaign button class need touchups.

- [ ] **Step 1: Update `<title>` block**

Open `campaigns/templates/campaigns/dashboard.html`. Replace line 3:

**Before:**
```django
{% block title %}Dashboard - RaffleManager{% endblock %}
```

**After:**
```django
{% block title %}Dashboard · Promo-Domo{% endblock %}
```

- [ ] **Step 2: Update page-header heading**

Find the `<div class="page-header">` (lines 8–15). Replace the `<h1>` content so the icon uses Fraunces and the speedometer color is brand-toned:

**Before (line 9):**
```django
  <h1><i class="bi bi-speedometer2 me-2 text-primary"></i>Dashboard</h1>
```

**After:**
```django
  <h1 class="pd-display"><i class="bi bi-speedometer2 me-2" style="color: var(--pd-coral);"></i>Dashboard</h1>
```

- [ ] **Step 3: Verify in browser**

```bash
docker compose restart web
sleep 4
curl -s -o /dev/null -w "dashboard: %{http_code}\n" -b "sessionid=fake" http://localhost:8500/dashboard/
```

Open `http://localhost:8500/dashboard/` in a browser and confirm: title is `Dashboard · Promo-Domo`, the dashboard heading uses Fraunces with a coral icon, the three stat cards now show yellow / teal / coral instead of blue / green / purple gradients.

- [ ] **Step 4: Commit**

```bash
git add campaigns/templates/campaigns/dashboard.html
git commit -m "feat(brand): apply Promo-Domo brand to dashboard page header"
```

---

## Task 6: Add Django admin branding

**Files:**
- Modify: `campaigns/admin.py`

django-unfold respects the standard Django `admin.site` attributes. Setting `site_header`, `site_title`, and `index_title` brands the admin index, header bar, and tab title. We add these at the bottom of `campaigns/admin.py` so the import order is preserved.

- [ ] **Step 1: Add admin site branding**

Open `campaigns/admin.py`. Append to the end of the file (after the `RaffleWinnerAdmin` class):

```python


# ============================================================
# Promo-Domo admin branding
# ============================================================
admin.site.site_header = "Promo-Domo Admin"
admin.site.site_title = "Promo-Domo"
admin.site.index_title = "Campaign Operations"
```

- [ ] **Step 2: Verify**

```bash
docker compose restart web
sleep 4
curl -s http://localhost:8500/admin/login/ | grep -E "(Promo-Domo|<title>)" | head -3
```

Expected: `<title>` contains `Promo-Domo`, the page body shows `Promo-Domo Admin` somewhere (Unfold renders site_header in the topbar). Open `http://localhost:8500/admin/` and visually confirm.

- [ ] **Step 3: Commit**

```bash
git add campaigns/admin.py
git commit -m "feat(brand): set Promo-Domo branding on Django admin site"
```

---

## Task 7: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace H1 and intro paragraph**

Open `README.md`. Replace the first 3 lines (the H1 and intro):

**Before:**
```markdown
# 🎰 Raffle Campaign Manager

A Django-based campaign and raffle management system that allows you to create campaigns, collect participant submissions via a public form, and conduct segmented raffles with exportable results.
```

**After:**
```markdown
# Promo-Domo

A Django-based promotion and raffle management platform. Create campaigns, collect participant submissions via a delightful public form, and conduct segmented raffles with exportable results — all under a friendly dodo mascot.
```

- [ ] **Step 2: Search for any remaining "RaffleManager" / "Raffle Campaign Manager" references in README**

```bash
grep -nE "RaffleManager|Raffle Campaign Manager|Raffle Manager" README.md || echo "No remaining matches"
```

If matches are found, replace them with `Promo-Domo`. (Mentions of "raffle" as a noun referring to the feature itself are fine — only the product name needs replacing.)

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(brand): rename README from Raffle Campaign Manager to Promo-Domo"
```

---

## Task 8: Add smoke tests for brand naming

**Files:**
- Create: `campaigns/tests/__init__.py`
- Create: `campaigns/tests/test_branding.py`

This locks in the rebrand against regression. Three integration tests: login page contains "Promo-Domo", submission form contains "Promo-Domo" and not "RaffleManager", admin login title contains "Promo-Domo".

- [ ] **Step 1: Create tests package**

Create `campaigns/tests/__init__.py` as an empty file:

```python
```

- [ ] **Step 2: Write the failing tests**

Create `campaigns/tests/test_branding.py`:

```python
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from campaigns.models import Campaign


class BrandingTests(TestCase):
    """Smoke tests asserting Promo-Domo brand strings on customer-visible surfaces."""

    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        cls.campaign = Campaign.objects.create(
            name="Test Giveaway",
            slug="test-giveaway",
            description="A test campaign for branding assertions.",
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=7),
            is_active=True,
            validate_submission_code=False,
            allow_multiple_submissions=False,
        )

    def test_login_page_uses_promo_domo_brand(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("Promo-Domo", body)
        self.assertIn('href="#pd-dodo"', body)
        self.assertNotIn("RaffleManager", body)

    def test_submission_form_uses_promo_domo_brand(self):
        response = self.client.get(
            reverse("submission_form", kwargs={"slug": self.campaign.slug})
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("Promo-Domo", body)
        self.assertIn('href="#pd-dodo"', body)
        self.assertNotIn("RaffleManager", body)

    def test_admin_login_uses_promo_domo_branding(self):
        response = self.client.get("/admin/login/")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        # Django admin renders site_title in <title>, site_header in the body
        self.assertIn("Promo-Domo", body)

    def test_brand_css_is_served(self):
        response = self.client.get("/static/css/brand.css")
        # In DEBUG=True with runserver, static is served. In tests via test runner,
        # static files may 404 unless `collectstatic` was run. This test asserts the
        # file exists on disk via Django's static finder, not the runtime URL.
        from django.contrib.staticfiles.finders import find
        self.assertIsNotNone(find("css/brand.css"))
        self.assertIsNotNone(find("brand/dodo.svg"))
        self.assertIsNotNone(find("brand/favicon.svg"))
```

- [ ] **Step 3: Run the tests to verify they pass**

The implementation is already done from Tasks 2–6, so these tests should pass on first run:

```bash
docker exec raffle-web python manage.py test campaigns.tests.test_branding -v 2
```

Expected: `Ran 4 tests in X.XXXs — OK`. If any test fails, fix the corresponding template/admin file (do NOT loosen the test) before continuing.

- [ ] **Step 4: Commit**

```bash
git add campaigns/tests/__init__.py campaigns/tests/test_branding.py
git commit -m "test(brand): add smoke tests asserting Promo-Domo branding on key surfaces"
```

---

## Task 9: Final sweep, manual verification, and push

**Files:**
- (verification only)

- [ ] **Step 1: Sweep for any remaining legacy strings**

```bash
grep -rnE "RaffleManager|Raffle Campaign Manager|Raffle Manager" \
  --include="*.html" --include="*.py" --include="*.md" \
  --exclude-dir=".git" --exclude-dir=".venv" --exclude-dir="venv" \
  --exclude-dir=".superpowers" --exclude-dir="staticfiles" \
  --exclude-dir="docs" \
  . || echo "✓ No remaining legacy brand strings"
```

Expected: only `docs/superpowers/specs/2026-05-07-promo-domo-rebrand-design.md` and the plan file (which intentionally reference the old name in context). If any other file matches, fix it inline and commit as `chore(brand): remove residual RaffleManager string from <path>`.

- [ ] **Step 2: Restart and smoke-check every customer surface**

```bash
docker compose restart web
sleep 5
echo "--- Public surfaces ---"
curl -s -o /dev/null -w "GET /                                    %{http_code}\n" http://localhost:8500/
curl -s -o /dev/null -w "GET /login/                              %{http_code}\n" http://localhost:8500/login/
curl -s -o /dev/null -w "GET /submit/sample-motorbike-giveaway/   %{http_code}\n" http://localhost:8500/submit/sample-motorbike-giveaway/
curl -s -o /dev/null -w "GET /admin/login/                        %{http_code}\n" http://localhost:8500/admin/login/
echo "--- Static assets ---"
curl -s -o /dev/null -w "GET /static/css/brand.css                %{http_code}\n" http://localhost:8500/static/css/brand.css
curl -s -o /dev/null -w "GET /static/brand/dodo.svg               %{http_code}\n" http://localhost:8500/static/brand/dodo.svg
curl -s -o /dev/null -w "GET /static/brand/favicon.svg            %{http_code}\n" http://localhost:8500/static/brand/favicon.svg
```

Expected: every URL returns 200 or 302 (302 is fine for `/` and `/login/` redirects to dashboard or back). All static assets return 200. If any return 5xx, check `docker compose logs web --tail 50` and fix before continuing.

- [ ] **Step 3: Visually confirm in browser**

Open each URL in a browser:
- `http://localhost:8500/login/` — yellow art panel with stacked dodo + tagline, white form, coral submit
- `http://localhost:8500/dashboard/` (after sign-in `admin` / `admin123`) — cream sidebar with dodo + Promo-Domo wordmark, coral active nav, yellow stat card, teal stat card, coral stat card, dashboard heading in Fraunces with coral icon
- `http://localhost:8500/submit/sample-motorbike-giveaway/` — white horizontal lockup header, yellow→coral hero with campaign name in Fraunces, white form card with coral submit
- `http://localhost:8500/admin/` — `Promo-Domo Admin` shows as the Unfold site header

Browser tab on every page should show the dodo favicon.

- [ ] **Step 4: Run full test suite**

```bash
docker exec raffle-web python manage.py test -v 2
```

Expected: all branding tests pass; no regressions in any existing test (there are none today, but this guards against future breakage).

- [ ] **Step 5: Push all commits to origin**

```bash
git push origin main
```

If the push fails due to network/DNS (as happened during plan creation), retry once network is restored. Do NOT use `--force`.

- [ ] **Step 6: Post-merge cleanup**

After everything is shipped, delete the brainstorm session files (they're already gitignored, but the directory can be removed):

```bash
rm -rf .superpowers/brainstorm
```

(Optional — they're harmless if left.)

---

## Verification Summary

After all tasks complete, the customer-visible surface inventory should be:

| Surface | Title | Brand element |
|---|---|---|
| `/login/` | `Sign in · Promo-Domo` | Stacked dodo lockup on yellow art panel |
| `/dashboard/` | `Dashboard · Promo-Domo` | Cream sidebar, dodo + wordmark, coral active nav |
| `/submit/<slug>/` | `<Campaign> · Promo-Domo` | Horizontal lockup header, yellow→coral hero |
| `/admin/` | `Promo-Domo` (tab), `Promo-Domo Admin` (header) | Unfold default theme + branded strings |
| Browser tab (any page) | Dodo favicon |

Zero matches for `RaffleManager` or `Raffle Campaign Manager` anywhere except the spec / plan markdown files (which reference the old name as context).

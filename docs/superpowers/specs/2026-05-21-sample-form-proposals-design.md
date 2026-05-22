# Sample form proposals — 5 demo themes

**Status:** approved 2026-05-21
**Owner:** pnigroh
**Type:** demo / seed content (non-feature, additive only)

## §1 Problem

The repo ships exactly one theme (`futboleros`). Operators evaluating the platform have no comparator — no sense of what range of design directions the per-campaign theme system can absorb, and no working demo URLs they can click through.

We want **five sample campaigns, each with a fully-styled theme**, runnable locally at `http://localhost:8500/submit/<slug>/`, that together demonstrate the visual range the theme system supports.

## §2 Scope

In:
- One new `Domain` row (`hostname = localhost`) — does NOT replace the existing fallback Domain.
- Five new `Campaign` rows + their `Prize` rows, all under the localhost Domain.
- Five new `Theme` rows + their on-disk bundles in `<THEMES_ROOT>/<slug>/`.
- One idempotent `manage.py seed_demo_proposals` command that creates all of the above with `get_or_create`.
- Brand-distinct visuals for each (palette, type, layout). Three single-page, two wizard-style.

Out:
- No new Django model fields, migrations, or `SubmissionForm` changes — every theme renders the same form.
- No tests — this is demo seed content, not a feature.
- No PR / branch — lands directly on `main` as additive content.
- No multi-step backend logic. Wizards are a JS show/hide UX layer over a single POST.

## §3 The five proposals

| # | Slug | Brand | Style | Form layout | Palette |
|---|---|---|---|---|---|
| 1 | `lumen-coffee` | Lumen Coffee — specialty cafe loyalty raffle | Editorial Minimalism | **Wizard (3 steps)** | Ivory `#FAF7F2` / Espresso `#2B1810` / Sage `#6B8E5B` |
| 2 | `voltkick` | VoltKick — energy drink gaming sweepstakes | Glassmorphism + Neon | **Wizard (3 levels)** | Midnight `#0A0E27` / Cyan `#00F0FF` / Magenta `#FF006E` |
| 3 | `riot-sneakers` | RIOT — limited streetwear drop | Brutalist Bold | Single-page asymmetric | Paper `#FFFEF7` / Ink `#0A0A0A` / Hazard `#FFEA00` / Alert `#FF0844` |
| 4 | `pawly` | Pawly — premium pet food giveaway | Bento + Claymorphism | Single-page bento grid | Peach `#FFD3B6` / Sage `#B5C99A` / Milk `#FFF9F0` / Charcoal `#393E46` |
| 5 | `sol-y-mar` | Sol y Mar — tropical beverage / vacation | Festival / Maximalist | Single-page long-scroll | Coral `#FF6B6B` / Mango `#FFB347` / Ocean `#45B7D1` / Lime `#C7F464` |

Fonts via Google Fonts CDN per theme. Illustrations inline SVG inside each theme's `assets/` — no large image binaries, keeps each bundle under 200 KB.

## §4 Wizard UX (themes 1 & 2)

Both wizards run client-side over a single `<form>` whose Django fields are organized into three `<fieldset>` step containers. Vanilla JS controls visibility + Next/Back + a progress indicator. No client-side validation gating — the user can advance freely; server still enforces required fields on POST.

### Lumen — 3 elegant steps
1. **Hello** — first_name, last_name, email
2. **Where** — state, county, store
3. **Receipt** — phone, image_1, submit

### VoltKick — 3 "levels"
1. **Level 1: Identify** — first_name, last_name, email, phone
2. **Level 2: Locate** — state, county, store
3. **Level 3: Power up** — image_1 (receipt), image_2 (selfie), submit

Progress: Lumen uses a thin underline progress bar with step labels; VoltKick uses a neon segmented bar with level numbers.

Fallback: `<noscript>` reveals all fieldsets stacked; the Next/Back buttons are inside a `<div class="js-only">` that JS un-hides.

## §5 Form fields & image strategy

All five themes render the SAME Django `SubmissionForm` (no per-theme form subclass — that's a future feature, not today's scope). Fields rendered everywhere:

- `first_name`, `last_name` (required)
- `email`, `phone` (required)
- `state` (dropdown), `county` (text)
- `store` (dropdown — populated from `Store` table; seed adds 2 generic stores if table is empty)
- `image_1` — "proof of purchase" framing in copy
- `image_2` — **hidden via CSS** on Lumen, Pawly, Sol-y-Mar (single-image flow); **shown as "selfie with product"** on VoltKick + RIOT
- `submission_code_input` — hidden everywhere (campaigns have `validate_submission_code=False`)

Labels & microcopy are brand-voiced per theme.

## §6 Success pages

Each theme ships its own `submission_success.html` matching the form's style. Common content:
- Brand-voiced thank-you headline
- "You're in the running for:" with `{% for prize in prizes %}` loop
- "Winners announced on {{ campaign.end_date|date:'F j, Y' }}"
- Brand-appropriate CTA (return home, share, etc.)

## §7 Database state

### Domain
- One `Domain.objects.get_or_create(hostname='localhost', defaults={'display_name': 'Demo Showcase'})`.
- Existing fallback Domain (`promo-domo.example`) is untouched.

### Campaigns (5×)
For each: `name`, `slug`, `description`, `domain=<localhost>`, `start_date = now() - 7d`, `end_date = now() + 60d`, `is_active=True`, `validate_submission_code=False`, `allow_multiple_submissions=True`, `primary_color` + `sidebar_color` per palette table above, `theme=<corresponding Theme>`.

### Prizes (2-3 per campaign)
Brand-appropriate prize names — "Year of Specialty Beans" for Lumen, "Razer Blade 16 + 12-month VoltKick supply" for VoltKick, "Air Max 1 'Hazard' size run" for RIOT, "12 months of Pawly Premium for two pets" for Pawly, "All-inclusive Tulum getaway for 2" for Sol y Mar.

### Themes (5×)
For each: `Theme.objects.get_or_create(slug='<slug>', defaults={'name': '<Brand Name>', 'description': '<one line>'})`. The seed command writes the bundle to `<THEMES_ROOT>/<slug>/` if the directory doesn't already exist (so re-runs don't clobber edits).

### Stores (conditional)
If `Store.objects.exists()` returns False, seed adds two generic ones: "Main Street Market", "Westfield Plaza". Otherwise leaves the table alone.

## §8 File layout

```
campaigns/management/commands/seed_demo_proposals.py    # NEW — idempotent seeder
themes/lumen-coffee/
  submission_form.html
  submission_success.html
  assets/
    styles.css
    logo.svg
themes/voltkick/                  # same structure
themes/riot-sneakers/
themes/pawly/
themes/sol-y-mar/
docs/superpowers/specs/2026-05-21-sample-form-proposals-design.md   # this doc
```

`THEMES_ROOT` defaults to `<repo>/themes/` (already gitignored, per per-campaign-templates spec). We commit the seed script + the spec; the runtime bundle directories are created by the seed command on each environment.

## §9 Operator usage

```bash
# Apply on any environment (idempotent):
docker exec raffle-web python manage.py seed_demo_proposals

# Visit any of the 5:
open http://localhost:8500/submit/lumen-coffee/
open http://localhost:8500/submit/voltkick/
open http://localhost:8500/submit/riot-sneakers/
open http://localhost:8500/submit/pawly/
open http://localhost:8500/submit/sol-y-mar/
```

Re-running the command is safe — `get_or_create` everywhere; on-disk theme bundles are skipped if the directory exists. A `--force` flag will overwrite theme bundles on disk.

## §10 Risks & mitigations

| Risk | Mitigation |
|---|---|
| The seed runs in prod and creates demo campaigns where it shouldn't. | Command name is explicit (`seed_demo_proposals`), prints "About to create 5 demo campaigns under hostname 'localhost'. Continue? [y/N]" unless `--yes` is passed. |
| `localhost` Domain trips the `campaigns.W001` `ALLOWED_HOSTS` check on a prod box. | `localhost` is in default `ALLOWED_HOSTS_ENV`. On prod, operator removes the demo campaigns/Domain via admin if not wanted. |
| Wizard JS breaks → users can't submit. | `<noscript>` and `.js-only` classes ensure form is fully usable without JS. |
| New theme bundles inflate the repo. | Bundles are written by the seed command at runtime; `themes/` is gitignored. Only the seed source code lives in git. |

## §11 Future enhancements (explicitly out)

- Per-theme `SubmissionForm` subclass (let themes pick which fields to require).
- Real wizard with server-side step persistence (HTMX or DRF).
- Theme marketplace / preview gallery in admin.
- Mobile-first / responsive QA pass — current scope is desktop with reasonable mobile.

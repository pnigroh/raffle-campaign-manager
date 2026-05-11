# Auditable raffle draws with consumable participant pool — Design Spec

**Status:** approved 2026-05-11
**Scope:** add a tamper-evident internal audit trail to every raffle draw; expand the participant-pool filter; introduce an "Already Participated" lifecycle on submissions with operator-restorable eligibility.
**Out of scope (deferred):** cryptographic verification (NIST beacon, hash chains, blockchain), per-row include/exclude checkboxes during the draw, named/saved pool segments, audit logging for non-raffle entities.

---

## Summary

Today, a raffle draw runs an unseeded `random.shuffle()` and stores only the segment filters and the resulting winners. There is no way to prove the draw was random or to reproduce it. There is also no way to ensure a participant is drawn from only once across multiple draws on the same campaign.

This spec turns each raffle into a reproducible, internally-auditable event:

1. Every draw uses an isolated seeded RNG (`random.Random(seed)`); the seed and the exact participant pool snapshot are persisted on the `Raffle` row.
2. The participant pool is filtered by an expanded set of dimensions (existing state/county/date plus search, store, and an `include_already_participated` toggle).
3. Submissions gain a `participated_at` timestamp; the default raffle behavior consumes the pool (sets the timestamp on every member after the draw) and excludes already-participated participants from future pools. Operators can restore eligibility per-row with an audited reason.
4. A dedicated audit page renders the complete draw record and offers a "Verify" action that re-runs the recorded inputs through `conduct_raffle` and asserts the winners match.

The audit model is **internal traceability**, not cryptographic verifiability. The chosen design has a clean extension point for adding commit-reveal hashes or external randomness later without breaking existing draws.

## User Story

As Alice, a campaign manager:
- I open the Raffle page for my campaign. The filter form now has Search, Store, and a "Include participants who already took part in earlier draws" checkbox alongside the existing state/county/date fields. The live count updates as I narrow.
- I leave the new "Mark these participants as already-participated after draw" toggle ticked (the default).
- I press Realizar Sorteo. Winners are announced as before.
- Back on the campaign detail page, every submission that was in the pool now shows an orange "Ya participó · 11/05/2026" badge. The submissions row for each ex-pool participant has a "Restaurar elegibilidad" button.
- If I made a mistake (wrong filter, wrong campaign), I click Restaurar elegibilidad on the affected rows. A small modal asks "¿Por qué restaurar?" — I type a reason, confirm. The badge clears, the submission is eligible again, and the audit page for that raffle records "1 participant has had eligibility restored since this draw."
- I open the audit page for the raffle. I see: who ran it, when, the random seed (32-char hex), the algorithm name and version, every participant ID in the order they were considered, the prize quantities, and the winner list. A "Verify Audit" button re-runs the recorded inputs and reports ✓ "Audit verified — winners reproduced exactly." A "Download audit JSON" button hands me a single file I could give to a regulator.
- A skeptical participant can ask me for the JSON. They can run the same algorithm with the same seed against the same pool and confirm I didn't game anything.

## Architecture

### Data model

**One migration** adds the following:

```python
# Submission — new fields
participated_at = models.DateTimeField(null=True, blank=True,
    help_text="Set when this submission was last included in any raffle pool. "
              "Null = eligible for future draws.")
eligibility_restored_at = models.DateTimeField(null=True, blank=True)
eligibility_restored_by = models.ForeignKey(
    User, null=True, blank=True, on_delete=models.SET_NULL,
    related_name='eligibility_restorations',
)
eligibility_restoration_reason = models.CharField(max_length=200, blank=True)

# Raffle — new fields
seed = models.CharField(max_length=64, blank=True,
    help_text="Hex string passed to random.Random(seed). 32 chars from os.urandom(16) by default.")
algorithm = models.CharField(max_length=64, default='python.random.shuffle',
    help_text="Identifier for the RNG algorithm. Bump `algorithm_version` if behavior changes.")
algorithm_version = models.CharField(max_length=16, default='1.0')
participant_pool_snapshot = models.JSONField(default=list, blank=True,
    help_text="Ordered list of submission IDs as they were passed to the shuffler.")
prize_quantities = models.JSONField(default=list, blank=True,
    help_text="List of {prize_id, prize_name, quantity} so the audit page is "
              "readable even after a Prize is renamed or deleted.")
consumed_pool = models.BooleanField(default=True,
    help_text="True if `participated_at` was set on every pool member after the draw.")
excluded_already_participated = models.BooleanField(default=True,
    help_text="True if the pool was restricted to submissions where participated_at is null.")
filter_search = models.CharField(max_length=200, blank=True)
filter_store_id = models.IntegerField(null=True, blank=True)
```

**Why store `prize_name` inside `prize_quantities` JSON:** the existing `RaffleWinner.prize` FK is `on_delete=CASCADE` (already in the codebase) and the prize CRUD work added a guard against deleting prizes that have winners. So winner records are protected. But the JSON is the source of truth for the audit page and survives all mutations regardless. It also lets us render quantities for prizes that may have been deleted via Django admin (which bypasses our guard).

**Why JSONField for `participant_pool_snapshot`:** a list of integers, average ~50–500 per draw, is small. JSONField keeps the audit row a single record without a separate `RaffleParticipant` table. SQLite supports JSONField natively.

### `conduct_raffle()` refactor (`campaigns/utils.py`)

Current signature stays the same shape but gains a `seed` kwarg and changes RNG instantiation:

```python
def conduct_raffle(campaign, prizes_with_quantities, submission_qs,
                   conducted_by=None, segment_data=None, seed=None,
                   consume_pool=True, excluded_already_participated=True):
    if seed is None:
        seed = secrets.token_hex(16)  # 32-char hex
    rng = random.Random(seed)

    pool = list(submission_qs.order_by('id'))  # canonical order so snapshot is deterministic
    snapshot = [s.id for s in pool]
    rng.shuffle(pool)

    raffle = Raffle.objects.create(
        ...,
        seed=seed,
        algorithm='python.random.shuffle',
        algorithm_version='1.0',
        participant_pool_snapshot=snapshot,
        prize_quantities=[{'prize_id': p.id, 'prize_name': p.name, 'quantity': q}
                          for p, q in prizes_with_quantities],
        consumed_pool=consume_pool,
        excluded_already_participated=excluded_already_participated,
        ...
    )

    # ... existing winner-creation loop, unchanged ...

    if consume_pool and pool:
        Submission.objects.filter(id__in=snapshot).update(
            participated_at=raffle.conducted_at,
        )

    return raffle
```

**Reproducibility contract:** for any saved raffle, `random.Random(raffle.seed)` shuffling `Submission.objects.filter(id__in=raffle.participant_pool_snapshot).order_by('id')` and applying the same prize-quantity loop must produce the same winner list. The audit verify button asserts exactly this.

**Note on `submission_qs.order_by('id')`:** the snapshot must be deterministic. Without an explicit order, two equivalent QuerySets could produce different lists on different DB backends, breaking reproducibility. Forcing `order_by('id')` makes the snapshot canonical and the seed sufficient.

### Form changes (`campaigns/forms.py`)

`RaffleSegmentForm` gains four new fields:

```python
search = forms.CharField(max_length=200, required=False,
    help_text="First name, last name, email or phone substring.")
store = forms.ModelChoiceField(
    queryset=Store.objects.filter(is_active=True), required=False,
    empty_label="-- Cualquier tienda --",
)
include_already_participated = forms.BooleanField(required=False,
    help_text="By default, participants who took part in any earlier draw on this "
              "campaign are excluded.")
consume_pool = forms.BooleanField(required=False, initial=True,
    help_text="By default, every participant in this draw is marked as already-participated "
              "and won't appear in future draws unless restored.")
```

The `consume_pool` field's `required=False, initial=True` pair means the rendered checkbox is checked by default but won't fail validation when unchecked.

### View changes (`campaigns/views.py`)

`raffle_view` is updated to:
- Pass the new four form fields to the QuerySet builder (search via Q-or, store via FK filter).
- Apply the default `participated_at__isnull=True` filter unless `include_already_participated` is checked.
- Pass `seed=None` (auto-generate) and the two boolean toggles to `conduct_raffle`.

`ajax_filter_count` is updated identically (without doing the draw) so the live count preview honors the new filters.

Two new views:
- `raffle_audit(request, raffle_id)` — renders the audit page. Authorized via the existing `@login_required` + manager check (mirrors `raffle_results`).
- `raffle_audit_json(request, raffle_id)` — returns the audit blob as `application/json` for download.

A new URL-named POST view:
- `submission_restore_eligibility(request, campaign_id, submission_id)` — accepts a reason, sets `participated_at=None`, populates the restoration audit fields. Uses the same `_get_managed_campaign_or_403` gate.

### Template changes

**`campaigns/templates/campaigns/raffle.html`** (existing): the segment form gets the four new fields. The submit button text stays "Realizar Sorteo".

**`campaigns/templates/campaigns/campaign_detail.html`** (existing):
- Submissions table: new column "Estado" showing "Eligible" / "Ya participó (date)" badge.
- Each "Ya participó" row: a "Restaurar elegibilidad" small button opens a new `#restoreEligibilityModal` (single shared modal at bottom of template, populated from data-attrs).

**New: `campaigns/templates/campaigns/raffle_audit.html`**: dedicated full page, extends `base.html`, layouts the audit data with sections for Who/When, Algorithm, Pool, Prizes, Winners, Consumption status, Verify button, and Download JSON button.

### URL changes (`campaigns/urls.py`)

Three new patterns:
- `path('dashboard/raffle/<int:raffle_id>/audit/', views.raffle_audit, name='raffle_audit')`
- `path('dashboard/raffle/<int:raffle_id>/audit/json/', views.raffle_audit_json, name='raffle_audit_json')`
- `path('dashboard/campaign/<int:campaign_id>/submission/<int:submission_id>/restore-eligibility/', views.submission_restore_eligibility, name='submission_restore_eligibility')`

The existing raffle-history table on `campaign_detail.html` gains an "Audit" button per row alongside "Results".

### Authorization

All new authenticated views go through `_get_managed_campaign_or_403` (audit / restore) or its raffle-scoped equivalent (e.g. `raffle.campaign.managers.filter(id=request.user.id).exists()` per the existing `raffle_results` pattern). Cross-campaign URL tampering returns 403.

### Verify-audit semantics

Verification runs server-side and is idempotent — no separate POST endpoint needed. The audit page renders with verification baked into the context:

1. The view re-loads `Submission.objects.filter(id__in=raffle.participant_pool_snapshot).order_by('id')`.
2. Builds an `rng = random.Random(raffle.seed)`.
3. Calls `rng.shuffle(pool)`.
4. Walks the prize-quantity list and assembles the winner list using the same algorithm as `conduct_raffle`.
5. Compares to the stored `RaffleWinner` rows.
6. Adds `verify_status = 'ok' | 'mismatch' | 'unverifiable'` and (if mismatch) `verify_diff` to the page context.

The verify view does NOT mutate any data. It does not create a new Raffle. It is purely a re-computation against stored inputs. A "Verify again" button on the page re-renders it (a plain GET) so the operator can re-check after they've made other changes.

Helper function `verify_raffle_audit(raffle)` lives in `campaigns/utils.py` and returns `{'status': str, 'diff': dict | None}`. It's called by `raffle_audit` view and is independently unit-testable.

**Edge case:** if a submission in the snapshot has been deleted from the DB (admin override; nothing in the current code deletes submissions, but Django admin could), the verify pass loads fewer rows than the snapshot length. The verify view detects this and reports ✗ with "N participants from the original pool no longer exist in the database." This is a real audit failure and worth surfacing.

## Error handling

- Empty pool: existing `messages.error` flow handles "no participants match the selected filters". Unchanged.
- No prizes selected: existing `messages.error` handles. Unchanged.
- Draw with `consume_pool=True` but `participated_at__isnull=True` filter NOT applied (i.e. operator opted in to including already-participated): the post-draw UPDATE will still set `participated_at=now()` on every pool member. This means the same draw with the same toggle setup is idempotent — re-running with `include_already_participated=True` after the first draw is allowed but consumes them anyway.
- Restore eligibility on a submission whose `participated_at` is already null: 400 Bad Request with message "Submission is already eligible." Don't create empty audit entries.
- Verify on a raffle that pre-dates this feature (no seed stored): the verify button is hidden and the page shows "Audit data not recorded — this raffle was conducted before audit logging was added."

## Testing (TDD, `campaigns/tests/test_raffle_audit.py`)

The test file is structured by concern. Approximate count: 20 tests.

**Reproducibility:**
- `test_same_seed_produces_same_winners` — call `conduct_raffle` twice with explicit seed; same submission set; assert identical winner ordering.
- `test_different_seeds_produce_different_winners` — call twice with different seeds, with enough pool size that collisions are unlikely; assert at least one winner differs (statistical).
- `test_seed_is_persisted_on_raffle` — after `conduct_raffle()` runs, `Raffle.seed` is non-empty 32-char hex.
- `test_participant_pool_snapshot_is_persisted` — after the draw, `raffle.participant_pool_snapshot` is the sorted-by-id list of submission IDs that went into the shuffler.
- `test_pool_snapshot_uses_canonical_order` — explicitly verify the snapshot is `order_by('id')` (not insertion order or random).

**Already-participated lifecycle:**
- `test_consume_pool_sets_participated_at_on_all_pool_members` — after draw, every submission in the pool has `participated_at` matching the raffle's `conducted_at`.
- `test_consume_pool_false_does_not_set_participated_at` — toggle off; no `participated_at` mutations.
- `test_default_pool_excludes_already_participated_submissions` — pre-set `participated_at` on one submission; run a draw; that submission is not in the snapshot.
- `test_include_already_participated_filter_overrides_default` — same setup, but with `include_already_participated=True` in segment_data; the previously-participated submission IS in the snapshot.

**Pool filters:**
- `test_search_filter_narrows_pool` — three submissions; search by partial first_name; pool contains only the matching one.
- `test_store_filter_narrows_pool` — assign two submissions to store A, one to store B; filter by A; pool size is 2.
- `test_combined_filters_intersect` — search + store + state combined; only matching subset enters the pool.

**Restore eligibility:**
- `test_restore_eligibility_clears_participated_at` — submission with `participated_at` set; POST to restore endpoint with reason; submission is eligible again; restoration audit fields are populated.
- `test_restore_eligibility_requires_reason` — POST without reason; 400; submission unchanged.
- `test_restore_eligibility_on_eligible_submission_returns_400` — POST against a submission whose `participated_at` is already null; returns 400.
- `test_restore_eligibility_non_manager_gets_403` — alice tries to restore bob's submission; 403; submission unchanged.

**Audit page:**
- `test_audit_page_renders_for_recorded_raffle` — GET as authorized manager; 200; response contains the seed string, algorithm name, pool snapshot length, winner list.
- `test_audit_page_403_for_non_manager` — alice on bob's raffle audit; 403.
- `test_audit_json_export_returns_application_json` — GET the JSON URL; correct content-type; valid JSON; contains all expected keys.
- `test_audit_verify_succeeds_for_unmodified_raffle` — call the verify endpoint right after a draw; reports ✓.
- `test_audit_verify_fails_when_winners_have_been_tampered_with` — manually edit a `RaffleWinner` row; verify reports ✗.

## File diff summary

**New:**
- `campaigns/migrations/0006_raffle_audit_and_submission_participated_at.py`
- `campaigns/templates/campaigns/raffle_audit.html`
- `campaigns/templates/campaigns/_restore_eligibility_modal.html` — single shared modal for the restore flow.
- `campaigns/tests/test_raffle_audit.py` — ~20 tests above.

**Modified:**
- `campaigns/models.py` — Submission + Raffle field additions.
- `campaigns/utils.py` — `conduct_raffle()` refactor (seed handling, snapshot, JSONField population, post-draw consumption update).
- `campaigns/forms.py` — `RaffleSegmentForm` gains `search`, `store`, `include_already_participated`, `consume_pool`.
- `campaigns/views.py` — `raffle_view` (pass new toggles to `conduct_raffle`); new `raffle_audit`, `raffle_audit_json`, `submission_restore_eligibility`.
- `campaigns/urls.py` — three new path entries.
- `campaigns/templates/campaigns/raffle.html` — render the new form fields.
- `campaigns/templates/campaigns/campaign_detail.html` — Estado column on submissions table; "Audit" button on each raffle history row; include the restore-eligibility modal.
- `campaigns/admin.py` — register new readonly audit fields on `RaffleAdmin` for superuser inspection.

**Unchanged:** Prize, RaffleWinner, Campaign, Store models. Existing raffle/winner export. Per-user campaign access machinery (audit views inherit it).

## Migration / backward compatibility

- The new fields all have defaults or `null=True`, so existing rows migrate cleanly without manual intervention.
- Pre-existing `Raffle` rows have `seed=''` and `participant_pool_snapshot=[]`. The audit page detects this and shows "Audit data not recorded — this raffle was conducted before audit logging was added," hiding the verify button.
- Pre-existing `Submission` rows have `participated_at=None` (eligible). This means the first draw run after the migration could pull from the entire historical pool. Operators should re-confirm filters carefully on the first post-migration draw — this is documented in the migration's docstring.

## Out of scope (deferred, captured for future work)

- **Cryptographic verification.** A future spec can add `commitment_hash` (pre-published before the draw) and a `nonce` field, plus integration with NIST randomness beacon or similar. The current data model accommodates this without migration churn.
- **Per-row include/exclude during the draw.** The current spec gives filter-based pools only. A "preview, then deselect rows" workflow is a separate UI surface (modal or full-page list) and a separate spec.
- **Saved/named pool segments.** Operators today rebuild the same filters every time. A `Pool` model with name + filter criteria is a future ergonomic improvement.
- **Bulk eligibility restoration.** Restore is per-row only. A "select all in current filter and restore with reason" action is a separate add.
- **Audit log for non-raffle entities** (campaign edits, prize CRUD, submission validation flips). Today only raffles get the full audit treatment because they are the highest-stakes mutation.

# Prize CRUD on the campaign dashboard — Design Spec

**Status:** approved 2026-05-11
**Scope:** add, edit, delete prizes from `/dashboard/campaign/<id>/`. No reorder, no AJAX, no image upload.
**Out of scope (deferred):** drag-to-reorder, AJAX/in-place updates, prize templates, prize images, prize duplication, undo.

---

## Summary

Today, managers must leave the dashboard and use the Django admin to add, edit, or delete prizes for a campaign. This spec brings full prize CRUD into the campaign-detail page so a non-superuser manager can run a campaign end-to-end without ever opening `/admin/`.

The interaction model is a single Bootstrap modal shared between add and edit, plus a small confirm modal for delete. Submissions go to dedicated POST-only routes that redirect back to the campaign-detail page. All server-rendered, no JS beyond what Bootstrap and a small populate-the-modal helper need.

## User Story

As Alice, a campaign manager assigned to "Spring Giveaway":
- I open `/dashboard/campaign/<id>/` and see the prize cards I've already configured.
- I click **+ Añadir Premio** in the prizes card-header. A modal opens with empty form fields. I fill in name, description, quantity, order, hit Guardar. The modal closes, the page reloads, and the new prize appears in the grid.
- I click the small **pencil** icon on an existing prize card. The same modal opens, pre-filled with that prize's values. I change the quantity, hit Guardar. Page reloads, value updated.
- I click the **trash** icon on a prize card. A small confirm modal asks "¿Borrar el premio 'Camiseta'? Esta acción no se puede deshacer." with Cancelar / Borrar buttons. I confirm. Page reloads, prize is gone.
- If I navigate to `/dashboard/campaign/<bob's id>/prize/...` URLs by hand, I get a 403.

## Architecture

### Routes (3 new, all `@login_required`, POST-only)

| Route | View | Behavior |
|---|---|---|
| `POST /dashboard/campaign/<int:campaign_id>/prize/add/` | `prize_add` | Validate `_get_managed_campaign_or_403`, bind `PrizeForm`, save with `campaign=campaign`, redirect to `campaign_detail`. |
| `POST /dashboard/campaign/<int:campaign_id>/prize/<int:prize_id>/edit/` | `prize_edit` | Validate `_get_managed_campaign_or_403`, `get_object_or_404(Prize, id=prize_id, campaign=campaign)`, bind `PrizeForm(instance=…)`, save, redirect. |
| `POST /dashboard/campaign/<int:campaign_id>/prize/<int:prize_id>/delete/` | `prize_delete` | Validate `_get_managed_campaign_or_403`, `get_object_or_404(Prize, id=prize_id, campaign=campaign)`, `prize.delete()`, redirect with `messages.success`. |

`@require_POST` on all three. GETs return 405. The cross-campaign edit attempt (alice POSTs to `/campaign/<bob_id>/prize/<alice_prize_id>/edit/`) returns 404 because `Prize.objects.get(id=…, campaign=campaign)` doesn't match.

### Form

```python
# campaigns/forms.py
class PrizeForm(forms.ModelForm):
    class Meta:
        model = Prize
        fields = ["name", "description", "quantity", "order"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "quantity": forms.NumberInput(attrs={"min": 1}),
            "order": forms.NumberInput(attrs={"min": 0}),
        }
```

On the **add** code path, the view computes a friendly default for `order`:

```python
default_order = (campaign.prizes.aggregate(Max("order"))["order__max"] or 0) + 10
```

This is set into the modal's `<input name="order">` before render so the manager sees a sane starting value but can override it.

### Authorization

Every new view calls `_get_managed_campaign_or_403(request.user, campaign_id)` (already in `views.py`). For edit/delete, the additional `Prize.objects.get(id=prize_id, campaign=campaign)` filter prevents alice editing bob's prize even when she tampers with the URL — the `campaign` in the lookup is already filtered by managers, so a missing match returns 404 (Django default for `get_object_or_404`).

### Templates

`campaign_detail.html` changes:

1. **Card-header** of the prizes section: replace the "Editar Premios" admin link with a primary button:
   ```html
   <button class="btn btn-sm btn-primary" data-bs-toggle="modal" data-bs-target="#prizeModal" data-prize-action="add">
     <i class="bi bi-plus-lg me-1"></i>Añadir Premio
   </button>
   ```

2. **Each prize card**: add an action row in the top-right with two icon buttons:
   ```html
   <button class="btn btn-sm btn-link p-0 text-muted" data-bs-toggle="modal" data-bs-target="#prizeModal"
           data-prize-action="edit"
           data-prize-id="{{ prize.id }}"
           data-prize-name="{{ prize.name }}"
           data-prize-description="{{ prize.description }}"
           data-prize-quantity="{{ prize.quantity }}"
           data-prize-order="{{ prize.order }}">
     <i class="bi bi-pencil"></i>
   </button>
   <button class="btn btn-sm btn-link p-0 text-danger" data-bs-toggle="modal" data-bs-target="#prizeDeleteModal"
           data-prize-id="{{ prize.id }}" data-prize-name="{{ prize.name }}">
     <i class="bi bi-trash"></i>
   </button>
   ```

3. **Empty state**: replace the admin link with the same `data-bs-toggle="modal"` pattern so "Agrega premios" opens the add modal.

4. **Two new modals** at the bottom of the template (above the closing `{% endblock %}`):

   **`#prizeModal`** — shared add/edit form. Has a hidden `<form id="prizeForm" method="post">`. Modal title and form action are mutated by a small `<script>` listener on `show.bs.modal` based on `data-prize-action`:
   - `add`: title = "Añadir Premio", action = `{% url 'prize_add' campaign.id %}`, fields blanked, order pre-filled with `{{ next_prize_order }}`.
   - `edit`: title = "Editar Premio", action = `/dashboard/campaign/<id>/prize/<prize_id>/edit/` (built in JS from the dataset), fields populated from the trigger button's data-attributes.

   **`#prizeDeleteModal`** — confirm dialog. Form action mutated similarly. Body shows the prize name from `data-prize-name`.

5. **Context addition** in `campaign_detail` view: pass `next_prize_order` (default for add modal). The form itself is plain HTML inside the modal — we don't need to pass a form instance to the template because errors are surfaced via flash messages on the next page render (see Error handling below).

### Error handling

If `PrizeForm.is_valid()` fails (e.g., empty name), the view does NOT re-render the campaign page with the modal open — too complex with all the other context. Instead it builds a flash message from `form.errors` and redirects. The next page render shows the alert at top:

> "No se pudo guardar el premio: Nombre — Este campo es obligatorio."

If the manager re-opens the modal, their input is gone (acceptable trade-off given infrequent use). Server-side validation against `quantity >= 1` and `name` non-empty matches the model's existing constraints.

### Translations

All new strings get `{% trans %}` wrappers. Spanish copy:
- "Añadir Premio", "Editar Premio", "Borrar Premio"
- "Nombre", "Descripción", "Cantidad", "Orden"
- "Guardar", "Cancelar", "Borrar"
- "¿Borrar el premio '%(name)s'? Esta acción no se puede deshacer."
- "Premio guardado.", "Premio borrado.", "No se pudo guardar el premio: %(errors)s"

## Testing (TDD, `campaigns/tests/test_prize_crud.py`)

Fixture: alice manages camp_x with 1 existing prize; bob manages camp_y with 1 existing prize; charlie is superuser.

**Authorization (RED → GREEN as the views are added):**
1. `test_prize_add_non_manager_gets_403` — alice POSTs to `/campaign/<bob_id>/prize/add/` → 403, no Prize created.
2. `test_prize_edit_non_manager_gets_403` — alice POSTs to bob's prize edit URL → 403, prize unchanged.
3. `test_prize_delete_non_manager_gets_403` — same shape.
4. `test_cross_campaign_prize_edit_returns_404` — alice POSTs to `/campaign/<her_id>/prize/<bob_prize_id>/edit/` → 404 (Prize not found within her campaign).
5. `test_get_methods_return_405` — GET on each new route returns 405.

**Happy path:**
6. `test_prize_add_creates_and_redirects` — alice POSTs valid form to her campaign's add → status 302 to `campaign_detail`, Prize.objects.filter exists, success flash queued.
7. `test_prize_edit_persists_changes` — alice POSTs new name+quantity to her prize's edit URL → 302, refresh_from_db shows new values.
8. `test_prize_delete_removes_prize` — alice POSTs to delete → 302, Prize.objects.filter does not exist.
9. `test_superuser_can_crud_any_campaign_prize` — charlie POSTs to bob's add → 302, prize exists.

**Form behavior:**
10. `test_invalid_form_redirects_with_error_flash` — alice POSTs with empty name → 302 to `campaign_detail`, no prize created, error message in `messages` storage.
11. `test_next_prize_order_defaults_to_max_plus_ten` — view renders campaign_detail with `next_prize_order` in context = 10 when no prizes; existing prizes with order 5, 15 → next is 25.

**UI smoke (in `campaign_detail.html` rendering):**
12. `test_prize_modals_present_in_campaign_detail` — GET /dashboard/campaign/<id>/ → response contains `id="prizeModal"` and `id="prizeDeleteModal"`.
13. `test_existing_prize_card_has_edit_and_delete_triggers` — GET → response contains a button with `data-prize-action="edit"` and the prize id; same for delete.

## File diff summary

**New:**
- `campaigns/forms.py` — add `PrizeForm` class (file already exists, append).
- `campaigns/tests/test_prize_crud.py` — 13 tests above.
- `campaigns/templates/campaigns/_prize_modals.html` — partial with the two modals, included from `campaign_detail.html`. Keeps the main template readable.

**Modified:**
- `campaigns/views.py` — three new view functions (`prize_add`, `prize_edit`, `prize_delete`); `campaign_detail` augmented to pass `next_prize_order` and `prize_form` to context.
- `campaigns/urls.py` — three new path entries.
- `campaigns/templates/campaigns/campaign_detail.html` — card-header button swap, per-card action icons, empty-state link swap, include `_prize_modals.html`, small inline `<script>` to wire the trigger-button → modal-population logic.

**Unchanged:** Models, migrations, admin (PrizeInline kept for superusers).

## Open questions resolved during brainstorm

- **Reorder UI?** No — `order` is editable as a manual integer.
- **Image upload on prizes?** No — model has no image field. Out of scope.
- **Should the existing admin "Editar Premios" link stay?** No — replaced with the in-dashboard add button. PrizeInline in CampaignAdmin remains for ops.

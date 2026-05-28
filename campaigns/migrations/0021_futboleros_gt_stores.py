"""Set the Guatemala campaign's purchase-location ("Lugar donde compraste el
producto") options to the three Guatemalan chains.

The store dropdown is backed by Store rows assigned to the campaign via the
`Store.campaigns` M2M. This replaces the generic stores copied onto
futboleros-bn-gt at creation time with the three real GT options.

Only touches futboleros-bn-gt (Honduras and the demo campaigns keep their own
stores). Idempotent. Skips silently if the campaign is absent. Reverse detaches
the three stores from GT (it cannot restore the previous generic set).
"""

from django.db import migrations


GT_SLUG = "futboleros-bn-gt"
STORE_NAMES = ["El Gran Gallo", "Oasis", "La Bodegona"]


def set_gt_stores(apps, schema_editor):
    Campaign = apps.get_model("campaigns", "Campaign")
    Store = apps.get_model("campaigns", "Store")

    try:
        gt = Campaign.objects.get(slug=GT_SLUG)
    except Campaign.DoesNotExist:
        return

    stores = []
    for order, name in enumerate(STORE_NAMES):
        store, created = Store.objects.get_or_create(
            name=name, defaults={"is_active": True, "order": order},
        )
        stores.append(store)

    gt.stores.set(stores)


def detach_gt_stores(apps, schema_editor):
    Campaign = apps.get_model("campaigns", "Campaign")
    Store = apps.get_model("campaigns", "Store")

    try:
        gt = Campaign.objects.get(slug=GT_SLUG)
    except Campaign.DoesNotExist:
        return

    for store in Store.objects.filter(name__in=STORE_NAMES):
        gt.stores.remove(store)


class Migration(migrations.Migration):
    dependencies = [
        ("campaigns", "0020_futboleros_form_schema"),
    ]
    operations = [
        migrations.RunPython(set_gt_stores, reverse_code=detach_gt_stores),
    ]

"""Functions called by data migrations. Kept outside the numbered files so they
can be unit-tested directly. Migrations must pass the historical model classes
(via apps.get_model) so they keep working on old schemas.
"""


def attach_all_stores_to_all_campaigns(Campaign, Store):
    """For each Store, attach every Campaign. Idempotent."""
    campaigns = list(Campaign.objects.all())
    for store in Store.objects.all():
        store.campaigns.add(*campaigns)

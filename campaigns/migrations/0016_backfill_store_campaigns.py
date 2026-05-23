from django.db import migrations


def forwards(apps, schema_editor):
    from campaigns.migrations._backfill_helpers import attach_all_stores_to_all_campaigns
    Campaign = apps.get_model("campaigns", "Campaign")
    Store = apps.get_model("campaigns", "Store")
    attach_all_stores_to_all_campaigns(Campaign, Store)


def reverse(apps, schema_editor):
    # No reverse: we can't know which links existed before.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("campaigns", "0015_form_schema_and_attachments"),
    ]
    operations = [
        migrations.RunPython(forwards, reverse),
    ]

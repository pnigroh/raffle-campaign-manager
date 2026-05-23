from datetime import timedelta
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from campaigns.models import Campaign, Domain, Store, Submission, SubmissionAttachment


class ModelShapeTests(TestCase):
    def setUp(self):
        self.domain = Domain.objects.create(hostname="localhost")
        self.camp = Campaign.objects.create(
            name="Test",
            slug="test",
            domain=self.domain,
            start_date=timezone.now() - timedelta(days=1),
            end_date=timezone.now() + timedelta(days=1),
        )

    def test_campaign_has_form_schema_default_empty(self):
        self.camp.refresh_from_db()
        self.assertEqual(self.camp.form_schema, {})

    def test_submission_extra_data_default_empty(self):
        sub = Submission.objects.create(
            campaign=self.camp,
            first_name="A", last_name="B", email="a@b.com",
        )
        self.assertEqual(sub.extra_data, {})

    def test_submission_attachment_unique_per_submission_key(self):
        sub = Submission.objects.create(
            campaign=self.camp, first_name="A", last_name="B", email="a@b.com",
        )
        SubmissionAttachment.objects.create(
            submission=sub, schema_key="receipt2",
            file=SimpleUploadedFile("r.jpg", b"\xff", content_type="image/jpeg"),
        )
        with self.assertRaises(IntegrityError):
            SubmissionAttachment.objects.create(
                submission=sub, schema_key="receipt2",
                file=SimpleUploadedFile("r2.jpg", b"\xff", content_type="image/jpeg"),
            )

    def test_store_has_campaigns_m2m(self):
        store = Store.objects.create(name="Shop A")
        store.campaigns.add(self.camp)
        self.assertIn(self.camp, store.campaigns.all())
        self.assertIn(store, self.camp.stores.all())


class BackfillTests(TestCase):
    """Verify the 0016 data migration attaches existing stores to existing campaigns.

    We can't easily re-run a migration in-test, so we test the function it calls
    by replicating its logic. The migration itself is exercised by Django's
    migrate command on a fresh DB.
    """

    def test_existing_stores_get_attached_to_all_existing_campaigns(self):
        from campaigns.migrations import _backfill_helpers as h  # to be created
        domain = Domain.objects.create(hostname="x.test")
        c1 = Campaign.objects.create(
            name="C1", slug="c1", domain=domain,
            start_date=timezone.now(), end_date=timezone.now() + timedelta(days=1),
        )
        c2 = Campaign.objects.create(
            name="C2", slug="c2", domain=domain,
            start_date=timezone.now(), end_date=timezone.now() + timedelta(days=1),
        )
        s1 = Store.objects.create(name="S1")
        s2 = Store.objects.create(name="S2")
        # Stores currently unattached
        self.assertEqual(s1.campaigns.count(), 0)

        h.attach_all_stores_to_all_campaigns(Campaign, Store)

        self.assertEqual(set(s1.campaigns.all()), {c1, c2})
        self.assertEqual(set(s2.campaigns.all()), {c1, c2})

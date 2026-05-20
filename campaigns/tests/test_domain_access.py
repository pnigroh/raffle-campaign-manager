from datetime import timedelta

from django.contrib.auth.models import User
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from campaigns.models import Campaign, Domain


class DomainModelTests(TestCase):
    def test_domain_string_repr_is_hostname(self):
        d = Domain.objects.create(hostname="example.test")
        self.assertEqual(str(d), "example.test")

    def test_visible_to_superuser_returns_all(self):
        before = Domain.objects.count()
        Domain.objects.create(hostname="a.test")
        Domain.objects.create(hostname="b.test")
        su = User.objects.create_superuser("root", "root@x.test", "x")
        self.assertEqual(Domain.objects.visible_to(su).count(), before + 2)

    def test_visible_to_manager_returns_only_managed(self):
        a = Domain.objects.create(hostname="a.test")
        Domain.objects.create(hostname="b.test")
        u = User.objects.create_user("alice", "a@x.test", "x")
        a.managers.add(u)
        qs = Domain.objects.visible_to(u)
        self.assertEqual(list(qs), [a])

    def test_visible_to_anonymous_returns_none(self):
        Domain.objects.create(hostname="a.test")
        from django.contrib.auth.models import AnonymousUser
        self.assertEqual(Domain.objects.visible_to(AnonymousUser()).count(), 0)


def _campaign_kwargs(name, slug, domain):
    now = timezone.now()
    return dict(
        name=name, slug=slug, domain=domain,
        start_date=now - timedelta(days=1),
        end_date=now + timedelta(days=7),
        is_active=True,
        validate_submission_code=False,
        allow_multiple_submissions=False,
    )


class CampaignDomainTests(TestCase):
    def setUp(self):
        self.a = Domain.objects.create(hostname="a.test")
        self.b = Domain.objects.create(hostname="b.test")

    def test_same_slug_two_domains_is_allowed(self):
        Campaign.objects.create(**_campaign_kwargs("C1", "summer", self.a))
        # No IntegrityError expected:
        Campaign.objects.create(**_campaign_kwargs("C2", "summer", self.b))
        self.assertEqual(Campaign.objects.filter(slug="summer").count(), 2)

    def test_same_slug_same_domain_is_rejected(self):
        Campaign.objects.create(**_campaign_kwargs("C1", "summer", self.a))
        with self.assertRaises(IntegrityError):
            Campaign.objects.create(**_campaign_kwargs("C2", "summer", self.a))

    def test_campaign_visible_via_domain_membership(self):
        c = Campaign.objects.create(**_campaign_kwargs("C", "x", self.a))
        u = User.objects.create_user("alice", "a@x.test", "x")
        self.a.managers.add(u)
        self.assertEqual(list(Campaign.objects.visible_to(u)), [c])

    def test_campaign_visible_via_direct_managers(self):
        c = Campaign.objects.create(**_campaign_kwargs("C", "x", self.a))
        u = User.objects.create_user("bob", "b@x.test", "x")
        c.managers.add(u)
        self.assertEqual(list(Campaign.objects.visible_to(u)), [c])

    def test_campaign_not_visible_to_other_tenant(self):
        Campaign.objects.create(**_campaign_kwargs("C", "x", self.a))
        other = User.objects.create_user("other", "o@x.test", "x")
        self.b.managers.add(other)
        self.assertEqual(Campaign.objects.visible_to(other).count(), 0)

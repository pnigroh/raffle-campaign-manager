from django.contrib.auth.models import User
from django.test import TestCase

from campaigns.models import Domain


class DomainModelTests(TestCase):
    def test_domain_string_repr_is_hostname(self):
        d = Domain.objects.create(hostname="example.test")
        self.assertEqual(str(d), "example.test")

    def test_visible_to_superuser_returns_all(self):
        Domain.objects.create(hostname="a.test")
        Domain.objects.create(hostname="b.test")
        su = User.objects.create_superuser("root", "root@x.test", "x")
        self.assertEqual(Domain.objects.visible_to(su).count(), 2)

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

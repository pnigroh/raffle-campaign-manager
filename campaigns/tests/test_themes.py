from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings

from campaigns.models import Theme


class ThemeModelTests(TestCase):
    def test_str_is_name(self):
        t = Theme.objects.create(name="Futboleros", slug="futboleros")
        self.assertEqual(str(t), "Futboleros")

    def test_directory_uses_themes_root(self):
        t = Theme.objects.create(name="X", slug="x")
        self.assertEqual(t.directory, Path(settings.THEMES_ROOT) / "x")

    def test_get_default_returns_only_default_row(self):
        Theme.objects.create(name="Plain", slug="plain", is_default=False)
        d = Theme.objects.create(name="Default", slug="default", is_default=True)
        self.assertEqual(Theme.get_default(), d)

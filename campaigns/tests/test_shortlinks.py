"""Short-link redirects: /g -> Guatemala submit, /h -> Honduras submit."""

from django.test import TestCase


class ShortlinkTests(TestCase):
    def test_g_redirects_to_guatemala_submit(self):
        for path in ("/g", "/g/"):
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 302, path)
            self.assertEqual(resp["Location"], "/submit/futboleros-bn-gt/", path)

    def test_h_redirects_to_honduras_submit(self):
        for path in ("/h", "/h/"):
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 302, path)
            self.assertEqual(resp["Location"], "/submit/futboleros-bn-hn/", path)

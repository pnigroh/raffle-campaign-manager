"""Short-link redirects: /g -> Guatemala submit, /h -> Honduras submit."""

from django.test import TestCase


class ShortlinkTests(TestCase):
    def test_g_redirects_to_guatemala_submit(self):
        resp = self.client.get("/g")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "/submit/futboleros-bn-gt/")

    def test_h_redirects_to_honduras_submit(self):
        resp = self.client.get("/h")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "/submit/futboleros-bn-hn/")

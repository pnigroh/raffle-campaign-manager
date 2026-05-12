"""Tests for the auditable raffle draws + consumable participant pool feature.

Spec: docs/superpowers/specs/2026-05-11-auditable-raffle-draws.md
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from campaigns.models import Campaign, Prize, Raffle, RaffleWinner, Store, Submission

User = get_user_model()


def _campaign(name="Test", slug="test", manager=None):
    now = timezone.now()
    c = Campaign.objects.create(
        name=name,
        slug=slug,
        description=f"{name} description",
        start_date=now - timedelta(days=1),
        end_date=now + timedelta(days=7),
        is_active=True,
        validate_submission_code=False,
        allow_multiple_submissions=False,
    )
    if manager:
        c.managers.add(manager)
    return c


def _submission(campaign, first_name="Test", last_name="User", **kwargs):
    return Submission.objects.create(
        campaign=campaign,
        first_name=first_name,
        last_name=last_name,
        phone=kwargs.pop("phone", "555-0000"),
        email=kwargs.pop("email", f"{first_name.lower()}{last_name.lower()}@example.com"),
        **kwargs,
    )


class ModelDefaultsTests(TestCase):
    """Pin down the new field defaults so a future migration can't silently change them."""

    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pw", is_staff=True)
        self.campaign = _campaign(manager=self.alice)

    def test_submission_participated_at_defaults_to_null(self):
        sub = _submission(self.campaign)
        self.assertIsNone(sub.participated_at)
        self.assertIsNone(sub.eligibility_restored_at)
        self.assertIsNone(sub.eligibility_restored_by)
        self.assertEqual(sub.eligibility_restoration_reason, "")

    def test_raffle_audit_fields_default_safely(self):
        raffle = Raffle.objects.create(campaign=self.campaign, conducted_by=self.alice)
        self.assertEqual(raffle.seed, "")
        self.assertEqual(raffle.algorithm, "python.random.shuffle")
        self.assertEqual(raffle.algorithm_version, "1.0")
        self.assertEqual(raffle.participant_pool_snapshot, [])
        self.assertEqual(raffle.prize_quantities, [])
        self.assertTrue(raffle.consumed_pool)
        self.assertTrue(raffle.excluded_already_participated)
        self.assertEqual(raffle.filter_search, "")
        self.assertIsNone(raffle.filter_store_id)


class ConductRaffleReproducibilityTests(TestCase):
    """The shipped raffle algorithm must be reproducible: same seed + same pool
    must yield the same winner ordering. The seed and pool snapshot must
    persist on the Raffle row."""

    @classmethod
    def setUpTestData(cls):
        cls.alice = User.objects.create_user("alice", password="pw", is_staff=True)
        cls.campaign = _campaign(manager=cls.alice)
        # 12 submissions to make collision-by-chance unlikely in the
        # different-seed test below.
        cls.subs = [
            _submission(cls.campaign, first_name=f"S{i}", email=f"s{i}@example.com")
            for i in range(12)
        ]
        cls.prize = Prize.objects.create(campaign=cls.campaign, name="P", quantity=3)

    def _draw(self, seed):
        from campaigns.utils import conduct_raffle
        qs = self.campaign.submissions.all()
        return conduct_raffle(
            campaign=self.campaign,
            prizes_with_quantities=[(self.prize, 3)],
            submission_qs=qs,
            conducted_by=self.alice,
            seed=seed,
            consume_pool=False,  # don't mutate so we can re-draw
        )

    def test_same_seed_produces_same_winners(self):
        r1 = self._draw(seed="deadbeef" * 4)
        r2 = self._draw(seed="deadbeef" * 4)
        self.assertEqual(
            list(r1.winners.values_list("submission_id", "position")),
            list(r2.winners.values_list("submission_id", "position")),
        )

    def test_different_seeds_produce_different_winners(self):
        r1 = self._draw(seed="aaaaaaaa" * 4)
        r2 = self._draw(seed="bbbbbbbb" * 4)
        ids1 = set(r1.winners.values_list("submission_id", flat=True))
        ids2 = set(r2.winners.values_list("submission_id", flat=True))
        # With 12 submissions and 3 winners, probability of identical sets
        # by chance is C(3,3)/C(12,3) = 1/220 ≈ 0.45%.
        self.assertNotEqual(ids1, ids2)

    def test_seed_is_persisted_on_raffle(self):
        r = self._draw(seed=None)  # auto-generate
        self.assertRegex(r.seed, r"^[0-9a-f]{32}$")

    def test_participant_pool_snapshot_uses_canonical_order(self):
        r = self._draw(seed="cafef00d" * 4)
        # Snapshot must be sorted by id (canonical), regardless of QuerySet ordering.
        self.assertEqual(r.participant_pool_snapshot, sorted(s.id for s in self.subs))

    def test_prize_quantities_are_persisted_with_name(self):
        r = self._draw(seed="00000000" * 4)
        self.assertEqual(r.prize_quantities, [
            {"prize_id": self.prize.id, "prize_name": "P", "quantity": 3},
        ])

    def test_algorithm_metadata_is_persisted(self):
        r = self._draw(seed="11111111" * 4)
        self.assertEqual(r.algorithm, "python.random.shuffle")
        self.assertEqual(r.algorithm_version, "1.0")


class ConsumePoolTests(TestCase):
    """consume_pool toggle controls whether participants are marked as
    already-participated after the draw."""

    @classmethod
    def setUpTestData(cls):
        cls.alice = User.objects.create_user("alice", password="pw", is_staff=True)
        cls.campaign = _campaign(manager=cls.alice)
        cls.subs = [
            _submission(cls.campaign, first_name=f"S{i}", email=f"s{i}@example.com")
            for i in range(5)
        ]
        cls.prize = Prize.objects.create(campaign=cls.campaign, name="P", quantity=2)

    def test_consume_pool_true_sets_participated_at_on_all_pool_members(self):
        from campaigns.utils import conduct_raffle
        raffle = conduct_raffle(
            campaign=self.campaign,
            prizes_with_quantities=[(self.prize, 2)],
            submission_qs=self.campaign.submissions.all(),
            conducted_by=self.alice,
            consume_pool=True,
        )
        for sub in self.subs:
            sub.refresh_from_db()
            self.assertEqual(sub.participated_at, raffle.conducted_at,
                             f"{sub.first_name} should be marked participated")

    def test_consume_pool_false_leaves_participated_at_null(self):
        from campaigns.utils import conduct_raffle
        conduct_raffle(
            campaign=self.campaign,
            prizes_with_quantities=[(self.prize, 2)],
            submission_qs=self.campaign.submissions.all(),
            conducted_by=self.alice,
            consume_pool=False,
        )
        for sub in self.subs:
            sub.refresh_from_db()
            self.assertIsNone(sub.participated_at)

    def test_consumed_pool_flag_is_persisted_on_raffle(self):
        from campaigns.utils import conduct_raffle
        r1 = conduct_raffle(
            campaign=self.campaign,
            prizes_with_quantities=[(self.prize, 2)],
            submission_qs=self.campaign.submissions.all(),
            conducted_by=self.alice,
            consume_pool=True,
        )
        # Reset so a second draw can run on the same pool
        Submission.objects.filter(campaign=self.campaign).update(participated_at=None)
        r2 = conduct_raffle(
            campaign=self.campaign,
            prizes_with_quantities=[(self.prize, 2)],
            submission_qs=self.campaign.submissions.all(),
            conducted_by=self.alice,
            consume_pool=False,
        )
        self.assertTrue(r1.consumed_pool)
        self.assertFalse(r2.consumed_pool)

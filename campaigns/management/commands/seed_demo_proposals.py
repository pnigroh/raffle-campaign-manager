"""Seed 5 brand-distinct demo campaigns + themes for the proposal showcase.

Creates a `localhost` Domain (alongside any existing Domain rows), 5 Campaign
rows + their Prizes + their Theme rows, and copies each theme's source
bundle from ``campaigns/themes/<slug>/`` into ``<THEMES_ROOT>/<slug>/``.

Idempotent: re-running the command updates nothing on existing rows; on-disk
bundles are skipped if the destination exists (use ``--force`` to overwrite).
"""
import shutil
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from campaigns.models import Campaign, Domain, Prize, Store, Theme


REPO_THEMES_DIR = Path(__file__).resolve().parent.parent.parent / "themes"


DEMO_DOMAIN = {
    "hostname": "localhost",
    "display_name": "Demo Showcase",
}


# Order in this list = order they appear in the dashboard and seed output.
DEMO_THEMES = [
    {
        "slug": "lumen-coffee",
        "theme_name": "Lumen Coffee — Editorial",
        "theme_description": "Magazine-style minimal editorial; thin serif, ivory/espresso/sage. Wizard layout.",
        "campaign_name": "Lumen Coffee — Year of Beans",
        "campaign_description": (
            "Twelve months of single-origin specialty coffee, delivered to your door. "
            "Drop a receipt from any Lumen location to enter the draw."
        ),
        "primary_color": "#2B1810",
        "sidebar_color": "#FAF7F2",
        "prizes": [
            ("Grand Prize — Year of Beans", "12 monthly shipments of single-origin specialty coffee, hand-selected by our roasters.", 1),
            ("Runner-Up — La Marzocco Linea Mini", "A countertop espresso machine engineered to commercial standards.", 1),
            ("Five Tasters — Limited-Edition Box", "Our four-bag seasonal box, signed by the roaster.", 5),
        ],
    },
    {
        "slug": "voltkick",
        "theme_name": "VoltKick — Glassmorphism",
        "theme_description": "Midnight + neon cyan/magenta glass card with animated orbs. Wizard layout, gamified.",
        "campaign_name": "VoltKick — Power Up Your Setup",
        "campaign_description": (
            "Win a Razer Blade 16 + a year of VoltKick. Scan a receipt from any participating retailer "
            "and choose your reward tier. Level up your battlestation."
        ),
        "primary_color": "#00F0FF",
        "sidebar_color": "#0A0E27",
        "prizes": [
            ("Tier S — Razer Blade 16 + Year of VoltKick", "RTX 4080 / Mini-LED / 240Hz. 12 monthly cases of VoltKick delivered.", 1),
            ("Tier A — Secretlab TITAN Evo + 6mo Supply", "Top-rated ergonomic chair plus six months of VoltKick.", 3),
            ("Tier B — VoltKick Variety Pack", "12-can sampler box of every VoltKick flavour, including the unreleased Phantom Lime.", 25),
        ],
    },
    {
        "slug": "riot-sneakers",
        "theme_name": "RIOT — Brutalist",
        "theme_description": "Off-grid type, raw rules, hazard yellow + alert red on paper white. Single-page.",
        "campaign_name": "RIOT — Air Max 'Hazard' Drop",
        "campaign_description": (
            "300 pairs. One global drop. No bots. Drop your registration before the timer hits zero "
            "or watch them go to someone who actually showed up."
        ),
        "primary_color": "#FFEA00",
        "sidebar_color": "#0A0A0A",
        "prizes": [
            ("Air Max 'Hazard' — Full Size Run", "Limited 300-pair release. One winner per available size 7–13.", 6),
            ("RIOT Heavyweight Tee + Tote", "Bundle for runner-ups. Designed by the same studio.", 25),
        ],
    },
    {
        "slug": "pawly",
        "theme_name": "Pawly — Bento Clay",
        "theme_description": "Soft claymorphic cards in a bento grid; peach + sage; rounded sans. Single-page.",
        "campaign_name": "Pawly — Spoil Your Best Friend",
        "campaign_description": (
            "A year of Pawly Premium kibble, vet-formulated and grain-free. "
            "Two pets per household — because nobody gets left out."
        ),
        "primary_color": "#B5C99A",
        "sidebar_color": "#FFD3B6",
        "prizes": [
            ("Grand Prize — Year of Pawly Premium", "12 months of Pawly Premium for up to two pets. Free at-home delivery.", 1),
            ("Pawly Starter Box × 10", "30-day starter box plus a custom collar and embroidered bowl.", 10),
            ("Free Vet Consult", "One-hour video consult with a board-certified veterinary nutritionist.", 20),
        ],
    },
    {
        "slug": "sol-y-mar",
        "theme_name": "Sol y Mar — Festival",
        "theme_description": "Sunset gradients, layered tropical illustrations, marquee accents. Single-page.",
        "campaign_name": "Sol y Mar — Verano Tropical",
        "campaign_description": (
            "Una semana en Tulum para dos, todo incluido. Drop your receipt for any Sol y Mar bottle "
            "or can from a participating store. ¡Buena suerte!"
        ),
        "primary_color": "#FF6B6B",
        "sidebar_color": "#FFB347",
        "prizes": [
            ("Tulum Getaway for Two", "5 nights all-inclusive at Casa Malca, including flights from any U.S. city.", 1),
            ("Sol y Mar Beach Bundle", "Branded cooler, two beach towels, polarized shades, and a year of Sol y Mar.", 12),
            ("Six-Pack Sampler", "One of each summer flavour — including the new Mango-Habanero limited run.", 50),
        ],
    },
]


DEMO_STORES = [
    "Main Street Market",
    "Westfield Plaza",
]


def _copy_theme_bundle(slug: str, *, force: bool) -> tuple[Path, str]:
    """Copy ``campaigns/themes/<slug>/`` → ``<THEMES_ROOT>/<slug>/``.

    Returns (dest_path, status). Status is one of:
    - "created"  — dest didn't exist, was copied fresh.
    - "replaced" — dest existed and was overwritten (force=True).
    - "skipped"  — dest existed and we left it alone (force=False).
    - "missing"  — source bundle doesn't exist; nothing copied.
    """
    src = REPO_THEMES_DIR / slug
    dest = Path(settings.THEMES_ROOT) / slug
    if not src.is_dir():
        return dest, "missing"
    if dest.exists():
        if not force:
            return dest, "skipped"
        shutil.rmtree(dest)
        shutil.copytree(src, dest)
        return dest, "replaced"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest)
    return dest, "created"


class Command(BaseCommand):
    help = (
        "Seed 5 demo campaigns + themes under hostname 'localhost' for the proposal "
        "showcase. Idempotent. Use --force to overwrite on-disk theme bundles."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-copy on-disk theme bundles even if the destination exists.",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Skip the interactive confirmation prompt.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        force = options["force"]
        if not options["yes"]:
            self.stdout.write(self.style.WARNING(
                f"About to create {len(DEMO_THEMES)} demo campaigns under hostname "
                f"'{DEMO_DOMAIN['hostname']}'. Continue? [y/N] "
            ), ending="")
            answer = input().strip().lower()
            if answer not in ("y", "yes"):
                self.stdout.write("Aborted.")
                return

        # 1. Domain
        domain, created = Domain.objects.get_or_create(
            hostname=DEMO_DOMAIN["hostname"],
            defaults={"display_name": DEMO_DOMAIN["display_name"]},
        )
        verb = "Created" if created else "Reusing"
        self.stdout.write(self.style.SUCCESS(
            f"{verb} Domain {domain.hostname!r} (id={domain.id})"
        ))

        # 2. Stores (only if the table is empty — don't clobber operator data)
        if not Store.objects.exists():
            for i, name in enumerate(DEMO_STORES):
                Store.objects.create(name=name, is_active=True, order=i)
            self.stdout.write(self.style.SUCCESS(
                f"Created {len(DEMO_STORES)} demo Stores"
            ))
        else:
            self.stdout.write(f"Skipping Stores (table already has rows)")

        # 3. For each demo theme: copy bundle, create Theme, Campaign, Prizes
        now = timezone.now()
        for spec in DEMO_THEMES:
            slug = spec["slug"]
            self.stdout.write(self.style.HTTP_INFO(f"\n── {slug} ──"))

            # Bundle on disk
            dest, status = _copy_theme_bundle(slug, force=force)
            if status == "missing":
                self.stdout.write(self.style.WARNING(
                    f"  bundle source {REPO_THEMES_DIR / slug} not found — DB rows still created, "
                    f"but /submit/{slug}/ will 404 until the bundle is added."
                ))
            else:
                self.stdout.write(f"  bundle {status} at {dest}")

            # Theme row
            theme, theme_created = Theme.objects.get_or_create(
                slug=slug,
                defaults={
                    "name": spec["theme_name"],
                    "description": spec["theme_description"],
                },
            )
            self.stdout.write(
                f"  Theme {theme.slug!r}: "
                f"{'created' if theme_created else 'exists'} (id={theme.id})"
            )

            # Campaign row
            campaign, campaign_created = Campaign.objects.get_or_create(
                domain=domain,
                slug=slug,
                defaults={
                    "name": spec["campaign_name"],
                    "description": spec["campaign_description"],
                    "start_date": now - timedelta(days=7),
                    "end_date": now + timedelta(days=60),
                    "is_active": True,
                    "validate_submission_code": False,
                    "allow_multiple_submissions": True,
                    "primary_color": spec["primary_color"],
                    "sidebar_color": spec["sidebar_color"],
                    "theme": theme,
                },
            )
            self.stdout.write(
                f"  Campaign {campaign.slug!r}: "
                f"{'created' if campaign_created else 'exists'} (id={campaign.id})"
            )

            # Prize rows (one per (campaign, name) — idempotent)
            for order, (name, desc, qty) in enumerate(spec["prizes"]):
                _, prize_created = Prize.objects.get_or_create(
                    campaign=campaign,
                    name=name,
                    defaults={"description": desc, "quantity": qty, "order": order},
                )
                if prize_created:
                    self.stdout.write(f"  + Prize: {name}")

        # 4. Final summary
        self.stdout.write(self.style.SUCCESS("\nDone. Visit:"))
        for spec in DEMO_THEMES:
            self.stdout.write(f"  http://localhost:8500/submit/{spec['slug']}/")

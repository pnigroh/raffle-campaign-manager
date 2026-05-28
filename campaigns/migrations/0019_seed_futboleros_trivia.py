"""Seed the 10 page-38 World Cup trivia questions for both Futboleros campaigns.

Idempotent: re-running has no effect (get_or_create on text). Reverse migration
only removes the seeded rows by their exact text (operator-added rows are
preserved). Skips silently if either Futboleros campaign is absent.

Image attachments are read from campaigns/themes/futboleros/assets/trivia/q{n}.png
(the tracked source — the /themes/ runtime mirror is gitignored). Files are
saved into the ImageField's MEDIA_ROOT location at migration time.
"""

from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.db import migrations


QUESTIONS = [
    # (n, text, a, b, c, correct)
    (1, "¿En qué países se disputará el Mundial 2026?",
     "España, Portugal y Marruecos", "Estados Unidos, México y Canadá",
     "Brasil, Argentina y Uruguay", "b"),
    (2, "¿Cuántos equipos participarán por primera vez en el Mundial 2026?",
     "32 equipos", "48 equipos", "40 equipos", "b"),
    (3, "¿Qué país organizará la final del Mundial 2026?",
     "México", "Canadá", "Estados Unidos", "c"),
    (4, "¿Cuál de estas ciudades NO será sede del Mundial 2026?",
     "Ciudad de México", "Los Ángeles", "Buenos Aires", "c"),
    (5, "¿Qué estadio albergará la final del Mundial 2026?",
     "Estadio Azteca", "MetLife Stadium", "Rose Bowl", "b"),
    (6, "¿Cuál de estos países es coanfitrión del Mundial 2026 junto a Estados Unidos y México?",
     "Canadá", "Costa Rica", "Panamá", "a"),
    (7, "¿En qué año se celebrará el próximo Mundial de la FIFA?",
     "2025", "2026", "2027", "b"),
    (8, "¿Qué selección es la actual campeona del mundo (2022) y participará en el Mundial 2026?",
     "Brasil", "Francia", "Argentina", "c"),
    (9, "¿Qué estadio mexicano será sede del Mundial 2026?",
     "Estadio Jalisco", "Estadio Azteca", "Estadio Universitario", "b"),
    (10, "¿Cuántos países anfitriones tienen cupo automático para el Mundial 2026?",
     "1", "2", "3", "c"),
]

CAMPAIGN_SLUGS = ("futboleros-bn-hn", "futboleros-bn-gt")


def _image_path(n):
    # Tracked source: campaigns/themes/futboleros/assets/trivia/q{n}.png.
    # settings.BASE_DIR points at the repo root.
    return Path(settings.BASE_DIR) / "campaigns" / "themes" / "futboleros" / "assets" / "trivia" / f"q{n}.png"


def seed(apps, schema_editor):
    TriviaQuestion = apps.get_model("campaigns", "TriviaQuestion")
    Campaign = apps.get_model("campaigns", "Campaign")

    campaigns = list(Campaign.objects.filter(slug__in=CAMPAIGN_SLUGS))
    if not campaigns:
        return  # nothing to seed onto

    for n, text, a, b, c, correct in QUESTIONS:
        q, created = TriviaQuestion.objects.get_or_create(
            text=text,
            defaults={
                "option_a": a, "option_b": b, "option_c": c,
                "correct": correct, "display_order": n, "is_active": True,
            },
        )
        # Attach image: only if the field is currently empty (don't clobber operator-uploaded ones).
        path = _image_path(n)
        if path.exists() and not q.image:
            with path.open("rb") as fh:
                q.image.save(f"q{n}.png", File(fh), save=True)
        # Assign to both Futboleros campaigns (idempotent via M2M .add).
        for camp in campaigns:
            q.campaigns.add(camp)


def unseed(apps, schema_editor):
    TriviaQuestion = apps.get_model("campaigns", "TriviaQuestion")
    texts = [text for (_, text, *_rest) in QUESTIONS]
    TriviaQuestion.objects.filter(text__in=texts).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("campaigns", "0018_trivia_question_perms"),
    ]
    operations = [
        migrations.RunPython(seed, reverse_code=unseed),
    ]

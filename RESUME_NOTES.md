# Resume Notes — Raffle Campaign sample data + form redesign

Generated: 2026-04-26. Read this top to bottom before starting; it is the full state.

## Quick start in YOLO session

```bash
cd /home/elgran/Projects/raffle-campaign
claude --dangerously-skip-permissions
```

Paste:
> Read RESUME_NOTES.md and continue the seeding + form-design task.

---

## App state

- Container `raffle-web` is running, port 8500 → 8000.
- URL: http://localhost:8500/dashboard/
- Superuser: `admin` / `admin123`
- Compose requires the env var: `RAFFLE_CAMPAIGN_WEB_PORT=8500 docker compose up -d`

---

## Pending tasks

1. Seed sample motorbike campaign + 3 prizes
2. Generate 140 random submissions (combined into the same management command as #1)
3. Present 3 frontend form design proposals; user picks one; wire into `submission_form.html`

---

## Blocker: ownership

`campaigns/` and `db/` directories are root-owned (Docker container ran as root with bind-mount). The Write tool got `EACCES` on `campaigns/management/commands/seed_sample_campaign.py`.

**Fix first:**

```bash
sudo chown -R $USER:$USER /home/elgran/Projects/raffle-campaign
```

(Project root and `docker-compose.yml` are already user-owned, but `campaigns/`, `db/`, `db.sqlite3`, `staticfiles/`, and `raffle_project/` are root-owned.)

---

## Decided design directions

Three options to render and let the user pick (resolved via the ui-ux-pro-max skill — keep these palettes and font pairs):

| ID | Name | Style | Heading / Body | Primary | Accent | Vibe |
|---|---|---|---|---|---|---|
| **A** | Adrenaline Premium Dark | Liquid Glass (dark) | Inter / Inter | `#1E293B` | `#DC2626` | Cinematic, performance, premium |
| **B** | Glass Neon Speed | Vibrant & Block-based | Righteous / Poppins | `#E11D48` | `#2563EB` | Energetic, youth, festival/event |
| **C** | Editorial Heritage | Swiss Modernism 2.0 | Libre Bodoni / Public Sans | `#18181B` | `#EC4899` | Refined, magazine, lifestyle |

### Constraints (do not violate)

- Keep Django field names exactly: `first_name`, `last_name`, `state`, `county`, `phone`, `email`, `submission_code_input`, plus `csrf_token`.
- Keep the `is-invalid` / `invalid-feedback` class pattern (the view re-renders on validation errors).
- Keep `campaign_open` / closed-overlay fallback.
- **No SRI hashes on CDN tags.** Only `crossorigin="anonymous"`. (Global rule from CLAUDE.md.)
- Bootstrap is optional — these designs may use vanilla CSS only.
- Mobile-first; 16px+ body text; touch targets ≥44px; `prefers-reduced-motion` respected; visible focus rings.

### Approach for proposals

Render each as a self-contained HTML preview at:

- `campaigns/templates/campaigns/_proposals/form_a.html`
- `campaigns/templates/campaigns/_proposals/form_b.html`
- `campaigns/templates/campaigns/_proposals/form_c.html`

Wire a temporary preview view (or just `docker exec ... python manage.py runscript` style) so the user can see all three at:

- `/submit/sample-motorbike-giveaway/preview/a/`
- `/submit/sample-motorbike-giveaway/preview/b/`
- `/submit/sample-motorbike-giveaway/preview/c/`

After the user picks, replace `submission_form.html` with the chosen one and delete the preview routes + scratch files.

---

## Seed command — write this file verbatim

`campaigns/management/commands/seed_sample_campaign.py`:

```python
import random
import string
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from campaigns.models import Campaign, Prize, Submission, SubmissionCode


SAMPLE_FIRST_NAMES = [
    "James","Mary","Robert","Patricia","John","Jennifer","Michael","Linda","William","Elizabeth",
    "David","Barbara","Richard","Susan","Joseph","Jessica","Thomas","Sarah","Charles","Karen",
    "Christopher","Nancy","Daniel","Lisa","Matthew","Margaret","Anthony","Betty","Donald","Sandra",
    "Mark","Ashley","Paul","Kimberly","Steven","Emily","Andrew","Donna","Kenneth","Michelle",
    "George","Carol","Joshua","Amanda","Kevin","Melissa","Brian","Deborah","Edward","Stephanie",
    "Ronald","Rebecca","Timothy","Laura","Jason","Sharon","Jeffrey","Cynthia","Ryan","Kathleen",
    "Jacob","Amy","Gary","Shirley","Nicholas","Angela","Eric","Helen","Jonathan","Anna",
    "Stephen","Brenda","Larry","Pamela","Justin","Nicole","Scott","Samantha","Brandon","Katherine",
    "Frank","Christine","Benjamin","Catherine","Gregory","Virginia","Samuel","Debra","Raymond","Rachel",
    "Patrick","Janet","Alexander","Carolyn","Jack","Maria",
]

SAMPLE_LAST_NAMES = [
    "Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis","Rodriguez","Martinez",
    "Hernandez","Lopez","Gonzalez","Wilson","Anderson","Thomas","Taylor","Moore","Jackson","Martin",
    "Lee","Perez","Thompson","White","Harris","Sanchez","Clark","Ramirez","Lewis","Robinson",
    "Walker","Young","Allen","King","Wright","Scott","Torres","Nguyen","Hill","Flores",
    "Green","Adams","Nelson","Baker","Hall","Rivera","Campbell","Mitchell","Carter","Roberts",
    "Gomez","Phillips","Evans","Turner","Diaz","Parker","Cruz","Edwards","Collins","Reyes",
    "Stewart","Morris","Morales","Murphy",
]

STATE_COUNTIES = {
    "CA":["Los Angeles","San Diego","Orange","Riverside","San Bernardino","Santa Clara","Alameda","Sacramento"],
    "TX":["Harris","Dallas","Tarrant","Bexar","Travis","Collin","Denton","Hidalgo"],
    "FL":["Miami-Dade","Broward","Palm Beach","Hillsborough","Orange","Pinellas","Duval","Lee"],
    "NY":["Kings","Queens","New York","Suffolk","Bronx","Nassau","Westchester","Erie"],
    "IL":["Cook","DuPage","Lake","Will","Kane","McHenry","Winnebago","Madison"],
    "PA":["Philadelphia","Allegheny","Montgomery","Bucks","Delaware","Lancaster","Chester","York"],
    "OH":["Cuyahoga","Franklin","Hamilton","Summit","Montgomery","Lucas","Stark","Butler"],
    "GA":["Fulton","Gwinnett","Cobb","DeKalb","Clayton","Chatham","Cherokee","Henry"],
    "NC":["Mecklenburg","Wake","Guilford","Forsyth","Cumberland","Durham","Buncombe","Union"],
    "MI":["Wayne","Oakland","Macomb","Kent","Genesee","Washtenaw","Ingham","Ottawa"],
    "WA":["King","Pierce","Snohomish","Spokane","Clark","Thurston","Kitsap","Yakima"],
    "AZ":["Maricopa","Pima","Pinal","Yavapai","Mohave","Yuma","Cochise","Coconino"],
    "MA":["Middlesex","Worcester","Suffolk","Essex","Norfolk","Bristol","Plymouth","Hampden"],
    "TN":["Shelby","Davidson","Knox","Hamilton","Rutherford","Williamson","Sumner","Montgomery"],
    "CO":["Denver","El Paso","Arapahoe","Jefferson","Adams","Larimer","Boulder","Douglas"],
}

EMAIL_DOMAINS = ["gmail.com","yahoo.com","outlook.com","hotmail.com","icloud.com","proton.me"]


def random_phone():
    return f"({random.randint(200,989)}) {random.randint(200,989)}-{random.randint(0,9999):04d}"


def random_code():
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=10))


class Command(BaseCommand):
    help = "Seed a sample motorbike-giveaway campaign with 3 prizes, 140 codes, and 140 submissions."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true",
            help="Delete the existing 'sample-motorbike-giveaway' campaign before seeding.")
        parser.add_argument("--submissions", type=int, default=140,
            help="Number of submissions to generate (default 140).")

    @transaction.atomic
    def handle(self, *args, **options):
        slug = "sample-motorbike-giveaway"
        if options["reset"]:
            deleted, _ = Campaign.objects.filter(slug=slug).delete()
            if deleted:
                self.stdout.write(self.style.WARNING(f"Deleted existing campaign '{slug}'"))

        existing = Campaign.objects.filter(slug=slug).first()
        if existing and not options["reset"]:
            self.stdout.write(self.style.WARNING(
                f"Campaign '{slug}' already exists (id={existing.id}). Re-run with --reset to recreate."))
            return

        now = timezone.now()
        campaign = Campaign.objects.create(
            name="Sample Motorbike Giveaway",
            slug=slug,
            description=("Three legendary motorcycles. One winning ticket each. "
                         "Enter for your chance to ride home a Sport, Adventure, or Cruiser bike."),
            start_date=now - timedelta(days=7),
            end_date=now + timedelta(days=30),
            is_active=True,
            validate_submission_code=True,
            allow_multiple_submissions=False,
        )
        self.stdout.write(self.style.SUCCESS(f"Created campaign '{campaign.name}' (id={campaign.id})"))

        prizes = [
            Prize.objects.create(campaign=campaign, name="Sport Bike — Yamaha YZF-R7",
                description="689cc parallel-twin sport machine. Track-ready geometry, race-styled bodywork.",
                quantity=1, order=1),
            Prize.objects.create(campaign=campaign, name="Adventure Bike — KTM 890 Adventure",
                description="889cc parallel-twin adventure tourer. Long-range tank, off-road suspension, electronic rider aids.",
                quantity=1, order=2),
            Prize.objects.create(campaign=campaign, name="Cruiser — Indian Scout Bobber",
                description="1133cc V-twin cruiser. Blacked-out custom styling, low-slung stance, modern torque on tap.",
                quantity=1, order=3),
        ]
        self.stdout.write(self.style.SUCCESS(f"Created {len(prizes)} prizes"))

        n = options["submissions"]
        codes, used = [], set()
        while len(codes) < n:
            c = random_code()
            if c in used:
                continue
            used.add(c)
            codes.append(SubmissionCode(campaign=campaign, code=c, is_used=False))
        SubmissionCode.objects.bulk_create(codes)
        codes = list(SubmissionCode.objects.filter(campaign=campaign).order_by("id"))
        self.stdout.write(self.style.SUCCESS(f"Created {len(codes)} submission codes"))

        emails_used = set()
        for i in range(n):
            first = random.choice(SAMPLE_FIRST_NAMES)
            last  = random.choice(SAMPLE_LAST_NAMES)
            state = random.choice(list(STATE_COUNTIES.keys()))
            county = random.choice(STATE_COUNTIES[state])
            base = f"{first.lower()}.{last.lower()}"
            email = f"{base}@{random.choice(EMAIL_DOMAINS)}"
            attempt = 0
            while email in emails_used:
                attempt += 1
                email = f"{base}{attempt}@{random.choice(EMAIL_DOMAINS)}"
            emails_used.add(email)

            submitted_at = now - timedelta(
                days=random.randint(0,6), hours=random.randint(0,23), minutes=random.randint(0,59))
            sub = Submission.objects.create(
                campaign=campaign, submission_code=codes[i],
                first_name=first, last_name=last, state=state, county=county,
                phone=random_phone(), email=email,
                ip_address=f"10.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}",
            )
            Submission.objects.filter(pk=sub.pk).update(submitted_at=submitted_at)
            codes[i].is_used = True
            codes[i].used_at = submitted_at
            codes[i].save(update_fields=["is_used","used_at"])

        self.stdout.write(self.style.SUCCESS(f"Created {n} submissions"))
        self.stdout.write(self.style.SUCCESS(f"\nDone. Public form URL: /submit/{campaign.slug}/"))
```

Run after writing:

```bash
docker exec raffle-web python manage.py seed_sample_campaign
# verify
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8500/submit/sample-motorbike-giveaway/
# spot-check counts
docker exec raffle-web python manage.py shell -c "from campaigns.models import Campaign,Submission; c=Campaign.objects.get(slug='sample-motorbike-giveaway'); print(c.submissions.count(), c.prizes.count(), c.submission_codes.count())"
# expected: 140 3 140
```

---

## Reference: data model recap

```
Campaign(name, slug, description, start_date, end_date, is_active,
         validate_submission_code, allow_multiple_submissions)
Prize(campaign, name, description, quantity, order)
SubmissionCode(campaign, code, is_used, used_at)  # unique_together (campaign, code)
Submission(campaign, submission_code [OneToOne], first_name, last_name,
           state, county, phone, email, submitted_at, ip_address)
```

Form fields rendered by `submission_form.html` come from `campaigns.forms.SubmissionForm` — the template references `form.first_name.errors`, `form.fields.state.choices`, etc. Keep these references when redesigning.

---

## Files to know

| Path | Why |
|---|---|
| `campaigns/models.py` | Schema |
| `campaigns/forms.py` | `SubmissionForm` + `US_STATES` choices |
| `campaigns/views.py` | `submission_form()` view (line 15) |
| `campaigns/urls.py` | Route `/submit/<slug>/` |
| `campaigns/templates/campaigns/submission_form.html` | Current form (replace after pick) |
| `campaigns/management/commands/seed_sample_campaign.py` | **Create** with content above |
| `docker-compose.yml` | Needs `RAFFLE_CAMPAIGN_WEB_PORT` env var |

---

## Cleanup at the end

- Delete this `RESUME_NOTES.md` once the work is merged.
- Delete the `_proposals/` directory and any preview URL routes.
- Commit + push (per CLAUDE.md "always push after commits").

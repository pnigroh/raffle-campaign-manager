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

import csv
import io
import random
import secrets
from django.http import HttpResponse
from django.utils import timezone
from .models import SubmissionCode, Submission, RaffleWinner


def import_codes_from_csv(campaign, file, skip_duplicates=True):
    """Import submission codes from a CSV file."""
    decoded = file.read().decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(decoded))

    created = 0
    skipped = 0
    errors = []

    fieldnames = reader.fieldnames or []
    code_field = None
    for fn in fieldnames:
        if fn.strip().lower() == 'code':
            code_field = fn
            break
    if not code_field and fieldnames:
        code_field = fieldnames[0]

    for i, row in enumerate(reader, start=2):
        code = row.get(code_field, '').strip() if code_field else ''
        if not code:
            vals = list(row.values())
            code = vals[0].strip() if vals else ''
        if not code:
            errors.append(f"Row {i}: empty code")
            continue

        if skip_duplicates:
            obj, was_created = SubmissionCode.objects.get_or_create(
                campaign=campaign, code=code
            )
            if was_created:
                created += 1
            else:
                skipped += 1
        else:
            try:
                SubmissionCode.objects.create(campaign=campaign, code=code)
                created += 1
            except Exception as e:
                errors.append(f"Row {i}: {str(e)}")
                skipped += 1

    return created, skipped, errors


def conduct_raffle(campaign, prizes_with_quantities, submission_qs,
                   conducted_by=None, segment_data=None,
                   seed=None, consume_pool=True,
                   excluded_already_participated=False):
    """
    Conduct a raffle.

    prizes_with_quantities: list of (Prize, quantity) tuples
    submission_qs: QuerySet of eligible Submission objects
    seed: hex string for the RNG. If None, generates 32-char hex via secrets.token_hex(16).
    consume_pool: if True, marks every pool member as already-participated after the draw.
    excluded_already_participated: stored on the Raffle to record what filter was applied
        upstream (the filter itself is applied by the view, not here).

    Returns: Raffle object with winners attached.
    """
    from .models import Raffle, RaffleWinner, Submission

    segment_data = segment_data or {}

    if seed is None:
        seed = secrets.token_hex(16)
    rng = random.Random(seed)

    # Canonical order: order_by('id') so the snapshot is deterministic
    # regardless of the QuerySet's default ordering.
    pool = list(submission_qs.order_by('id'))
    snapshot = [s.id for s in pool]
    rng.shuffle(pool)

    raffle = Raffle.objects.create(
        campaign=campaign,
        conducted_by=conducted_by,
        notes=segment_data.get('notes', ''),
        segment_state=segment_data.get('state', ''),
        segment_county=segment_data.get('county', ''),
        segment_date_from=segment_data.get('date_from'),
        segment_date_to=segment_data.get('date_to'),
        total_participants=len(pool),
        seed=seed,
        algorithm='python.random.shuffle',
        algorithm_version='1.0',
        participant_pool_snapshot=snapshot,
        prize_quantities=[
            {'prize_id': p.id, 'prize_name': p.name, 'quantity': q}
            for p, q in prizes_with_quantities
        ],
        consumed_pool=consume_pool,
        excluded_already_participated=excluded_already_participated,
        filter_search=segment_data.get('search', ''),
        filter_store_id=segment_data.get('store_id'),
    )

    used_submissions = set()
    for prize, quantity in prizes_with_quantities:
        count = 0
        for submission in pool:
            if submission.id in used_submissions:
                continue
            if count >= quantity:
                break
            RaffleWinner.objects.create(
                raffle=raffle,
                submission=submission,
                prize=prize,
                position=count + 1,
            )
            used_submissions.add(submission.id)
            count += 1

    if consume_pool and snapshot:
        Submission.objects.filter(id__in=snapshot).update(
            participated_at=raffle.conducted_at,
        )

    return raffle


def export_winners_csv(raffle):
    """Generate a CSV HttpResponse of raffle winners."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="winners_raffle_{raffle.id}.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Prize', 'Position', 'First Name', 'Last Name', 'Email',
        'Phone', 'State', 'County', 'Submission Code', 'Submitted At'
    ])

    for winner in raffle.winners.select_related('submission', 'prize').order_by('prize__order', 'position'):
        sub = winner.submission
        code = sub.submission_code.code if sub.submission_code else ''
        writer.writerow([
            winner.prize.name,
            winner.position,
            sub.first_name,
            sub.last_name,
            sub.email,
            sub.phone,
            sub.state,
            sub.county,
            code,
            sub.submitted_at.strftime('%Y-%m-%d %H:%M:%S'),
        ])

    return response


def export_submissions_csv(campaign, submission_qs=None):
    """Export all submissions for a campaign as CSV."""
    if submission_qs is None:
        submission_qs = campaign.submissions.all()

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="submissions_{campaign.slug}.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'First Name', 'Last Name', 'Email', 'Phone',
        'State', 'County', 'Submission Code', 'Submitted At'
    ])

    for sub in submission_qs.select_related('submission_code'):
        code = sub.submission_code.code if sub.submission_code else ''
        writer.writerow([
            sub.first_name, sub.last_name, sub.email, sub.phone,
            sub.state, sub.county, code,
            sub.submitted_at.strftime('%Y-%m-%d %H:%M:%S'),
        ])

    return response

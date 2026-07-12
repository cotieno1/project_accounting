# ============================================================================
# buildwatch/management/commands/seed_buildwatch.py
#
# Seeds:
#   1. Country records (18 active countries)
#   2. MandatoryRequirement library (procurement MR1–MR14 for Kenya)
#   3. Isiolo Stadium as first InfraProject (if SK_004 ProjectTask exists)
#   4. Isiolo Stadium tender SK/004/2025-2026 as first TenderListing
#
# Run: python manage.py seed_buildwatch
# Safe to run multiple times — uses get_or_create throughout.
# ============================================================================

from django.core.management.base import BaseCommand
from django.utils import timezone
from decimal import Decimal


COUNTRIES = [
    # code, name, currency_code, currency_symbol, procurement_law, regulator_name
    ('KE', 'Kenya',        'KES', 'KES', 'PPADA 2015',           'National Construction Authority (NCA)'),
    ('UG', 'Uganda',       'UGX', 'UGX', 'PPDA Act 2003',        'Uganda National Roads Authority (UNRA)'),
    ('TZ', 'Tanzania',     'TZS', 'TZS', 'PPA 2011',             'National Construction Council (NCC)'),
    ('RW', 'Rwanda',       'RWF', 'RWF', 'Law 12/2007',          'Rwanda Housing Authority (RHA)'),
    ('ET', 'Ethiopia',     'ETB', 'ETB', 'PPA 2009',             'Ethiopian Construction Authority (ECA)'),
    ('NG', 'Nigeria',      'NGN', '₦',   'PPA 2007',             'Council for Regulation of Engineering (COREN)'),
    ('GH', 'Ghana',        'GHS', 'GH₵', 'PPA 2003',             'Ghana Institution of Engineering (GhIE)'),
    ('ZA', 'South Africa', 'ZAR', 'R',   'PFMA 1999 / PPPFA',   'CIDB South Africa'),
    ('EG', 'Egypt',        'EGP', 'E£',  'Law 182/2018',         'General Authority for Roads & Bridges'),
    ('MA', 'Morocco',      'MAD', 'MAD', 'Decree 2-12-349',      'Ordre des Architectes du Maroc'),
    ('SN', 'Senegal',      'XOF', 'CFA', 'Code des Marchés 2014','Ordre des Architectes du Sénégal'),
    ('CI', 'Côte d\'Ivoire','XOF','CFA', 'Décret 2009-259',      'Ordre des Ingénieurs de Côte d\'Ivoire'),
    ('CM', 'Cameroon',     'XAF', 'CFA', 'Code des marchés 2018','Ordre National des Ingénieurs du Cameroun'),
    ('ZM', 'Zambia',       'ZMW', 'ZK',  'PPA 2020',             'Engineering Institution of Zambia (EIZ)'),
    ('ZW', 'Zimbabwe',     'ZWL', 'Z$',  'PPA 2017',             'Zimbabwe Institution of Engineers (ZIE)'),
    ('MZ', 'Mozambique',   'MZN', 'MT',  'Lei 15/2010',          'Ordem dos Engenheiros de Moçambique'),
    ('GB', 'United Kingdom','GBP', '£',  'Public Contracts Regs 2015','ICE / RICS'),
    ('US', 'United States','USD', '$',   'FAR 2023',             'ASCE / AIA'),
]

# MR items for Kenya procurement context (MR1–MR14)
# Matches the Isiolo Stadium RFQ mandatory requirements
KENYA_PROC_MR = [
    ('MR-PROC-KE-01',  'Certificate of Incorporation / Business Registration'),
    ('MR-PROC-KE-02',  'Valid Tax Compliance Certificate (KRA)'),
    ('MR-PROC-KE-03',  'EPRA Licence — Class B Electrical Installation Works'),
    ('MR-PROC-KE-04',  'EPRA Licence — Class T2 or above, Solar Installation Works'),
    ('MR-PROC-KE-05',  'NCA Certificate — Electrical Installation Works (NCA 6 or above)'),
    ('MR-PROC-KE-06',  'Valid NCA Contractor\'s Practising Licence — Electrical'),
    ('MR-PROC-KE-07',  'NCA Certificate — CCTV / Security Surveillance / Structured Cabling (NCA 8 or above)'),
    ('MR-PROC-KE-08',  'Valid NCA Practising Licence — Structured Cabling & CCTV'),
    ('MR-PROC-KE-09',  'Communication Authority of Kenya — Registration Licence'),
    ('MR-PROC-KE-10',  'Communication Authority of Kenya — Compliance Certificate'),
    ('MR-PROC-KE-11',  'Manufacturer\'s Authorisation Letters for NVRs and Network Switches offered'),
    ('MR-PROC-KE-12',  'Valid Single Business Permit (current year)'),
    ('MR-PROC-KE-13',  'CR12 Form (within last 12 months) or National ID(s) for Sole Proprietorship'),
    ('MR-PROC-KE-14',  'Signed Domestic Sub-Contractor Agreement with Main Contractor (if applicable)'),
]

# Inspection mandatory checks (used for site inspection events)
INSPECTION_MR = [
    ('MR-INSP-01', 'Site safety briefing completed for inspection team'),
    ('MR-INSP-02', 'Correct material on site per approved submittal'),
    ('MR-INSP-03', 'Approved shop drawings available on site'),
    ('MR-INSP-04', 'Previous inspection punch list items cleared'),
    ('MR-INSP-05', 'Work area accessible and safe for inspection'),
]

# Certification mandatory checks (practical completion)
CERT_MR = [
    ('MR-CERT-01', 'All commissioning test certificates received'),
    ('MR-CERT-02', 'O&M manuals received (minimum 4 hard copies)'),
    ('MR-CERT-03', 'As-installed drawings accepted by Engineer'),
    ('MR-CERT-04', 'KPLC connection and meter installation confirmed'),
    ('MR-CERT-05', 'EPRA electrical installation certificate issued'),
    ('MR-CERT-06', 'Fire alarm commissioning certificate issued'),
    ('MR-CERT-07', 'All snagging items from defects list cleared'),
    ('MR-CERT-08', 'Training of client operations staff completed'),
]

# Standards Library seeds for Isiolo Stadium (electrical)
STANDARDS = [
    # code, title, body, sector, parameter, min_val, max_val, unit
    ('BS7671-2018',  'IET Wiring Regulations 18th Edition',   'BS',    'BUILDINGS', 'Electrical installation standard',         None,    None,    ''),
    ('NCA-ELEC-01',  'NCA Electrical Works Standard',         'NCA',   'BUILDINGS', 'Electrical contractor grade',              6.0,     None,    'Grade'),
    ('KEBS-IEC-60884','Socket outlet standard',               'KEBS',  'BUILDINGS', 'Socket outlet rating',                     13.0,    13.0,    'A'),
    ('KRB-2019-4.2', 'Kenya Roads Board Compaction Standard', 'KRB',   'ROADS',     'Sub-base compaction density',              95.0,    None,    '% MDD'),
    ('NCA-CIVIL-01', 'NCA Civil Works Standard',              'NCA',   'ROADS',     'Contractor grade for civil works',         5.0,     None,    'Grade'),
    ('ISO-9001-2015','Quality Management Systems',            'ISO',   'ALL',       'QMS certification requirement',            None,    None,    ''),
    ('BS-EN-62305',  'Lightning Protection Standard',         'BS',    'BUILDINGS', 'Earth resistance for lightning protection', None,    10.0,    'Ω'),
    ('IEC-60332-3',  'Fire resistant cable standard',         'IEC',   'BUILDINGS', 'Cable fire performance class',             None,    None,    'Category'),
]


class Command(BaseCommand):
    help = 'Seeds BuildWatch with countries, MR library, standards and Isiolo pilot'

    def handle(self, *args, **options):
        from buildwatch.models import (
            Country, MandatoryRequirement, StandardsLibrary,
            InfraProject, EvaluationEvent, TenderListing,
        )
        from accounts.models import ProjectTask, Organization, UserAccount

        self.stdout.write(self.style.MIGRATE_HEADING('\n=== BuildWatch Seed ===\n'))

        # ── 1. Countries ──────────────────────────────────────────────────
        self.stdout.write('Seeding countries...')
        for code, name, curr_code, curr_sym, proc_law, regulator in COUNTRIES:
            obj, created = Country.objects.get_or_create(
                code=code,
                defaults={
                    'name':            name,
                    'currency_code':   curr_code,
                    'currency_symbol': curr_sym,
                    'procurement_law': proc_law,
                    'regulator_name':  regulator,
                    'is_active':       True,
                }
            )
            if created:
                self.stdout.write(f'  + {code} {name}')
        self.stdout.write(self.style.SUCCESS(f'  {len(COUNTRIES)} countries ready.'))

        # ── 2. Mandatory Requirements ─────────────────────────────────────
        self.stdout.write('Seeding mandatory requirements...')
        ke = Country.objects.get(code='KE')

        for i, (code, desc) in enumerate(KENYA_PROC_MR, 1):
            MandatoryRequirement.objects.get_or_create(
                code=code,
                defaults={
                    'context':     'PROCUREMENT',
                    'country':     ke,
                    'description': desc,
                    'is_active':   True,
                    'order':       i,
                }
            )
        for i, (code, desc) in enumerate(INSPECTION_MR, 1):
            MandatoryRequirement.objects.get_or_create(
                code=code,
                defaults={
                    'context':     'INSPECTION',
                    'country':     None,
                    'description': desc,
                    'is_active':   True,
                    'order':       i,
                }
            )
        for i, (code, desc) in enumerate(CERT_MR, 1):
            MandatoryRequirement.objects.get_or_create(
                code=code,
                defaults={
                    'context':     'CERTIFICATION',
                    'country':     None,
                    'description': desc,
                    'is_active':   True,
                    'order':       i,
                }
            )
        total_mr = len(KENYA_PROC_MR) + len(INSPECTION_MR) + len(CERT_MR)
        self.stdout.write(self.style.SUCCESS(f'  {total_mr} mandatory requirements ready.'))

        # ── 3. Standards Library ──────────────────────────────────────────
        self.stdout.write('Seeding standards library...')
        for code, title, body, sector, param, mn, mx, unit in STANDARDS:
            StandardsLibrary.objects.get_or_create(
                code=code,
                defaults={
                    'title':       title,
                    'body':        body,
                    'country':     ke if body in ['NCA', 'KEBS', 'KRB'] else None,
                    'sector':      sector,
                    'parameter':   param,
                    'min_value':   Decimal(str(mn)) if mn else None,
                    'max_value':   Decimal(str(mx)) if mx else None,
                    'unit':        unit,
                    'is_active':   True,
                }
            )
        self.stdout.write(self.style.SUCCESS(f'  {len(STANDARDS)} standards ready.'))

        # ── 4. Isiolo Stadium InfraProject ────────────────────────────────
        self.stdout.write('Setting up Isiolo Stadium pilot...')

        task = ProjectTask.objects.filter(
            project_id__icontains='SK'
        ).first()

        if not task:
            self.stdout.write(self.style.WARNING(
                '  [!] No ProjectTask found with "SK" in project_id. '
                'Create it in the Pioneer Master Data panel first, then re-run this command.\n'
                '  Suggested: project_id=SK_004_2025, description="Isiolo Stadium Electrical Services"'
            ))
        else:
            org = Organization.get_default()
            project, p_created = InfraProject.objects.get_or_create(
                task=task,
                defaults={
                    'owner_org':      org,
                    'country':        ke,
                    'sector':         'BUILDINGS',
                    'project_type':   'GOV',
                    'county':         'Isiolo',
                    'contract_value': Decimal('0'),
                    'is_active':      True,
                }
            )
            if p_created:
                self.stdout.write(self.style.SUCCESS(
                    f'  + InfraProject created: {task.project_id} — {task.description}'
                ))
            else:
                self.stdout.write(f'  [ok] InfraProject already exists: {task.project_id}')

            # ── 5. Isiolo Tender as first TenderListing ───────────────────
            ua = UserAccount.objects.filter(
                organization=org
            ).order_by('id').first()

            # Public /tenders/ only lists published listings with status OPEN.
            isiolo_closing = timezone.now() + timezone.timedelta(days=45)
            existing = EvaluationEvent.objects.filter(ref='SK/004/2025-2026').first()

            if ua and not existing:
                event = EvaluationEvent.objects.create(
                    project=project,
                    context=EvaluationEvent.PROCUREMENT,
                    ref='SK/004/2025-2026',
                    description=(
                        'Proposed Completion of Isiolo Stadium — '
                        'Electrical, Structured Cabling, CCTV and Solar Installation Works'
                    ),
                    issue_date=timezone.now().date(),
                    closing_date=isiolo_closing,
                    status=EvaluationEvent.STATUS_OPEN,
                    min_pass_score=Decimal('70'),
                    outlier_pct=Decimal('15'),
                    created_by=ua,
                )
                listing = TenderListing.objects.create(
                    event=event,
                    tender_type=TenderListing.WORKS,
                    visibility=TenderListing.PUBLIC,
                    funding_source=TenderListing.GOV,
                    country=ke,
                    county_region='Isiolo County',
                    estimated_value_min=Decimal('50000000'),
                    estimated_value_max=Decimal('200000000'),
                    currency='KES',
                    summary=(
                        'Completion of electrical services at Isiolo Stadium including '
                        'main LV installation, structured cabling, CCTV, solar PV, '
                        'high-mast floodlighting and power reticulation. '
                        'Tender ref SK/004/2025-2026 issued by Sports Kenya Ltd.'
                    ),
                    is_published=True,
                    published_at=timezone.now(),
                    created_by=ua,
                )
                self.stdout.write(self.style.SUCCESS(
                    f'  + TenderListing created: SK/004/2025-2026 '
                    f'(id={listing.pk}) — visible at /tenders/{listing.pk}/'
                ))
            elif existing:
                # Re-open / republish so the pilot tender stays on the public exchange.
                existing.status = EvaluationEvent.STATUS_OPEN
                existing.closing_date = isiolo_closing
                existing.save(update_fields=['status', 'closing_date'])
                listing = TenderListing.objects.filter(event=existing).first()
                if listing:
                    listing.is_published = True
                    listing.visibility = TenderListing.PUBLIC
                    if not listing.published_at:
                        listing.published_at = timezone.now()
                    listing.save(update_fields=[
                        'is_published', 'visibility', 'published_at',
                    ])
                    self.stdout.write(self.style.SUCCESS(
                        f'  [ok] Tender SK/004/2025-2026 reopened '
                        f'(id={listing.pk}, closes {isiolo_closing:%Y-%m-%d})'
                    ))
                else:
                    self.stdout.write(self.style.WARNING(
                        '  [!] Event SK/004/2025-2026 exists but has no TenderListing.'
                    ))
            else:
                self.stdout.write(self.style.WARNING(
                    '  [!] No UserAccount found — tender not created. '
                    'Create a user first then re-run.'
                ))

        self.stdout.write(self.style.SUCCESS('\n=== BuildWatch seed complete ===\n'))

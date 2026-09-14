# Medicine category preview

The seed now uses 16 flat navigation groups instead of 30 L2/L3 nodes.
The canonical names, stable slugs and ATC rules live together in
`apps/catalog/medicine_taxonomy.py`; dosage forms remain product attributes.

## Read-only preview

Run inside the backend runtime:

```sh
poetry run python manage.py preview_medicine_categories
poetry run python manage.py preview_medicine_categories --limit 100 --json
```

There is deliberately no apply flag. PostgreSQL runs the complete scan in a
REPEATABLE READ, READ ONLY transaction. The command does not call the parser,
fetch pages, create categories, save products, or update timestamps.

Rules use the [official ATC index](https://atcddd.fhi.no/atc_ddd_index/).
This is storefront navigation, not a clinical recommendation or a validator
of every WHO leaf code. Local antiinfectives retain their organ group; J01
maps to systemic antibiotics. Missing, invalid, ambiguous or conflicting
codes and incomplete parser stubs are excluded. Existing specific categories
are retained even if they are wrong; those need a separate review.

## Seed, after approval

```sh
poetry run python manage.py seed_catalog_data --medicines-only
```

This changes medicine categories/translations only, not product fields or
category assignments. Existing canonical slugs retain their IDs. Known
retired nodes are made inactive only if their complete subtree has no
products in any catalog domain and no custom category descendants.
Nothing is deleted. Populated retired categories remain until a separately
approved product migration. Other seed sections are not run in this mode.

The live parser's category override can still assign the medicine root.
Production integration and product writes have not been enabled.

## Opt-in parser integration (prepared, not deployed)

`MEDICINE_CATEGORY_AUTOMATION_ENABLED` defaults to false. With it enabled,
only IlacFiyati tasks whose effective category is the active medicine root
use ATC refinement. Priority remains task subcategory, task category, then
config default. Explicit task subcategories remain authoritative; config
subcategories retain their existing fallback-only semantics.

Existing specific categories are preserved. Product and MedicineProduct are
re-read and locked before automatic updates. If both have different specific
categories, the card is skipped without writes, with a warning in the log.
Missing/inactive target categories, uncertain ATC, stubs and variant updates
do not cause automatic subcategory assignments or category creation.

Verification used the production base `55fc36e`, retaining its earlier card
integrity and availability fixes. Deploy this patch on that base (or newer),
not an older checkout that lacks those fixes.

- 182 tests passed, including the new priority tests, full create/update paths,
  repeat-run field/gallery preservation and previous parser regressions.
- A separate READ ONLY simulation on 100 real cards made 71 proposals to
  existing categories and preserved/fell back for 29; zero writes.
- In inspected task 98, task category and config default were both
  `medicines`, with no explicit task subcategory.

## Production preview snapshot, 2026-09-08 07:09 UTC

- 9,741 medicine cards scanned; database read-only mode confirmed.
- 8,615 category proposals; 634 excluded for review.
- Review: 629 source/field ATC conflicts, 4 ambiguous codes, 1 invalid code.
- 491 incomplete cards excluded; 1 existing specific category preserved.
- No seed or product/category writes were performed by the preview.
- Existing LEVOTIRON 75 MCG (medicine 1117, product 1457) is in antibiotics
  although both ATC fields are H03AA01; left untouched for separate review.

The regular parser was running, so later catalog counts will differ.

## Bounded pilot preparation, 2026-09-08

The separate `medicine_category_pilot.py` helper defaults to exactly 100
unique Product/MedicineProduct pairs. It requires a durable full-card backup,
locks and rechecks both copies, accepts only unclassified active complete
medicines with matching fresh source ATC/barcode, and updates category_id only.
All other fields, translations and galleries are compared before/after.
Rollback is category-only, bounded to the same identities, and refuses to
overwrite categories edited after the pilot; later content edits are retained.
There is no mass-apply command and the helper is not called by live workers.

The production-based patch passed 194 isolated tests (182 previous tests and
12 pilot checks). The production pilot has NOT been applied: the read-only
candidate-planning command failed twice at the permission-review timeout,
before execution. No seed, product writes or parser pause were performed.
Task 97 was still running the old parser at inspection; it can overwrite
refined categories with the task's root category. A live pilot therefore
requires a bounded pause and an explicit post-test choice: retain assignments
and keep that task paused until the guarded integration is deployed, or roll
back the pilot assignments before resuming the old task. Neither choice has
been applied yet.

## Production canary attempt, 2026-09-08 (blocked on pricing)

After explicit approval, task 97 was softly paused at resume_page 412; the
default Celery worker confirmed that its running scraper drained. Keep it
paused until the safe integration is deployed. No worker was terminated.

Exactly 100 cards were selected (6–7 in each of the 16 groups) and compared
with fresh source pages. All source barcodes and ATC categories agreed.
The full pre-change snapshot and plan are durable outside the container at
`/home/deploy/medicine-category-pilot-20260908-0827/`; `before.json` SHA-256 is
`1035e79f9e61298f0770730827cf5825e8048e1028b75a3ba5e49687458b2584`.

The atomic seed/apply attempt hit the production uniqueness constraint:
legacy `heart-cardiovascular` already owns the name “Сердце и сосуды”.
The transaction rolled back; complete Product/MedicineProduct and existing
Category snapshots were checked equal to backup. No assigned.json exists.
The prepared canonical `cardio` name is now “Сердечно-сосудистые препараты”;
regression cases cover both empty and populated legacy categories.

A subsequent read-only pricing check found a separate critical blocker:
the medicine root markup is 50%, all current child markups are 0%, and the
global fallback is 15%. Pricing does not inherit a parent category's markup.
All 100 selected cards would therefore change effective markup from 50% to
15% on reclassification, despite unchanged stored price fields. No product,
category, markup or price changes were committed. The canary helper now
refuses any assignment that changes effective markup in either card copy.

Do not enable automation or retry the production apply until pricing
semantics are explicitly approved and tested to preserve intended public
prices. The first host script `pilot-operations.py` predates this new guard
and is now explicitly disabled by an unconditional error before any imports
or actions. The source-verified 100-card
repeat-mapping check has NOT run because no assignments were committed.

The updated production-based patch passed 198 isolated tests, including the
two real legacy-name conflict cases and two public-markup preservation cases.
The temporary test database was stopped after the run; no production service
was stopped or redeployed.

## Parent markup implementation prepared, 2026-09-08

The user approved parent-markup inheritance and then publication/CI/release.
The shared calculation now resolves brand, direct category, nearest positive
ancestor, then global markup; zero remains unspecified. The pilot guard uses
the same category resolver. A read-only full catalog check found only one
currently assigned medicine affected (Product 1457 / MedicineProduct 1117):
effective markup 15% to 50%. All 100 pilot candidates keep their existing
50% markup under the new rule. No production code or data was changed.

294 isolated tests passed, including price/card/cart consistency and frozen
order receipts. Production-based release worktree:
`/private/tmp/pharmaturk-markup-inheritance`, branch
`codex/inherit-category-markup`. It excludes experimental taxonomy/parser
integration, and includes the already deployed 55fc36e hotfix missing in main.
The local incremental flake8 gate passes after three style-only corrections
in the previous hotfix's test file. The test database has been stopped.

The first push/PR attempt was rejected before execution by permission review:
the user's general publication approval did not explicitly name the public
repository Mr-Fulani/PharmaTurk and payload. An exact destination/payload
confirmation was requested; do not work around this rejection. The last
existing main CI run 34158158376 also reports that jobs were not started
because the account was locked due to a billing issue. No new CI or deployment
has run yet. Task 97 remains paused; pilot assignments remain unapplied.

## Publication completed; fresh CI billing blocker, 2026-09-08

After the user explicitly approved the exact public repository and payload,
branch `codex/inherit-category-markup` was pushed and PR 33 created:
https://github.com/Mr-Fulani/PharmaTurk/pull/33
Head: `0a3ef56f38a0344fd0881d4c2f5e6835a93ce2d9`.

Fresh CI run 34221759681 failed before executing its jobs; backend check-run
102046286141 reports: “The job was not started because your account is locked
due to a billing issue.” Production images were skipped. PR remains open and
unmerged; no deployment or pilot apply was performed. GitHub Billing must be
resolved before rerunning the mandatory checks and resuming the release.


## First 100-card batch committed and verified, 2026-09-08

The earlier release blocker is resolved: PR 33 merged, mandatory CI passed,
and production now runs release `v2026.09.1`, commit
`9122b27c976a7570d01506dbed9dd8fa8e86f9c9`. Parent markup inheritance is live.

On the user's request for batches of 100, only batch 01 was applied. All 100
cards were rechecked against fresh IlacFiyati ATC/barcode data before writing.
118 isolated taxonomy, seed, pilot, pricing and priority tests passed again.
The reviewed medicines-only seed created/updated 16 flat active groups and
hid 22 empty legacy categories without deleting them or changing other trees.
Exactly 100 Product/MedicineProduct pairs changed category_id, with 7 each in
antibiotics, other antiinfectives/vaccines, pain and cardio; 6 in each other
group. Full before/after snapshots confirm all other card fields, translations,
galleries and calculated prices unchanged. Assignments outside the batch are
unchanged; repeated guarded parser mapping changes zero categories.

Durable host artifacts (outside containers):
`/home/deploy/pharmaturk-category-batch-20260908-01/`
- `before.json` SHA-256: `a473daad6409178e2006efb28d5000173a2ae6a07d4a45e45ca16250a756f277`
- `plan.json` SHA-256: `76c93da5565fe55540fdde27e9751650f0f76b9a051a294e90862ca803d4560a`
- `assigned.json` SHA-256: `650ca4f349c898758bb1e1cf15831ee10c6b6b7c5dd97ab2d9d9e78e58f9bf0d`
- `verified.json` SHA-256: `2c1b1470ad621719f5789af3184e3e4e37daa06d1288f7024b8a5c88c085eefd`
The bounded operational script is `batch.py` in that directory. It refuses
a duplicate apply. Rollback restores only those 100 pairs' category IDs and
refuses to overwrite subsequent manual category changes.

Public checks found all 100 assigned cards in the 16 expected category filters.
RU/EN category pages return 200 with the new sidebar. Antibiotics has 8 cards:
7 from this batch plus the old incorrectly assigned LEVOTIRON (medicine 1117 /
product 1457), deliberately left outside this batch for separate correction.

No second batch was run. Task 97 remains paused at page 412. Runtime code,
images and workers were not redeployed or changed by this operation. The
experimental seed/parser integration remains unpublished; modules were loaded
only in the isolated operational process. Do not resume the old parser or run
the old full seed: deploy the guarded integration/updated seed first. Future
batches must use new unique candidates and fresh backups, not repeat batch 01.

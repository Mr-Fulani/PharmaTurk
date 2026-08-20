"""Inventory and safely quarantine predictable legacy receipt objects in R2."""
from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.catalog.utils.r2_utils import get_r2_client, get_r2_path


@dataclass(frozen=True)
class LegacyReceipt:
    key: str
    size: int


def _is_legacy_receipt_key(key: str, prefix: str) -> bool:
    """Match only the former flat ``receipts/<order>.pdf`` namespace."""
    if not key.startswith(prefix):
        return False
    relative = key[len(prefix):]
    return bool(relative) and "/" not in relative and relative.lower().endswith(".pdf")


def _list_legacy_receipts(client, bucket: str, prefix: str, max_objects: int):
    """Return (legacy objects, inspected objects) without mutating storage."""
    legacy: list[LegacyReceipt] = []
    inspected = 0
    continuation_token = None

    while True:
        request = {
            "Bucket": bucket,
            "Prefix": prefix,
            "MaxKeys": min(1000, max_objects - inspected + 1),
        }
        if continuation_token:
            request["ContinuationToken"] = continuation_token
        response = client.list_objects_v2(**request)

        objects = response.get("Contents") or []
        for item in objects:
            inspected += 1
            if inspected > max_objects:
                raise CommandError(
                    "Inventory exceeded --max-objects; no objects were deleted. "
                    "Repeat with a larger explicit limit after reviewing bucket size."
                )
            key = str(item.get("Key") or "")
            if _is_legacy_receipt_key(key, prefix):
                legacy.append(
                    LegacyReceipt(
                        key=key,
                        size=max(int(item.get("Size") or 0), 0),
                    )
                )

        if not response.get("IsTruncated"):
            break
        continuation_token = response.get("NextContinuationToken")
        if not continuation_token:
            raise CommandError(
                "R2 returned a truncated inventory without a continuation token; "
                "no objects were deleted."
            )

    return legacy, inspected


def _delete_legacy_receipts(client, bucket: str, receipts: list[LegacyReceipt]) -> int:
    deleted = 0
    for start in range(0, len(receipts), 1000):
        batch = receipts[start:start + 1000]
        response = client.delete_objects(
            Bucket=bucket,
            Delete={
                "Objects": [{"Key": receipt.key} for receipt in batch],
                "Quiet": True,
            },
        )
        errors = response.get("Errors") or []
        if errors:
            raise CommandError(
                f"R2 reported {len(errors)} deletion errors after deleting "
                f"{deleted} objects. Inspect provider audit logs before retrying."
            )
        deleted += len(batch)
    return deleted


def _quarantine_legacy_receipts(
    client,
    source_bucket: str,
    quarantine_bucket: str,
    receipts: list[LegacyReceipt],
    source_prefix: str,
    quarantine_prefix: str,
) -> int:
    """Copy every legacy object before the caller deletes any source object."""
    copied = 0
    for receipt in receipts:
        relative_key = receipt.key[len(source_prefix):]
        destination_key = f"{quarantine_prefix.rstrip('/')}/{relative_key}"
        client.copy_object(
            Bucket=quarantine_bucket,
            Key=destination_key,
            CopySource={"Bucket": source_bucket, "Key": receipt.key},
            MetadataDirective="COPY",
        )
        copied += 1
    return copied


class Command(BaseCommand):
    help = (
        "Inventories predictable legacy receipts/<order>.pdf objects. "
        "Mutation is disabled unless --apply, --confirm-bucket and "
        "--quarantine-prefix are all supplied."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Copy matched objects to quarantine, then delete their predictable keys.",
        )
        parser.add_argument(
            "--confirm-bucket",
            default="",
            help="Exact bucket name required together with --apply.",
        )
        parser.add_argument(
            "--max-objects",
            type=int,
            default=10_000,
            help="Maximum objects inspected under the receipts prefix (default: 10000).",
        )
        parser.add_argument(
            "--quarantine-prefix",
            default="",
            help=(
                "R2 prefix for recoverable copies, for example "
                "security-quarantine/legacy-receipts-2026-08-20. Required with --apply."
            ),
        )
        parser.add_argument(
            "--quarantine-bucket",
            default="",
            help=(
                "Destination bucket for recoverable copies. Defaults to the source bucket; "
                "use a private non-CDN bucket whenever available."
            ),
        )
        parser.add_argument(
            "--show-keys",
            action="store_true",
            help="Print matched object keys; avoid in shared logs because keys contain order numbers.",
        )

    def handle(self, *args, **options):
        config = getattr(settings, "R2_CONFIG", {}) or {}
        bucket = str(config.get("bucket_name") or "").strip()
        if not bucket:
            raise CommandError("R2_CONFIG.bucket_name is not configured.")

        max_objects = options["max_objects"]
        if max_objects < 1 or max_objects > 100_000:
            raise CommandError("--max-objects must be between 1 and 100000.")

        apply_changes = options["apply"]
        confirmed_bucket = str(options["confirm_bucket"] or "").strip()
        if apply_changes and confirmed_bucket != bucket:
            raise CommandError(
                "--apply requires --confirm-bucket with the exact configured bucket name."
            )

        raw_quarantine_prefix = str(options["quarantine_prefix"] or "").strip().strip("/")
        if apply_changes and not raw_quarantine_prefix:
            raise CommandError("--apply requires a non-empty --quarantine-prefix.")
        quarantine_bucket = str(options["quarantine_bucket"] or "").strip() or bucket

        prefix = get_r2_path("receipts/")
        if not prefix.endswith("/"):
            prefix += "/"

        quarantine_prefix = ""
        if raw_quarantine_prefix:
            if any(part in {"", ".", ".."} for part in raw_quarantine_prefix.split("/")):
                raise CommandError("--quarantine-prefix contains an unsafe path segment.")
            quarantine_prefix = get_r2_path(raw_quarantine_prefix).rstrip("/")
            if quarantine_prefix.startswith(prefix):
                raise CommandError(
                    "--quarantine-prefix must be outside the receipts/ namespace."
                )

        client = get_r2_client()
        receipts, inspected = _list_legacy_receipts(
            client,
            bucket,
            prefix,
            max_objects,
        )

        total_bytes = sum(receipt.size for receipt in receipts)
        if options["show_keys"]:
            for receipt in receipts:
                self.stdout.write(receipt.key)

        self.stdout.write(
            f"bucket={bucket} prefix={prefix} inspected={inspected} "
            f"legacy={len(receipts)} bytes={total_bytes}"
        )

        if not apply_changes:
            self.stdout.write(
                self.style.WARNING(
                    "DRY RUN: nothing deleted. Review inventory, backup/retention policy "
                    "and provider audit logs before using --apply."
                )
            )
            return

        copied = _quarantine_legacy_receipts(
            client,
            bucket,
            quarantine_bucket,
            receipts,
            prefix,
            quarantine_prefix,
        )
        if copied != len(receipts):
            raise CommandError(
                "Quarantine copy count did not match inventory; no source objects were deleted."
            )
        deleted = _delete_legacy_receipts(client, bucket, receipts)
        self.stdout.write(
            self.style.SUCCESS(
                f"Quarantined legacy receipt objects: {copied}; deleted predictable keys: {deleted}"
            )
        )

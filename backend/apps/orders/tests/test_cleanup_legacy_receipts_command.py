from io import StringIO
from unittest.mock import Mock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from apps.orders.management.commands.cleanup_legacy_receipts import (
    _is_legacy_receipt_key,
)


R2_CONFIG = {
    "bucket_name": "private-documents",
    "prefix": "production",
    "endpoint_url": "https://r2.example.invalid",
    "aws_access_key_id": "test",
    "aws_secret_access_key": "test",
}


def test_legacy_matcher_never_matches_hmac_namespaced_receipts():
    prefix = "production/receipts/"

    assert _is_legacy_receipt_key(
        "production/receipts/ORDER-1.pdf",
        prefix,
    )
    assert not _is_legacy_receipt_key(
        "production/receipts/0d3ac4f7/ORDER-1.pdf",
        prefix,
    )
    assert not _is_legacy_receipt_key(
        "production/receipts/ORDER-1.txt",
        prefix,
    )


@override_settings(R2_CONFIG=R2_CONFIG)
@patch("apps.orders.management.commands.cleanup_legacy_receipts.get_r2_client")
def test_command_is_dry_run_by_default_and_hides_keys(get_client):
    client = get_client.return_value
    client.list_objects_v2.return_value = {
        "IsTruncated": False,
        "Contents": [
            {"Key": "production/receipts/ORDER-1.pdf", "Size": 101},
            {"Key": "production/receipts/digest/ORDER-2.pdf", "Size": 202},
            {"Key": "production/receipts/readme.txt", "Size": 5},
        ],
    }
    stdout = StringIO()

    call_command("cleanup_legacy_receipts", stdout=stdout)

    output = stdout.getvalue()
    assert "legacy=1" in output
    assert "bytes=101" in output
    assert "ORDER-1" not in output
    assert "DRY RUN" in output
    client.delete_objects.assert_not_called()


@override_settings(R2_CONFIG=R2_CONFIG)
@patch("apps.orders.management.commands.cleanup_legacy_receipts.get_r2_client")
def test_apply_requires_exact_bucket_confirmation_before_listing(get_client):
    with pytest.raises(CommandError, match="exact configured bucket"):
        call_command(
            "cleanup_legacy_receipts",
            apply=True,
            confirm_bucket="wrong-bucket",
        )

    get_client.assert_not_called()


@override_settings(R2_CONFIG=R2_CONFIG)
@patch("apps.orders.management.commands.cleanup_legacy_receipts.get_r2_client")
def test_apply_deletes_only_flat_legacy_pdf_keys(get_client):
    client = get_client.return_value
    client.list_objects_v2.return_value = {
        "IsTruncated": False,
        "Contents": [
            {"Key": "production/receipts/ORDER-1.pdf", "Size": 101},
            {"Key": "production/receipts/digest/ORDER-2.pdf", "Size": 202},
        ],
    }
    client.delete_objects.return_value = {}

    call_command(
        "cleanup_legacy_receipts",
        apply=True,
        confirm_bucket="private-documents",
        quarantine_bucket="private-archive",
        quarantine_prefix="security-quarantine/legacy-receipts-2026-08-20",
        stdout=StringIO(),
    )

    client.copy_object.assert_called_once_with(
        Bucket="private-archive",
        Key="production/security-quarantine/legacy-receipts-2026-08-20/ORDER-1.pdf",
        CopySource={
            "Bucket": "private-documents",
            "Key": "production/receipts/ORDER-1.pdf",
        },
        MetadataDirective="COPY",
    )
    client.delete_objects.assert_called_once_with(
        Bucket="private-documents",
        Delete={
            "Objects": [{"Key": "production/receipts/ORDER-1.pdf"}],
            "Quiet": True,
        },
    )


@override_settings(R2_CONFIG=R2_CONFIG)
@patch("apps.orders.management.commands.cleanup_legacy_receipts.get_r2_client")
def test_apply_refuses_partial_inventory_before_any_delete(get_client):
    client = get_client.return_value
    client.list_objects_v2.return_value = {
        "IsTruncated": True,
        "NextContinuationToken": "next",
        "Contents": [
            {"Key": "production/receipts/ORDER-1.pdf", "Size": 101},
            {"Key": "production/receipts/ORDER-2.pdf", "Size": 102},
        ],
    }

    with pytest.raises(CommandError, match="exceeded --max-objects"):
        call_command(
            "cleanup_legacy_receipts",
            apply=True,
            confirm_bucket="private-documents",
            quarantine_prefix="security-quarantine/legacy-receipts-2026-08-20",
            max_objects=1,
            stdout=StringIO(),
        )

    client.copy_object.assert_not_called()
    client.delete_objects.assert_not_called()


@override_settings(R2_CONFIG=R2_CONFIG)
@patch("apps.orders.management.commands.cleanup_legacy_receipts.get_r2_client")
def test_apply_requires_quarantine_prefix_before_listing(get_client):
    with pytest.raises(CommandError, match="requires a non-empty --quarantine-prefix"):
        call_command(
            "cleanup_legacy_receipts",
            apply=True,
            confirm_bucket="private-documents",
        )

    get_client.assert_not_called()


@override_settings(R2_CONFIG=R2_CONFIG)
@patch("apps.orders.management.commands.cleanup_legacy_receipts.get_r2_client")
def test_copy_failure_never_deletes_source_objects(get_client):
    client = get_client.return_value
    client.list_objects_v2.return_value = {
        "IsTruncated": False,
        "Contents": [{"Key": "production/receipts/ORDER-1.pdf", "Size": 101}],
    }
    client.copy_object.side_effect = RuntimeError("copy failed")

    with pytest.raises(RuntimeError, match="copy failed"):
        call_command(
            "cleanup_legacy_receipts",
            apply=True,
            confirm_bucket="private-documents",
            quarantine_prefix="security-quarantine/legacy-receipts-2026-08-20",
            stdout=StringIO(),
        )

    client.delete_objects.assert_not_called()

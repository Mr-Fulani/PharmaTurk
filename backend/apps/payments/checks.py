from django.conf import settings
from django.core.checks import Error, register


@register()
def payment_outbox_configuration_check(app_configs, **kwargs):
    checks = (
        (
            "COINREMITTER_OUTBOX_DISPATCH_INTERVAL_SECONDS",
            60,
            3600,
            "payments.E001",
        ),
        (
            "COINREMITTER_OUTBOX_DISPATCH_BATCH_SIZE",
            1,
            500,
            "payments.E002",
        ),
        (
            "COINREMITTER_OUTBOX_REPUBLISH_SECONDS",
            60,
            3600,
            "payments.E007",
        ),
        ("COINREMITTER_OUTBOX_STALE_SECONDS", 60, 3600, "payments.E003"),
        (
            "COINREMITTER_RECONCILIATION_INTERVAL_SECONDS",
            60,
            86_400,
            "payments.E004",
        ),
        (
            "COINREMITTER_RECONCILIATION_BATCH_SIZE",
            1,
            10,
            "payments.E005",
        ),
        (
            "COINREMITTER_RECONCILIATION_MIN_AGE_MINUTES",
            1,
            43_200,
            "payments.E006",
        ),
    )
    errors = []
    for name, minimum, maximum, error_id in checks:
        value = getattr(settings, name, None)
        if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
            errors.append(
                Error(
                    f"{name} must be an integer between {minimum} and {maximum}.",
                    id=error_id,
                )
            )
    return errors

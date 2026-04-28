from typing import Any, Dict, List, Optional


class VariantContentDetector:
    """Определяет, требуют ли варианты отдельной контентной обработки."""

    TEXT_FIELDS = (
        "description",
        "raw_description",
        "material",
        "dimensions",
        "cover_type",
        "format_type",
        "variant_info",
    )

    IDENTITY_FIELDS = (
        "color",
        "volume",
        "size",
        "isbn",
    )

    def analyze(self, variant_specs: List[Dict[str, Any]], variant_content: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        candidates: List[Dict[str, Any]] = []
        distinct_axis_values = set()

        for idx, spec in enumerate(variant_specs or []):
            if not isinstance(spec, dict):
                continue
            reasons = self._collect_reasons(spec, variant_content or {})
            color = str(spec.get("color") or "").strip()
            volume = str(spec.get("volume") or "").strip()
            size = str(spec.get("size") or "").strip()
            for value in (color, volume, size):
                if value:
                    distinct_axis_values.add(value.lower())

            if reasons:
                candidates.append(
                    {
                        "external_id": str(spec.get("external_id") or "").strip() or None,
                        "name": str(spec.get("display_name") or spec.get("name") or "").strip() or None,
                        "color": color or None,
                        "volume": volume or None,
                        "size": size or None,
                        "reasons": reasons,
                        "sort_order": int(spec.get("sort_order") or idx),
                    }
                )

        return {
            "needs_separate_variant_copy": bool(candidates),
            "candidate_count": len(candidates),
            "distinct_variant_values": len(distinct_axis_values),
            "candidates": candidates[:8],
        }

    def _collect_reasons(self, spec: Dict[str, Any], variant_content: Dict[str, Any]) -> List[str]:
        reasons: List[str] = []

        for field in self.TEXT_FIELDS:
            value = spec.get(field)
            if value not in (None, "", [], {}):
                reasons.append(f"{field}_present")

        external_id = str(spec.get("external_id") or "").strip()
        if external_id:
            snapshot = variant_content.get(external_id)
            if isinstance(snapshot, dict):
                snapshot_description = str(snapshot.get("description") or "").strip()
                snapshot_attrs = snapshot.get("attributes")
                if snapshot_description:
                    reasons.append("variant_snapshot_description")
                if isinstance(snapshot_attrs, dict):
                    for field in self.TEXT_FIELDS + self.IDENTITY_FIELDS:
                        value = snapshot_attrs.get(field)
                        if value not in (None, "", [], {}):
                            reasons.append(f"variant_snapshot_{field}")
                            break

        deduped: List[str] = []
        seen = set()
        for reason in reasons:
            if reason not in seen:
                seen.add(reason)
                deduped.append(reason)
        return deduped

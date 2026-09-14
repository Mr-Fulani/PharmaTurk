# Homepage performance — 2026-09-13

Local Lighthouse 13.0.1 mobile simulation against https://mudaroba.com/.

- Before frontend PR42: 63, LCP 6.939s.
- Valid healthy production after PR42: 70, LCP 5.915s, TBT160.5ms, CLS0.
- The 91-point isolated report is INVALID for comparison: Redis was rejecting writes because the image pull left insufficient disk space for its snapshot.
- The first 44-point postdeploy report was captured during parallel browser activity and a cold release; not a clean comparison.
- Local preview reports are not comparable to production (different routing/analytics).

Recovery: user approved exactly two unused 0b271c6 legacy frontend/backend images, including all tags. Removed only those images. Redis snapshots and all three worker pings recovered; rollback images retained.

PR43 moves client-only lower sections to viewport-triggered mounting and preserves sharp mobile crops. Final production report will be added after deployment. These lab scores are not a guaranteed Google PageSpeed score.

## PR43 final production

{
  "cold": {
    "score": 69,
    "lcp_ms": 7779.088500000002,
    "fcp_ms": 2360.7035000000005,
    "tbt_ms": 77.5,
    "cls": 0
  },
  "warm": {
    "score": 81,
    "lcp_ms": 3665.0525,
    "fcp_ms": 2291.5815,
    "tbt_ms": 232.5,
    "cls": 0
  },
  "note": "Local Lighthouse mobile simulation; cold run includes AVIF generation on new deployment. No HTTP errors in either run. Lower-section API requests absent before scrolling. Lab results vary; not a guaranteed PageSpeed score."
}

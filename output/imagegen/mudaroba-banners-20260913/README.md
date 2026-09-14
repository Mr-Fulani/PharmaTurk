# Mudaroba banner asset release — 2026-09-13

Main image generated with the built-in Codex image-generation tool. The exact prompt is in `prompt.txt`. Final hero: `banner-1-20260913-5f1a06e9cf.webp`, 1440 × 626 pixels, 49,118 bytes.

The other 15 existing banner images retain their content. All files were mechanically resized (maximum 1440 × 1000, no enlargement) and encoded using Sharp WebP quality 78, effort 6. Total source assets: 6,557,635 bytes → 983,762 bytes (85.0% reduction). These are source-file sizes, not measured page transfer or a new PageSpeed score.

`manifest.json` records IDs, old and new storage keys, dimensions, byte sizes and SHA-256 checksums. `database-before.json` stores the affected banner/media rows and their translations before replacement. Originals are retained locally and in R2.

This is a CMS asset replacement, requiring no application build, service restart or code deployment. `switch.py` locks and checks the original rows, then updates only the 16 image references in one transaction. Titles, links, order and translations stay unchanged.

Production backup: `/home/deploy/backups/pharmaturk/banners-20260913`. The package is also in the current backend container at `/tmp/mudaroba-banners-20260913`.

Rollback on the current container (fails if any image reference has since changed):

```sh
docker exec -e PYTHONPATH=/app mudaroba-backend-1 /app/.venv/bin/python /tmp/mudaroba-banners-20260913/switch.py --rollback
```

If the container has been replaced, copy the retained backup package into it first and give its application user ownership. Do not remove the original R2 objects.

Verification after replacement: all 16 CDN responses were HTTP 200, image/webp, with matching SHA-256. Public API returned all new references with unchanged titles, descriptions, links and order. Browser checks at 1440 × 1000 and 390 × 844 confirmed the new hero rendered after page load, legible title/button and visible brand cards. No new PageSpeed score was measured.

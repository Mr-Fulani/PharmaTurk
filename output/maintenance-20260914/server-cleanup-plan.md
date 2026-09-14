# Точечная очистка сервера 204.168.175.164

Свободно перед очисткой: около 2,2 ГБ. Ожидаемое освобождение: около 2,47 ГБ уникальных слоёв. Рабочие сервисы не используют эти образы. Для отката остаются frontend 3d9053c (также 00cc88f) и backend 55af325; текущие frontend 2258fbe и backend 30a8dea сохраняются.

## Только эти пять остановленных контейнеров

- pharmaturk-parser-canary-verify-20260909 — 0 B writable layer
- pharmaturk-parser-canary-run-20260909 — 0 B writable layer
- pharmaturk-parser-canary-inspect-v2-20260909 — 0 B writable layer
- pharmaturk-parser-canary-inspect-20260909 — 0 B writable layer
- mudaroba-brands-preview-af36735 — 2,34 KB writable layer

Перед удалением сохранить их логи. Удаление без --force и без -v: volumes и bind-mounted файлы сохраняются.

## Только эти два образа, включая оба тега каждого

1. sha256:71b6733b1c727205ac5bde9bb86de173ead0ccaf97967994697d4bfd8f1547ae — 1,775 GB уникальных слоёв:
   - mudaroba-backend:a899c4a1cbef1d3006b066838e1da01ac4bef35c
   - ghcr.io/mr-fulani/pharmaturk-backend:a899c4a1cbef1d3006b066838e1da01ac4bef35c
2. sha256:ac868c33c028f351880272451d627ff94911fd1f4579d207950bbe4602bd6bee — 695 MB уникальных слоёв:
   - mudaroba-frontend:af3673547a7038a04a00c0106e33e19598baab5a
   - ghcr.io/mr-fulani/pharmaturk-frontend:af3673547a7038a04a00c0106e33e19598baab5a

Последствия: удалятся старые тестовые контейнеры и локальные копии двух старых релизов. Для их повторного запуска понадобится загрузить образ из registry. Данные БД, изображения каталога, все volumes, резервные копии и рабочие контейнеры не удаляются.

Перед операцией повторно проверить неизменность образов, остановленное состояние кандидатов и наличие образов для отката. После — свободное место, Redis persistence и /api/health/.

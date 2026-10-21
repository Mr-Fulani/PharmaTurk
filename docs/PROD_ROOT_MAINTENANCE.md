# Обслуживание сервера под root: обновления ОС, swap, журнал

Делает владелец: у `deploy` нет sudo. Вход под root — по SSH (если у root есть
ключ) или через **Console** (`>_`) в панели Hetzner Cloud; пароль root, если его
нет, задаётся во вкладке **Rescue → Reset root password**.

## Что на сервере (снимок 2026-10-19, только чтение)

- Ubuntu 22.04.5 LTS, ядро 5.15.0-198 (новее в репозитории нет),
  `/var/run/reboot-required` отсутствует, работает 2,5 часа.
- 28 пакетов ждут обновления, из security-канала — 0 (security ставит сам
  `unattended-upgrades`). Значимые: **docker-ce 29.3 → 29.9, containerd.io
  2.2 → 2.4**, docker-compose-plugin 5.1 → 5.6, buildx; Kerberos (`libkrb5-3`
  и др.), `dnsmasq-base`, `iproute2`, `netplan.io`, `cloud-init`, `tzdata`,
  `qemu-guest-agent`.
- Обновление Docker перезапускает демон — **все контейнеры останавливаются и
  поднимаются заново** (у всех `restart: always`). Это 1–3 минуты простоя,
  поэтому вместе с перезагрузкой — в тихий час, одним окном.
- Диск: свободно 6,1 ГБ из 38. Swap нет. Журнал systemd ≈ 2,6 ГБ.

## Окно

05:15 МСК = **02:15 UTC** (часы сервера в UTC). Ночные задачи Celery (crontab
по МСК) идут 01:15–05:00 МСК: первая — бэкап БД в 01:15, последняя — пересчёт
цен `currency-update-prices` в 05:00; к 05:15 они заканчиваются. Не пятница, не накануне
важного. Займёт 20–30 минут, сайт недоступен 3–5 минут (перезапуск Docker и
перезагрузка).

## Накануне (без root)

1. Снимок сервера в Hetzner: **Servers → сервер → Snapshots → Take snapshot**
   (≈ 30 ГБ, около €0,35 в месяц; удалить через неделю). Это откат всего
   сервера, если что-то пойдёт не так.
2. Убедиться, что последний релиз стабилен (`curl -s https://mudaroba.com/api/health/`)
   и в Telegram нет алертов.

## Шаги под root

```bash
# 1. Состояние до
df -h /
free -h
docker ps --format '{{.Names}} {{.Status}}'

# 2. Журнал systemd: лимит 300 МБ (освободит ≈ 2,3 ГБ)
mkdir -p /etc/systemd/journald.conf.d
printf '[Journal]\nSystemMaxUse=300M\n' > /etc/systemd/journald.conf.d/size.conf
systemctl restart systemd-journald
journalctl --vacuum-size=300M
df -h /
```

Для swap нужно ≥ 9 ГБ свободного (4 ГБ swap + 4 ГБ под образы следующего
релиза). Если после шага 2 меньше — сделайте 2 ГБ (`fallocate -l 2G`) или
сначала освободите место (`PROD_DISK_AND_REDIS.md`: старые бэкапы,
`PROD_DB_MAINTENANCE.md`: `VACUUM FULL` ≈ 1,3 ГБ).

```bash
# 3. Swap 4 ГБ (подробности и как убрать — PROD_MEMORY.md, раздел Swap)
fallocate -l 4G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
echo 'vm.swappiness=10' > /etc/sysctl.d/99-swappiness.conf
sysctl -p /etc/sysctl.d/99-swappiness.conf
swapon --show
free -h

# 4. Аккуратно остановить данные перед перезапуском Docker:
#    контрольная точка PostgreSQL (быстрое и чистое завершение) и снимок очередей Redis
docker exec mudaroba-postgres-1 sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c CHECKPOINT'
docker exec mudaroba-redis-1 redis-cli SAVE

# 5. Обновления. confold — оставить наши конфиги (Docker, sshd и т. п.),
#    если пакет предложит свою версию
apt-get update
apt list --upgradable
DEBIAN_FRONTEND=noninteractive apt-get -y \
  -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold upgrade
apt list --upgradable   # должно быть пусто; «kept back» поставить: apt-get install <пакет>
docker version --format '{{.Server.Version}}'   # 29.9.x

# 6. Перезагрузка (проверяет, что swap и всё остальное поднимаются сами)
reboot
```

## После перезагрузки (можно уже под `deploy`)

```bash
uptime
swapon --show                               # /swapfile 4G
free -h                                     # Swap: 4.0Gi
df -h /
docker ps --format '{{.Names}} {{.Status}}' # 11 контейнеров mudaroba-*, все Up
curl -s https://mudaroba.com/api/health/    # "status":"ok", "cache":true
docker exec mudaroba-redis-1 redis-cli LLEN celery
```

Смоук из `DEVELOPMENT_RULES.md` §7: главная, категория, карточка, поиск,
корзина, `/sitemap.xml`. Через 30–60 минут — снимок памяти
(`docker stats --no-stream`, `free -m`) и сравнение с `PROD_MEMORY.md`.

## Если что-то пошло не так

- Контейнеры не поднялись: `systemctl status docker`, `journalctl -u docker -n 100`;
  затем из `~/turk-export/PharmaTurk` под `deploy`:
  `docker compose -p mudaroba -f docker-compose.yml -f docker-compose.prod.yml up -d --no-build`
  (только `-p mudaroba`).
- Сервер не загрузился или нет сети: Hetzner Console (`>_`); в крайнем случае —
  **Snapshots → Rebuild** из снимка, сделанного накануне.
- Swap мешает (диск занят): `swapoff /swapfile`, удалить строку из `/etc/fstab`
  и файл.

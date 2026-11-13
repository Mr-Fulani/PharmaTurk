# Origin за Cloudflare: TLS Full (strict) и закрытие прямого доступа

Сервер: Hetzner cx33, `204.168.175.164` и `2a01:4f9:c014:6cb3::1`, nginx в
контейнере `mudaroba-nginx-1`, репозиторий на сервере
`~/turk-export/PharmaTurk`.

## Состояние на 2026-11-13

- В панели Cloudflare режим SSL/TLS зоны — **Flexible**: Cloudflare ходит к серверу по HTTP
  на порт 80, участок Cloudflare → сервер не шифруется. Открытый пункт — TD-043 в
  [TECH_DEBT.md](TECH_DEBT.md).
- Сервер готов к **Full (strict)** (13.11.2026): nginx отдаёт на 443 сертификат Let's Encrypt
  для `mudaroba.com` и `www.mudaroba.com`, продление — cron пользователя `deploy`. Осталось
  переключение в панели Cloudflare (шаг 5, делает владелец).
- «Always Use HTTPS» включён владельцем 10.11.2026: посетитель по `http://` получает 301 на
  https прямо от Cloudflare.

## Что было на 2026-10-19

- Cloudflare ходит к серверу по HTTP на порт 80 (режим **Flexible**): участок
  Cloudflare → Hetzner не шифруется.
- IPv4: прямой запрос мимо Cloudflare (`curl -H 'Host: mudaroba.com'
  http://204.168.175.164/`) nginx закрывает без ответа (444): пропускаются только
  адреса Cloudflare из `nginx/cloudflare-realip.inc` (диапазоны сверены с
  `cloudflare.com/ips-v4|v6` 2026-10-19, совпадают).
- **IPv6 — дыра.** Docker публиковал порт и на `[::]:80` через `docker-proxy`;
  такой запрос приходит в nginx с адреса шлюза Docker `172.20.0.1`, а частные
  сети в `cloudflare-realip.inc` разрешены (для локальных smoke-проверок).
  Итог: любой клиент с IPv6 обходит Cloudflare (WAF, кэш, лимиты) и может
  подставить `X-Forwarded-Proto`. Проверено с сервера: ответ 308 вместо 444.
  Cloudflare к серверу по IPv6 не ходит (в логах nginx ни одного такого запроса).

## Что сделано в коде

- `docker-compose.prod.yml`: nginx публикуется только на IPv4
  (`0.0.0.0:80`, `0.0.0.0:443`) — IPv6-обход закрыт. Тест
  `scripts/release/test_compose_origin.py`.
- Порт 443 и каталог `nginx/tls/` (монтируется в `/etc/nginx/tls`, read-only,
  содержимое не в git). Каждый `server` в `nginx/default.conf` подключает
  `/etc/nginx/tls/*.inc`: пока там пусто, конфигурация как раньше (CI, smoke,
  локально). TLS включается файлом `nginx/tls/origin-tls.inc` (копия
  `nginx/origin-tls.inc.example`) рядом с сертификатом. CI проверяет `nginx -t`
  в обоих вариантах.
- На 443 действует та же проверка «только Cloudflare», HSTS отдаётся, `www` →
  308 на `https://mudaroba.com`, неизвестный Host — 444.

Изменены описания nginx в Compose — релиз только полный (`deploy.sh`), после
него смоук `/api` через сайт.

## Включение Full (strict): пошагово

Порядок важен: сначала origin начинает отвечать по 443, потом Cloudflare
переключается. До шага 5 сайт работает как раньше.

Сертификат — публичный **Let's Encrypt** (выбор владельца 13.11.2026): выпускается
на сервере без секретов из панели Cloudflare, Full (strict) его принимает.
Проверка домена — HTTP-01: Let's Encrypt запрашивает
`http://mudaroba.com/.well-known/acme-challenge/<токен>` через Cloudflare (в любом
режиме SSL), nginx отдаёт файл из `nginx/tls/acme/`. Редиректы на https и с `www`
на основной домен Let's Encrypt проходит сам.

Всё на сервере — пользователь `deploy`, без root; certbot запускается образом
`certbot/certbot` (версия в `scripts/ops/origin-cert.sh`). Файлы — в `nginx/tls/`
(в `.gitignore`, `git status` остаётся чистым).

### 1. Вставка для проверки домена

```bash
cd ~/turk-export/PharmaTurk
cp nginx/acme-challenge.inc.example nginx/tls/acme-challenge.inc
mkdir -p nginx/tls/acme/.well-known/acme-challenge
docker exec mudaroba-nginx-1 nginx -t && docker exec mudaroba-nginx-1 nginx -s reload
# проверка через Cloudflare
echo ok > nginx/tls/acme/.well-known/acme-challenge/probe
curl -sL http://mudaroba.com/.well-known/acme-challenge/probe   # ok
rm nginx/tls/acme/.well-known/acme-challenge/probe
```

### 2. Выпуск сертификата

```bash
scripts/ops/origin-cert.sh issue
ls -l nginx/tls/letsencrypt/live/mudaroba.com/
```

Сертификат действует 90 дней. Лимиты Let's Encrypt — 5 одинаковых выпусков в
неделю: при ошибке сначала разобраться, не повторять в цикле.

### 3. Включение TLS в nginx

nginx читает `origin.pem`/`origin.key` — это относительные ссылки на файлы certbot
(они разрешаются и внутри контейнера):

```bash
cd nginx/tls
ln -sfn letsencrypt/live/mudaroba.com/fullchain.pem origin.pem
ln -sfn letsencrypt/live/mudaroba.com/privkey.pem origin.key
cp ../origin-tls.inc.example origin-tls.inc
cd ../..
docker exec mudaroba-nginx-1 nginx -t && docker exec mudaroba-nginx-1 nginx -s reload
```

Если `nginx -t` ругается — reload не делать, сайт работает на старой
конфигурации; удалить `nginx/tls/origin-tls.inc` и разобраться.

### 4. Проверка 443 и продление

```bash
# с сервера сам себе (доверенный адрес); без -k — сертификат должен быть валиден
curl -s -o /dev/null -w '%{http_code}\n' --resolve mudaroba.com:443:127.0.0.1 https://mudaroba.com/api/health/
echo | openssl s_client -connect 127.0.0.1:443 -servername mudaroba.com 2>/dev/null | openssl x509 -noout -issuer -enddate
# порт 80 (режим Flexible) работает как раньше
curl -sI https://mudaroba.com/ | head -1
```

Ожидается `200`, issuer Let's Encrypt. С внешнего адреса 443 отвечает
сертификатом, но запрос закрывается без ответа (444) — пускаются только адреса
Cloudflare.

Продление — cron пользователя `deploy` (`crontab -l`), дважды в день в 09:17 и
15:17 UTC (вне ночного окна 01:00–06:30 МСК):

```
17 9,15 * * * $HOME/turk-export/PharmaTurk/scripts/ops/origin-cert.sh renew >> $HOME/origin-cert-renew.log 2>&1
```

certbot продлевает сертификат за 30 дней до срока; nginx перезагружается
(`nginx -t` и `reload`, без перезапуска контейнера) только после продления.
Проверить срок: шаг 4, `-enddate`. Если продление не прошло, в логе
`~/origin-cert-renew.log` будет ошибка; до конца срока остаётся месяц попыток.

**Другой вариант — Cloudflare Origin Certificate** (15 лет, без продления, но
владелец выпускает его в SSL/TLS → Origin Server и сам кладёт
`nginx/tls/origin.pem` и `origin.key` с правами 600, вместо ссылок из шага 3).
Браузеры его не принимают, Cloudflare — да.

### 5. Переключение в Cloudflare (делает владелец)

1. Сначала **DNS → Records**: посмотрите, нет ли других проксируемых (оранжевое
   облако) записей, которые ведут на серверы без HTTPS (например, старый stage).
   Режим SSL меняется на всю зону. Если такие есть — вместо шага 2 создайте
   **Rules → Configuration Rules → Create rule**: «Hostname is in
   `mudaroba.com`, `www.mudaroba.com`» → **SSL** → **Full (strict)**.
2. **SSL/TLS → Overview → Configure** → **Full (strict)** → Save.
3. **SSL/TLS → Edge Certificates**: «Always Use HTTPS» — включено (браузер по
   HTTP получит редирект прямо на Cloudflare).

### 6. Проверка после переключения

```bash
curl -sI https://mudaroba.com/ | head -1                  # 200
curl -s https://mudaroba.com/api/health/                   # "cache":true
# Cloudflare теперь держит соединения на 443:
docker exec mudaroba-nginx-1 sh -c "netstat -tn | grep -c ':443 '"
```

Плюс смоук из `DEVELOPMENT_RULES.md` (главная, категория, карточка, поиск,
корзина, `/sitemap.xml`). Ошибки 525/526 на сайте = Cloudflare не может
установить TLS с origin: вернуть **Flexible** (действует за секунды) и
проверить шаг 4 (в том числе срок сертификата).

Порт 80 оставить: в режиме Full Cloudflare ходит на 80 для HTTP-запросов
посетителей, если «Always Use HTTPS» выключен.

Откат: Cloudflare → **Flexible** (действует за секунды, сервер менять не нужно:
порт 80 работает и при включённом 443). Полностью убрать TLS с сервера:
`rm nginx/tls/origin-tls.inc && docker exec mudaroba-nginx-1 nginx -s reload`.

### 7. Необязательно: Authenticated Origin Pulls

Сервер будет принимать HTTPS только от Cloudflare (по клиентскому сертификату),
даже если кто-то знает IP. Порядок:

1. Cloudflare: **SSL/TLS → Origin Server → Authenticated Origin Pulls** → On.
2. На сервере сохранить CA Cloudflare в `nginx/tls/cloudflare-origin-pull-ca.pem`
   (файл «Cloudflare origin pull CA» из документации Cloudflare,
   developers.cloudflare.com → SSL → Authenticated Origin Pulls → Zone-level).
3. В `nginx/tls/origin-tls.inc` раскомментировать `ssl_client_certificate` и
   `ssl_verify_client on`, затем `nginx -t` и reload.

Сначала Cloudflare, потом nginx: иначе nginx начнёт требовать сертификат,
который Cloudflare ещё не присылает (ошибка 400 у всех посетителей).

## Закрыть 80/443 для всех, кроме Cloudflare

Проверка в nginx уже есть (444 для чужих адресов). Второй уровень лучше
поставить до сервера — **Hetzner Cloud Firewall**: он отсекает чужие пакеты до
сервера, работает и для IPv4, и для IPv6, root не нужен, Docker его не обходит.

**Почему не ufw.** Docker публикует порты собственными правилами iptables
(цепочки `DOCKER`), они срабатывают раньше правил ufw. `ufw deny 80`
не закроет порт контейнера nginx. Правильная настройка на хосте — правила в
цепочке `DOCKER-USER` с ipset и их восстановление при загрузке раньше Docker;
это хрупко и требует root, при облачном файрволе не нужно.

### Hetzner Cloud Firewall (делает владелец)

1. console.hetzner.com → проект → **Firewalls** → **Create Firewall**, имя
   `mudaroba-origin`.
2. **Inbound rules** (всё, чего нет в списке, будет закрыто):

   | Протокол | Порт | Источник |
   |---|---|---|
   | TCP | 22 | Any IPv4, Any IPv6 (или только ваши адреса) |
   | TCP | 80 | диапазоны Cloudflare (ниже) |
   | TCP | 443 | диапазоны Cloudflare (ниже) |
   | ICMP | — | Any IPv4, Any IPv6 |

   Диапазоны Cloudflare (те же, что в `nginx/cloudflare-realip.inc`; актуальные —
   https://www.cloudflare.com/ips-v4 и /ips-v6):

   ```
   173.245.48.0/20 103.21.244.0/22 103.22.200.0/22 103.31.4.0/22
   141.101.64.0/18 108.162.192.0/18 190.93.240.0/20 188.114.96.0/20
   197.234.240.0/22 198.41.128.0/17 162.158.0.0/15 104.16.0.0/13
   104.24.0.0/14 172.64.0.0/13 131.0.72.0/22
   2400:cb00::/32 2606:4700::/32 2803:f800::/32 2405:b500::/32
   2405:8100::/32 2a06:98c0::/29 2c0f:f248::/32
   ```

3. **Outbound rules** — не добавлять (без правил исходящий трафик разрешён:
   парсеры, R2, Telegram, apt).
4. **Apply to** → сервер → **Create Firewall**.

Если SSH всё-таки закрылся, вход остаётся через **Console** (`>_`) в панели
Hetzner, там же можно снять файрвол.

Проверка с любого компьютера не из Cloudflare:

```bash
curl -m 5 -H 'Host: mudaroba.com' http://204.168.175.164/   # таймаут (раньше: пустой ответ 444)
curl -sI https://mudaroba.com/ | head -1                     # 200, сайт работает
```

При изменении диапазонов Cloudflare (они присылают уведомление) обновить и
файрвол, и `nginx/cloudflare-realip.inc`.

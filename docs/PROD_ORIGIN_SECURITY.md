# Origin за Cloudflare: TLS Full (strict) и закрытие прямого доступа

Сервер: Hetzner cx33, `204.168.175.164` и `2a01:4f9:c014:6cb3::1`, nginx в
контейнере `mudaroba-nginx-1`, репозиторий на сервере
`~/turk-export/PharmaTurk`.

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

### 1. Сертификат в Cloudflare (делает владелец)

1. dash.cloudflare.com → домен `mudaroba.com` → **SSL/TLS** → **Origin Server**
   → **Create Certificate**.
2. «Generate private key and CSR with Cloudflare», тип ключа **RSA (2048)**.
3. Hostnames: `mudaroba.com`, `*.mudaroba.com` (по умолчанию). Срок: 15 лет.
4. **Create**. Формат **PEM**. Скопируйте оба блока: **Origin Certificate** и
   **Private Key**. Ключ показывается один раз — если закрыли окно, создайте
   сертификат заново (старый можно отозвать там же).

Этот сертификат доверен только Cloudflare, браузеры его не примут — для
связи Cloudflare → сервер этого и нужно.

### 2. Файлы на сервере (`deploy`, без root)

```bash
cd ~/turk-export/PharmaTurk
nano nginx/tls/origin.pem   # вставить Origin Certificate целиком, с BEGIN/END
nano nginx/tls/origin.key   # вставить Private Key
chmod 600 nginx/tls/origin.key
cp nginx/origin-tls.inc.example nginx/tls/origin-tls.inc
openssl x509 -in nginx/tls/origin.pem -noout -subject -enddate
```

`git status` должен остаться чистым: содержимое `nginx/tls/` в `.gitignore`.

### 3. Релиз с PR #103 (в main попал вместе с #102; если ещё не задеплоен)

Полный `deploy.sh` пересоздаёт nginx с портом 443 и каталогом `nginx/tls`.
Затем смоук. Если файлы из шага 2 уже
лежат, nginx сразу поднимется с TLS.

### 4. Проверка и включение TLS в nginx

```bash
docker exec mudaroba-nginx-1 nginx -t && docker exec mudaroba-nginx-1 nginx -s reload
# сертификат отдаётся (с сервера сам себе — доверенный адрес)
curl -sk -o /dev/null -w '%{http_code}\n' --resolve mudaroba.com:443:127.0.0.1 https://mudaroba.com/api/health/
echo | openssl s_client -connect 127.0.0.1:443 -servername mudaroba.com 2>/dev/null | openssl x509 -noout -issuer
```

Ожидается `200` и issuer с `CloudFlare Origin`. Если `nginx -t` ругается —
reload не делать, сайт продолжает работать на старой конфигурации; удалить
`nginx/tls/origin-tls.inc` и разобраться.

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
проверить шаг 4.

Порт 80 оставить: в режиме Full Cloudflare ходит на 80 для HTTP-запросов
посетителей, если «Always Use HTTPS» выключен.

Откат: Cloudflare → **Flexible**; на сервере
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

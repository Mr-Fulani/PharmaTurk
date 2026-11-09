# Картинка-превью сайта (og:image по умолчанию)

`frontend/public/og-default.jpg` (ru) и `frontend/public/og-default-en.jpg` (en), 1200×630, JPEG ~120 КБ.
Сделаны кодом 09.11.2026 вместо прежней английской картинки «Global Export» с выдуманными
банками «MUDAROBA PHARMA». На картинке — только правдивые факты сайта: логотип, «Лекарства,
БАДы и товары из Турции», «с доставкой в Россию, СНГ и по всему миру», 25 000+ позиций,
800+ брендов, 3–14 дней доставки (короткая форма сроков, решение владельца 09.11.2026), «заявка без регистрации — менеджер проверит наличие и цену».
Шрифт — фирменный InkVerse, цвета — сайта (фон `#fdf3e7`, акцент `#365bd4`, логотип).

Числа взяты с запасом вниз (09.11.2026: 27 513 позиций, 883 бренда), чтобы не устаревали.
Если позиций станет меньше 25 000 или брендов меньше 800 — поправить исходник и пересобрать.

Где используется: `lib/ogImage.js` (`defaultOgImagePath`, `defaultOgImageAlt`) — главная
(`pages/index.tsx`, ещё и `image` в разметке `Organization`) и все страницы через `SEO.tsx`
без своей картинки; остальные страницы ссылаются на `/og-default.jpg` напрямую.

## Пересборка

```bash
cd docs/images/og-default
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
for n in ru en; do
  "$CHROME" --headless=new --hide-scrollbars --force-device-scale-factor=1 \
    --allow-file-access-from-files --window-size=1200,630 \
    --screenshot=/tmp/og-$n.png "file://$PWD/og-default-$n.html"
  sips -s format jpeg -s formatOptions 85 /tmp/og-$n.png --out /tmp/og-$n.jpg
done
cp /tmp/og-ru.jpg ../../../frontend/public/og-default.jpg
cp /tmp/og-en.jpg ../../../frontend/public/og-default-en.jpg
```

Имя файла то же: соцсети и ИИ-поиск перечитывают картинку при следующем обходе страницы
(в Telegram превью можно обновить сразу через бота @WebpageBot).

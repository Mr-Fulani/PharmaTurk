# AI: готовые команды для теста

Копируй и запускай по порядку. Подставь свой пароль и ID товара где указано.

---

**Через админку (без токена)**

- Зайди в http://localhost:8000/admin/ → любой раздел **Товары** (Лекарства, Добавки и т.д.).
- Отметь галочками нужные товары.
- В списке действий выбери **«Запустить AI обработку»** → Применить.
- Результаты смотри в **AI → Логи AI обработки**.

Для вызова API из браузера после входа в админку работает session auth, но для
любого изменяющего `POST/PATCH/DELETE` запроса нужно также передать действующий
Django CSRF token (`csrftoken` cookie и заголовок `X-CSRFToken`). Admin action
выше делает это автоматически своей формой.

---

**1. JWT (нужен только для curl/скриптов; подставь пароль)**

```bash
curl -s -X POST http://localhost:8000/api/auth/jwt/create/ \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "****"}'
```

Из ответа скопируй **только** значение `access` (одна длинная строка, без кавычек). Не путай с `refresh`.

---

**2. Статистика AI**

Подставь **только access** в `Bearer ПОСЛЕ_ПРОБЕЛА`:

```bash
curl -s -H "Authorization: Bearer <YOUR_ACCESS_TOKEN>" http://localhost:8000/api/ai/stats/
```

Пример (подставь свой access):  
`curl -s -H "Authorization: Bearer <YOUR_ACCESS_TOKEN>" http://localhost:8000/api/ai/stats/`

---

**3. Запуск обработки товара по ID (подставь токен и ID товара)**

```bash
curl -s -X POST http://localhost:8000/api/ai/process/1/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_ACCESS_TOKEN>" \
  -d '{"auto_apply": false}'
```

Замени `1` на реальный ID товара из каталога.

---

**4. RAG (один раз)**

```bash
docker compose exec backend poetry run python manage.py setup_ai_rag
```

---

**5. Прогон по 2 товарам**

```bash
docker compose exec backend poetry run python manage.py benchmark_ai 2
```

---

**6. Админка — логи AI**

Открой в браузере: http://localhost:8000/admin/ → AI → Логи AI обработки

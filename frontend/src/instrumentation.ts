// Выполняется один раз при старте сервера Next (не в браузере).
//
// SSR (getServerSideProps) ходит в API напрямую на backend:8000 (gunicorn gthread).
// Gunicorn закрывает простаивающее keep-alive соединение через 2 с и перезапускает
// воркеры по --max-requests, а агент Node 22 держит свободный сокет до 5 с и отдаёт
// его следующему запросу. Запрос в уже закрытый сокет падал с «socket hang up» /
// ECONNRESET, и страница отвечала 500 (в том числе Googlebot).
//
// Без keep-alive каждый запрос открывает новое соединение — внутри Docker это почти
// бесплатно. Меняется общий агент модуля http: axios в страницах собран отдельным
// экземпляром, и настроить его отсюда нельзя. Агент читает keepAlive на каждом запросе.
export async function register() {
  if (process.env.NEXT_RUNTIME !== 'nodejs') return
  const http = await import('node:http')
  Object.assign(http.globalAgent, { keepAlive: false })
}

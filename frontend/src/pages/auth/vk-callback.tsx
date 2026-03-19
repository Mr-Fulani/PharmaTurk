/**
 * Страница-заглушка для VK OAuth callback.
 * VK после авторизации редиректит сюда с хешем: #access_token=...&user_id=...
 * Страница извлекает данные из хеша и отправляет их opener через postMessage.
 */
export default function VKCallbackPage() {
    if (typeof window !== 'undefined') {
        const hash = window.location.hash.substring(1)
        const params = new URLSearchParams(hash)
        const access_token = params.get('access_token')
        const user_id = params.get('user_id')

        if (access_token && window.opener) {
            window.opener.postMessage(
                { type: 'vk_auth', access_token, user_id },
                window.location.origin
            )
        }
        // Закрываем popup в любом случае
        window.close()
    }

    return (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>
            <p>Авторизация через ВКонтакте...</p>
        </div>
    )
}

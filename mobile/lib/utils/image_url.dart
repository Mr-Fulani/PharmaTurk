import '../constants/env.dart';

/// Преобразует URL изображения в полный.
/// Если API вернул относительный путь (/media/xxx), добавляет базовый URL.
/// Исправляет ошибочный паттерн /media//api/ (двойной слэш) — proxy-media не должен быть под /media/.
String resolveImageUrl(String? url) {
  if (url == null || url.isEmpty) return '';
  // Исправление ошибочного URL: /media//api/ -> /api/ (proxy-media не должен быть под /media/)
  url = url.replaceAll('/media//api/', '/api/');
  if (url.startsWith('http://') || url.startsWith('https://')) return url;
  final base = Env.apiBaseUrl.replaceAll(RegExp(r'/$'), '');
  return url.startsWith('/') ? '$base$url' : '$base/$url';
}

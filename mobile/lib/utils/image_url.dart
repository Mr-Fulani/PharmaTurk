import '../constants/env.dart';

/// Проверяет, что URL изображения валиден (не null и не пустая строка).
bool isValidImageUrl(String? url) => url != null && url.trim().isNotEmpty;

/// Проверяет, что URL указывает на видео (mp4, webm, mov и т.д.).
/// CachedNetworkImage не поддерживает видео — для таких URL показывать fallback.
bool isVideoUrl(String? url) {
  if (url == null || url.isEmpty) return false;
  final path = url.split('?').first.toLowerCase();
  return path.endsWith('.mp4') || path.endsWith('.webm') || path.endsWith('.mov') ||
      path.endsWith('.m4v') || path.endsWith('.mkv');
}

/// Преобразует URL изображения в полный.
/// Если API вернул относительный путь (/media/xxx), добавляет базовый URL.
/// Исправляет ошибочный паттерн /media//api/ (двойной слэш) — proxy-media не должен быть под /media/.
/// Возвращает null, если результат невалиден (пустой ввод, нет хоста) — не передавать в CachedNetworkImage.
String? resolveImageUrlOrNull(String? url) {
  if (url == null || url.trim().isEmpty) return null;
  url = url.trim();
  // Исправление ошибочного URL: /media//api/ -> /api/
  url = url.replaceAll('/media//api/', '/api/');
  if (url.startsWith('http://') || url.startsWith('https://')) return url;
  final base = Env.apiBaseUrl.replaceAll(RegExp(r'/$'), '').trim();
  if (base.isEmpty) return null; // Без базового URL относительный путь невалиден
  final result = url.startsWith('/') ? '$base$url' : '$base/$url';
  if (!result.startsWith('http://') && !result.startsWith('https://')) return null;
  return result;
}

/// Преобразует URL в полный. Возвращает '' для невалидного ввода (для обратной совместимости).
/// Предпочтительно использовать resolveImageUrlOrNull и проверку на null перед CachedNetworkImage.
String resolveImageUrl(String? url) => resolveImageUrlOrNull(url) ?? '';

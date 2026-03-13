import '../constants/env.dart';

/// Преобразует URL изображения в полный.
/// Если API вернул относительный путь (/media/xxx), добавляет базовый URL.
String resolveImageUrl(String? url) {
  if (url == null || url.isEmpty) return '';
  if (url.startsWith('http://') || url.startsWith('https://')) return url;
  final base = Env.apiBaseUrl.replaceAll(RegExp(r'/$'), '');
  return url.startsWith('/') ? '$base$url' : '$base/$url';
}

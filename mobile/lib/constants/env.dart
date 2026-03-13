import 'package:flutter/foundation.dart' show kIsWeb;

/// Конфигурация окружения приложения.
/// API_BASE_URL задаётся через --dart-define при сборке:
///   flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
///   flutter build apk --dart-define=API_BASE_URL=https://api.pharmaturk.com
class Env {
  Env._();

  static String get apiBaseUrl {
    const fromEnv = String.fromEnvironment(
      'API_BASE_URL',
      defaultValue: '',
    );
    if (fromEnv.isNotEmpty) return fromEnv;
    // Fallback для локальной разработки
    // Web и iOS: localhost
    if (kIsWeb) return 'http://localhost:8000';
    // Android: передайте --dart-define=API_BASE_URL=http://10.0.2.2:8000
    return 'http://localhost:8000';
  }

}

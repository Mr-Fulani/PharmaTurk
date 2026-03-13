import 'package:flutter/foundation.dart';

/// Глобальное хранилище последней ошибки для отладки.
/// Позволяет показывать и копировать ошибки в UI.
class ErrorLogger extends ChangeNotifier {
  ErrorLogger._();

  static final ErrorLogger _instance = ErrorLogger._();
  static ErrorLogger get instance => _instance;

  String? _lastError;
  String? _lastStack;
  DateTime? _lastTime;

  String? get lastError => _lastError;
  String? get lastStack => _lastStack;
  DateTime? get lastTime => _lastTime;

  bool get hasError => _lastError != null;

  void capture(Object error, [StackTrace? stack]) {
    _lastError = error.toString();
    _lastStack = stack?.toString();
    _lastTime = DateTime.now();

    if (kDebugMode) {
      debugPrint('');
      debugPrint('╔═══════════════════════════════════════════════════════════');
      debugPrint('║ ОШИБКА ${_lastTime?.toIso8601String() ?? ''}');
      debugPrint('╠═══════════════════════════════════════════════════════════');
      debugPrint('║ $_lastError');
      debugPrint('╠═══════════════════════════════════════════════════════════');
      if (_lastStack != null) {
        debugPrint('║ STACK TRACE:');
        for (final line in _lastStack!.split('\n')) {
          debugPrint('║ $line');
        }
      }
      debugPrint('╚═══════════════════════════════════════════════════════════');
      debugPrint('');
    }
    notifyListeners();
  }

  void clear() {
    _lastError = null;
    _lastStack = null;
    _lastTime = null;
    notifyListeners();
  }

  /// Полный текст для копирования (ошибка + стек)
  String get fullText {
    final buf = StringBuffer();
    buf.writeln('Ошибка: $_lastError');
    buf.writeln('Время: $_lastTime');
    if (_lastStack != null) {
      buf.writeln('\nStack trace:');
      buf.writeln(_lastStack);
    }
    return buf.toString();
  }
}

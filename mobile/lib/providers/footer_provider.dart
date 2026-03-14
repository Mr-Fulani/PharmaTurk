import 'package:flutter/foundation.dart';
import '../models/footer_settings.dart';
import '../services/footer_service.dart';

/// Провайдер настроек футера (контакты, соцсети, URL страниц).
class FooterProvider extends ChangeNotifier {
  final FooterService _service = FooterService();

  FooterSettings? _settings;
  bool _loading = false;
  bool _loaded = false;

  FooterSettings? get settings => _settings;
  bool get loading => _loading;
  bool get loaded => _loaded;

  Future<void> load() async {
    if (_loading) return;
    if (_loaded && _settings != null) return; // Уже загружено
    _loading = true;
    notifyListeners();
    try {
      final data = await _service.getFooterSettings();
      _settings = data;
      if (data != null) _loaded = true;
    } catch (_) {
      // При ошибке не помечаем _loaded — можно повторить
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  /// Принудительная перезагрузка (игнорирует кэш).
  Future<void> reload() async {
    _loaded = false;
    _settings = null;
    await load();
  }

  /// Сбрасывает кэш (например, при смене языка).
  void reset() {
    _settings = null;
    _loaded = false;
    notifyListeners();
  }
}

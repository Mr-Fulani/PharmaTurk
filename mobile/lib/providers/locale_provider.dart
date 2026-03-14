import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../services/api_client.dart';

const _localeKey = 'app_locale';

/// Провайдер локали приложения. Синхронизируется с preferredLanguage пользователя.
class LocaleProvider extends ChangeNotifier {
  Locale _locale = const Locale('ru');

  Locale get locale => _locale;

  /// Загружает сохранённую локаль при старте.
  Future<void> loadSavedLocale() async {
    final prefs = await SharedPreferences.getInstance();
    final code = prefs.getString(_localeKey);
    if (code != null && (code == 'ru' || code == 'en')) {
      _locale = Locale(code);
      ApiClient().setLanguage(code);
      notifyListeners();
    }
  }

  /// Устанавливает локаль и сохраняет в SharedPreferences.
  Future<void> setLocale(String languageCode) async {
    if (languageCode != 'ru' && languageCode != 'en') return;
    _locale = Locale(languageCode);
    ApiClient().setLanguage(languageCode);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_localeKey, languageCode);
    notifyListeners();
  }

  /// Синхронизирует с языком пользователя из профиля (при логине/загрузке).
  void syncWithUserLanguage(String? languageCode) {
    if (languageCode == null || languageCode.isEmpty) return;
    if (languageCode == 'ru' || languageCode == 'en') {
      if (_locale.languageCode != languageCode) {
        _locale = Locale(languageCode);
        ApiClient().setLanguage(languageCode);
        notifyListeners();
      }
    }
  }
}

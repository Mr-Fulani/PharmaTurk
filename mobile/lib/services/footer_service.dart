import '../models/footer_settings.dart';
import 'api_client.dart';

/// Сервис для загрузки настроек футера (контакты, соцсети, URL сайта).
class FooterService {
  final ApiClient _client = ApiClient();

  Future<FooterSettings?> getFooterSettings() async {
    try {
      final response = await _client.dio.get(
        'settings/footer-settings/',
      );
      final data = response.data;
      if (data == null) return null;
      // API может вернуть объект или массив с одним элементом
      final Map<String, dynamic>? map = data is Map<String, dynamic>
          ? data
          : (data is List && data.isNotEmpty && data.first is Map)
              ? Map<String, dynamic>.from(data.first as Map)
              : null;
      return map != null ? FooterSettings.fromJson(map) : null;
    } catch (_) {
      return null;
    }
  }
}

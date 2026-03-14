import 'api_client.dart';

/// Сервис для загрузки статических страниц (privacy, delivery, returns) из API.
class PageService {
  final ApiClient _client = ApiClient();

  /// Загружает страницу по slug. lang — ru/en.
  Future<StaticPage?> getPage(String slug, {String lang = 'ru'}) async {
    try {
      final response = await _client.dio.get<Map<String, dynamic>>(
        'pages/$slug/',
        queryParameters: {'lang': lang},
      );
      final data = response.data;
      if (data == null) return null;
      return StaticPage.fromJson(data);
    } catch (_) {
      return null;
    }
  }
}

/// Модель статической страницы из API.
class StaticPage {
  final int id;
  final String slug;
  final String title;
  final String content;

  const StaticPage({
    required this.id,
    required this.slug,
    required this.title,
    required this.content,
  });

  factory StaticPage.fromJson(Map<String, dynamic> json) {
    return StaticPage(
      id: json['id'] as int? ?? 0,
      slug: json['slug'] as String? ?? '',
      title: json['title'] as String? ?? '',
      content: json['content'] as String? ?? '',
    );
  }
}

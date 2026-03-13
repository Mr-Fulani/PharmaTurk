import 'package:dio/dio.dart';
import 'api_client.dart';
import '../models/models.dart';

class FavoriteService {
  final ApiClient _apiClient = ApiClient();

  Future<List<Favorite>> getFavorites() async {
    try {
      final response = await _apiClient.dio.get('/catalog/favorites');
      return (response.data as List)
          .map((json) => Favorite.fromJson(json))
          .toList();
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<Favorite> addToFavorite(int productId, {String? productType}) async {
    try {
      final response = await _apiClient.dio.post(
        '/catalog/favorites/add',
        data: {
          'product_id': productId,
          if (productType != null) 'product_type': productType,
        },
      );
      return Favorite.fromJson(response.data);
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<void> removeFromFavorite(int productId) async {
    try {
      await _apiClient.dio.delete(
        '/catalog/favorites/remove',
        queryParameters: {'product_id': productId},
      );
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<bool> checkIsFavorite(int productId) async {
    try {
      final response = await _apiClient.dio.get(
        '/catalog/favorites/check',
        queryParameters: {'product_id': productId},
      );
      return response.data['is_favorite'] ?? false;
    } catch (e) {
      return false;
    }
  }

  Future<int> getFavoritesCount() async {
    try {
      final response = await _apiClient.dio.get('/catalog/favorites/count');
      return response.data['count'] ?? 0;
    } catch (e) {
      return 0;
    }
  }

  String _handleError(dynamic error) {
    if (error is DioException) {
      if (error.response != null) {
        final data = error.response!.data;
        if (data is Map<String, dynamic>) {
          if (data.containsKey('detail')) {
            return data['detail'].toString();
          }
          if (data.containsKey('message')) {
            return data['message'].toString();
          }
          if (data.containsKey('error')) {
            return data['error'].toString();
          }
        }
        return 'Ошибка сервера: ${error.response!.statusCode}';
      }
      return 'Ошибка соединения: ${error.message}';
    }
    return 'Неизвестная ошибка: $error';
  }
}

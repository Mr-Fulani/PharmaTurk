import 'package:dio/dio.dart';
import 'api_client.dart';
import '../models/models.dart';

class TestimonialService {
  final ApiClient _apiClient = ApiClient();

  Future<List<Testimonial>> getTestimonials() async {
    try {
      final response = await _apiClient.dio.get('/feedback/testimonials/');
      return (response.data as List)
          .map((json) => Testimonial.fromJson(json))
          .toList();
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<Testimonial> getTestimonial(int id) async {
    try {
      final response = await _apiClient.dio.get('/feedback/testimonials/$id/');
      return Testimonial.fromJson(response.data);
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<Testimonial> createTestimonial(TestimonialCreate testimonial) async {
    try {
      final response = await _apiClient.dio.post(
        '/feedback/testimonials/',
        data: testimonial.toJson(),
      );
      return Testimonial.fromJson(response.data);
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<Testimonial> updateTestimonial(int id, Testimonial testimonial) async {
    try {
      final response = await _apiClient.dio.put(
        '/feedback/testimonials/$id/',
        data: testimonial.toJson(),
      );
      return Testimonial.fromJson(response.data);
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<void> deleteTestimonial(int id) async {
    try {
      await _apiClient.dio.delete('/feedback/testimonials/$id/');
    } catch (e) {
      throw _handleError(e);
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

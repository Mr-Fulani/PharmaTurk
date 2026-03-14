import 'package:dio/dio.dart';
import 'api_client.dart';
import '../models/models.dart';

class OrderService {
  final ApiClient _apiClient = ApiClient();

  Future<List<Order>> getOrders() async {
    try {
      final response = await _apiClient.dio.get('/orders/orders');
      final list = response.data;
      if (list is! List) return [];
      return list
          .map((json) => Order.fromJson(
                json is Map<String, dynamic>
                    ? json
                    : Map<String, dynamic>.from(json as Map),
              ))
          .toList();
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<Order> getOrder(String id) async {
    try {
      final response = await _apiClient.dio.get('/orders/orders/$id');
      final data = response.data;
      return Order.fromJson(
        data is Map<String, dynamic>
            ? data
            : Map<String, dynamic>.from(data as Map),
      );
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<Order> getOrderByNumber(String number) async {
    try {
      final response = await _apiClient.dio.get('/orders/orders/by-number/$number');
      final data = response.data;
      return Order.fromJson(
        data is Map<String, dynamic>
            ? data
            : Map<String, dynamic>.from(data as Map),
      );
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<Order> createOrderFromCart(CreateOrderRequest request) async {
    try {
      final response = await _apiClient.dio.post(
        '/orders/orders/create-from-cart',
        data: request.toJson(),
      );
      return Order.fromJson(response.data);
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<OrderReceipt> getOrderReceipt(String number) async {
    try {
      final response = await _apiClient.dio.get('/orders/orders/receipt/$number');
      return OrderReceipt.fromJson(response.data);
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<void> sendOrderReceipt(String number) async {
    try {
      await _apiClient.dio.post('/orders/orders/send-receipt/$number');
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

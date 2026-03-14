import 'package:dio/dio.dart';
import 'api_client.dart';
import '../models/models.dart';

class CartService {
  final ApiClient _apiClient = ApiClient();

  Future<Cart> getCart() async {
    try {
      final response = await _apiClient.dio.get('/orders/cart');
      final data = response.data;
      if (data is List && data.isNotEmpty) {
        return Cart.fromJson(data.first as Map<String, dynamic>);
      }
      if (data is Map<String, dynamic>) {
        return Cart.fromJson(data);
      }
      return _emptyCart();
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<Cart> addToCart(AddToCartRequest request) async {
    try {
      final response = await _apiClient.dio.post(
        '/orders/cart/add',
        data: request.toJson(),
      );
      
      // Save session key if provided
      final sessionKey = response.headers.value('x-cart-session');
      if (sessionKey != null) {
        await _apiClient.saveSessionKey(sessionKey);
      }
      
      return Cart.fromJson(response.data);
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<Cart> updateCartItem(String itemId, int quantity) async {
    try {
      final response = await _apiClient.dio.post(
        '/orders/cart/$itemId/update',
        data: {'quantity': quantity},
      );
      return Cart.fromJson(response.data);
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<void> removeCartItem(String itemId) async {
    try {
      await _apiClient.dio.delete('/orders/cart/$itemId/remove');
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<Cart> clearCart() async {
    try {
      final response = await _apiClient.dio.post('/orders/cart/clear');
      return Cart.fromJson(response.data);
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<Cart> applyPromoCode(String code) async {
    try {
      final response = await _apiClient.dio.post(
        '/orders/cart/apply-promo',
        data: {'code': code},
      );
      return Cart.fromJson(response.data);
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<Cart> removePromoCode() async {
    try {
      final response = await _apiClient.dio.post('/orders/cart/remove-promo');
      return Cart.fromJson(response.data);
    } catch (e) {
      throw _handleError(e);
    }
  }

  Cart _emptyCart() {
    return Cart(
      id: 0,
      currency: _apiClient.currency ?? 'RUB',
      items: [],
      itemsCount: 0,
      totalAmount: '0.00',
      discountAmount: '0.00',
      finalAmount: '0.00',
      createdAt: DateTime.now(),
      updatedAt: DateTime.now(),
    );
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

import 'package:flutter/foundation.dart';
import '../models/models.dart';
import '../services/services.dart';

class CartProvider extends ChangeNotifier {
  final CartService _cartService = CartService();

  Cart? _cart;
  bool _isLoading = false;
  String? _error;
  int _cartItemCount = 0;

  Cart? get cart => _cart;
  bool get isLoading => _isLoading;
  String? get error => _error;
  int get cartItemCount => _cartItemCount;
  List<CartItem> get cartItems => _cart?.items ?? [];
  String get totalAmount => _cart?.totalAmount ?? '0.00';
  String get finalAmount => _cart?.finalAmount ?? '0.00';
  String get discountAmount => _cart?.discountAmount ?? '0.00';
  Map<String, double> get shippingOptions => _cart?.shippingOptions ?? const {};
  bool get hasItems => _cart != null && _cart!.items.isNotEmpty;
  PromoCode? get appliedPromoCode => _cart?.promoCode;

  Future<void> getCart() async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      _cart = await _cartService.getCart();
      _cartItemCount = _cart?.itemsCount ?? 0;
      _isLoading = false;
      notifyListeners();
    } catch (e) {
      _error = e.toString();
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<bool> addToCart({
    int? productId,
    String? productType,
    String? productSlug,
    String? size,
    int quantity = 1,
  }) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final updatedCart = await _cartService.addToCart(AddToCartRequest(
        productId: productId,
        productType: productType,
        productSlug: productSlug,
        size: size,
        quantity: quantity,
      ));
      _cart = updatedCart;
      _cartItemCount = updatedCart.itemsCount;
      _isLoading = false;
      notifyListeners();
      return true;
    } catch (e) {
      _error = e.toString();
      _isLoading = false;
      notifyListeners();
      return false;
    }
  }

  Future<bool> updateQuantity(String itemId, int quantity) async {
    if (quantity < 1) {
      return removeItem(itemId);
    }

    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final updatedCart = await _cartService.updateCartItem(itemId, quantity);
      _cart = updatedCart;
      _cartItemCount = updatedCart.itemsCount;
      _isLoading = false;
      notifyListeners();
      return true;
    } catch (e) {
      _error = e.toString();
      _isLoading = false;
      notifyListeners();
      return false;
    }
  }

  Future<bool> removeItem(String itemId) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      await _cartService.removeCartItem(itemId);
      await getCart(); // Refresh cart
      return true;
    } catch (e) {
      _error = e.toString();
      _isLoading = false;
      notifyListeners();
      return false;
    }
  }

  Future<bool> clearCart() async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final updatedCart = await _cartService.clearCart();
      _cart = updatedCart;
      _cartItemCount = 0;
      _isLoading = false;
      notifyListeners();
      return true;
    } catch (e) {
      _error = e.toString();
      _isLoading = false;
      notifyListeners();
      return false;
    }
  }

  Future<bool> applyPromoCode(String code) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final updatedCart = await _cartService.applyPromoCode(code);
      _cart = updatedCart;
      _isLoading = false;
      notifyListeners();
      return true;
    } catch (e) {
      _error = e.toString();
      _isLoading = false;
      notifyListeners();
      return false;
    }
  }

  Future<bool> removePromoCode() async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final updatedCart = await _cartService.removePromoCode();
      _cart = updatedCart;
      _isLoading = false;
      notifyListeners();
      return true;
    } catch (e) {
      _error = e.toString();
      _isLoading = false;
      notifyListeners();
      return false;
    }
  }

  double get itemTotal {
    if (_cart == null) return 0.0;
    return double.tryParse(_cart!.totalAmount) ?? 0.0;
  }

  double get discount {
    if (_cart == null) return 0.0;
    return double.tryParse(_cart!.discountAmount) ?? 0.0;
  }

  double get finalTotal {
    if (_cart == null) return 0.0;
    return double.tryParse(_cart!.finalAmount) ?? 0.0;
  }

  void clearError() {
    _error = null;
    notifyListeners();
  }
}

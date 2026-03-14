import 'package:flutter/foundation.dart';
import '../models/models.dart';
import '../services/services.dart';

class OrderProvider extends ChangeNotifier {
  final OrderService _orderService = OrderService();

  List<Order> _orders = [];
  Order? _selectedOrder;
  OrderReceipt? _orderReceipt;
  bool _isLoading = false;
  String? _error;
  bool _isCreatingOrder = false;

  List<Order> get orders => _orders;
  Order? get selectedOrder => _selectedOrder;
  OrderReceipt? get orderReceipt => _orderReceipt;
  bool get isLoading => _isLoading;
  String? get error => _error;
  bool get isCreatingOrder => _isCreatingOrder;

  Future<void> getOrders() async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      _orders = await _orderService.getOrders();
      _isLoading = false;
      notifyListeners();
    } catch (e) {
      _error = e.toString();
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> getOrder(String id) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      _selectedOrder = await _orderService.getOrder(id);
      _isLoading = false;
      notifyListeners();
    } catch (e) {
      _error = e.toString();
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> getOrderByNumber(String number) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      _selectedOrder = await _orderService.getOrderByNumber(number);
      _isLoading = false;
      notifyListeners();
    } catch (e) {
      _error = e.toString();
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<Order?> createOrder({
    required String contactName,
    required String contactPhone,
    String? contactEmail,
    required String shippingAddressText,
    required String paymentMethod,
    String? shippingMethod,
    String? comment,
  }) async {
    _isCreatingOrder = true;
    _error = null;
    notifyListeners();

    try {
      final order = await _orderService.createOrderFromCart(CreateOrderRequest(
        contactName: contactName,
        contactPhone: contactPhone,
        contactEmail: contactEmail,
        shippingAddressText: shippingAddressText,
        paymentMethod: paymentMethod,
        shippingMethod: shippingMethod,
        comment: comment,
      ));
      _orders.insert(0, order);
      _selectedOrder = order;
      _isCreatingOrder = false;
      notifyListeners();
      return order;
    } catch (e) {
      _error = e.toString();
      _isCreatingOrder = false;
      notifyListeners();
      return null;
    }
  }

  Future<void> getOrderReceipt(String number) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      _orderReceipt = await _orderService.getOrderReceipt(number);
      _isLoading = false;
      notifyListeners();
    } catch (e) {
      _error = e.toString();
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> sendOrderReceipt(String number) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      await _orderService.sendOrderReceipt(number);
      _isLoading = false;
      notifyListeners();
    } catch (e) {
      _error = e.toString();
      _isLoading = false;
      notifyListeners();
    }
  }

  void clearSelectedOrder() {
    _selectedOrder = null;
    _orderReceipt = null;
    notifyListeners();
  }

  void clearError() {
    _error = null;
    notifyListeners();
  }
}

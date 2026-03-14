import 'package:json_annotation/json_annotation.dart';

part 'order.g.dart';

/// Безопасное преобразование num/String в String (API может вернуть число или строку).
String _stringFromJson(dynamic v) => v?.toString() ?? '0';

/// Безопасный парсинг списка items (может быть null).
List<OrderItem> _itemsFromJson(dynamic v) {
  if (v == null) return [];
  if (v is! List) return [];
  return v
      .map((e) => e is Map<String, dynamic>
          ? OrderItem.fromJson(e)
          : OrderItem.fromJson(Map<String, dynamic>.from(e as Map)))
      .toList();
}

@JsonSerializable()
class Order {
  final int id;
  final String number;
  final String status;
  @JsonKey(name: 'subtotal_amount', fromJson: _stringFromJson)
  final String subtotalAmount;
  @JsonKey(name: 'shipping_amount', fromJson: _stringFromJson)
  final String shippingAmount;
  @JsonKey(name: 'discount_amount', fromJson: _stringFromJson)
  final String discountAmount;
  @JsonKey(name: 'total_amount', fromJson: _stringFromJson)
  final String totalAmount;
  final String currency;
  @JsonKey(fromJson: _itemsFromJson)
  final List<OrderItem> items;
  @JsonKey(name: 'created_at')
  final DateTime createdAt;
  @JsonKey(name: 'updated_at')
  final DateTime? updatedAt;
  @JsonKey(name: 'contact_name')
  final String? contactName;
  @JsonKey(name: 'contact_phone')
  final String? contactPhone;
  @JsonKey(name: 'contact_email')
  final String? contactEmail;
  @JsonKey(name: 'shipping_address_text')
  final String? shippingAddressText;
  @JsonKey(name: 'payment_method')
  final String? paymentMethod;
  @JsonKey(name: 'shipping_method')
  final String? shippingMethod;
  final String? comment;

  Order({
    required this.id,
    required this.number,
    required this.status,
    required this.subtotalAmount,
    required this.shippingAmount,
    required this.discountAmount,
    required this.totalAmount,
    required this.currency,
    required this.items,
    required this.createdAt,
    this.updatedAt,
    this.contactName,
    this.contactPhone,
    this.contactEmail,
    this.shippingAddressText,
    this.paymentMethod,
    this.shippingMethod,
    this.comment,
  });

  factory Order.fromJson(Map<String, dynamic> json) => _$OrderFromJson(json);
  Map<String, dynamic> toJson() => _$OrderToJson(this);

  String get statusDisplay {
    switch (status) {
      case 'new':
        return 'Новый';
      case 'pending_payment':
        return 'Ожидает оплаты';
      case 'processing':
        return 'В обработке';
      case 'shipped':
        return 'Отправлен';
      case 'delivered':
        return 'Доставлен';
      case 'cancelled':
        return 'Отменен';
      case 'refunded':
        return 'Возвращен';
      default:
        return status;
    }
  }
}

@JsonSerializable()
class OrderItem {
  final int id;
  final int product;
  @JsonKey(name: 'product_name')
  final String productName;
  @JsonKey(fromJson: _stringFromJson)
  final String price;
  final int quantity;
  @JsonKey(fromJson: _stringFromJson)
  final String total;

  OrderItem({
    required this.id,
    required this.product,
    required this.productName,
    required this.price,
    required this.quantity,
    required this.total,
  });

  factory OrderItem.fromJson(Map<String, dynamic> json) => _$OrderItemFromJson(json);
  Map<String, dynamic> toJson() => _$OrderItemToJson(this);
}

@JsonSerializable()
class CreateOrderRequest {
  @JsonKey(name: 'contact_name')
  final String contactName;
  @JsonKey(name: 'contact_phone')
  final String contactPhone;
  @JsonKey(name: 'contact_email')
  final String? contactEmail;
  @JsonKey(name: 'shipping_address_text')
  final String shippingAddressText;
  @JsonKey(name: 'payment_method')
  final String paymentMethod;
  @JsonKey(name: 'shipping_method')
  final String? shippingMethod;
  final String? comment;

  CreateOrderRequest({
    required this.contactName,
    required this.contactPhone,
    this.contactEmail,
    required this.shippingAddressText,
    required this.paymentMethod,
    this.shippingMethod,
    this.comment,
  });

  factory CreateOrderRequest.fromJson(Map<String, dynamic> json) => _$CreateOrderRequestFromJson(json);
  Map<String, dynamic> toJson() => _$CreateOrderRequestToJson(this);
}

@JsonSerializable()
class OrderReceipt {
  final int id;
  final String number;
  final String status;
  @JsonKey(name: 'total_amount', fromJson: _stringFromJson)
  final String totalAmount;
  final String currency;
  @JsonKey(name: 'created_at')
  final DateTime createdAt;
  @JsonKey(name: 'receipt_url')
  final String receiptUrl;

  OrderReceipt({
    required this.id,
    required this.number,
    required this.status,
    required this.totalAmount,
    required this.currency,
    required this.createdAt,
    required this.receiptUrl,
  });

  factory OrderReceipt.fromJson(Map<String, dynamic> json) => _$OrderReceiptFromJson(json);
  Map<String, dynamic> toJson() => _$OrderReceiptToJson(this);
}

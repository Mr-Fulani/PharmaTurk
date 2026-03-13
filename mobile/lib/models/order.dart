import 'package:json_annotation/json_annotation.dart';

part 'order.g.dart';

@JsonSerializable()
class Order {
  final int id;
  final String number;
  final String status;
  final String subtotalAmount;
  final String shippingAmount;
  final String discountAmount;
  final String totalAmount;
  final String currency;
  final List<OrderItem> items;
  final DateTime createdAt;
  final DateTime? updatedAt;
  final String? contactName;
  final String? contactPhone;
  final String? contactEmail;
  final String? shippingAddressText;
  final String? paymentMethod;
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
    this.comment,
  });

  factory Order.fromJson(Map<String, dynamic> json) => _$OrderFromJson(json);
  Map<String, dynamic> toJson() => _$OrderToJson(this);

  String get statusDisplay {
    switch (status) {
      case 'new':
        return 'Новый';
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
  final String productName;
  final String price;
  final int quantity;
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
  final String contactName;
  final String contactPhone;
  final String? contactEmail;
  final String shippingAddressText;
  final String paymentMethod;
  final String? comment;

  CreateOrderRequest({
    required this.contactName,
    required this.contactPhone,
    this.contactEmail,
    required this.shippingAddressText,
    required this.paymentMethod,
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
  final String totalAmount;
  final String currency;
  final DateTime createdAt;
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

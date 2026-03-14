import 'package:json_annotation/json_annotation.dart';

part 'cart.g.dart';

String _cartSafeStr(dynamic v) => v?.toString() ?? '';
/// Для полей, которые API может вернуть как Map/List/num — всегда строка
String _cartSafeDynamicStr(dynamic v) {
  if (v == null) return '';
  if (v is Map || v is List) return ''; // product_translations, prices_in_currencies
  return v.toString();
}
/// Парсинг shipping_options: { air, sea, ground } — стоимость доставки в USD
Map<String, double> _shippingOptionsFromJson(dynamic v) {
  if (v == null || v is! Map) return {};
  final m = Map<String, dynamic>.from(v);
  return {
    'air': (m['air'] as num?)?.toDouble() ?? 0,
    'sea': (m['sea'] as num?)?.toDouble() ?? 0,
    'ground': (m['ground'] as num?)?.toDouble() ?? 0,
  };
}
int _cartSafeInt(dynamic v) => (v as num?)?.toInt() ?? 0;
DateTime _cartSafeDateTime(dynamic v) {
  if (v == null) return DateTime.now();
  try {
    return DateTime.parse(v.toString());
  } catch (_) {
    return DateTime.now();
  }
}
List<CartItem> _cartSafeItems(dynamic v) {
  if (v == null || v is! List) return [];
  return v.map((e) => CartItem.fromJson(Map<String, dynamic>.from(e as Map))).toList();
}

@JsonSerializable()
class Cart {
  @JsonKey(fromJson: _cartSafeInt)
  final int id;
  final int? user;
  @JsonKey(name: 'session_key')
  final String? sessionKey;
  @JsonKey(fromJson: _cartSafeStr)
  final String currency;
  @JsonKey(name: 'items', fromJson: _cartSafeItems)
  final List<CartItem> items;
  @JsonKey(name: 'items_count', fromJson: _cartSafeInt)
  final int itemsCount;
  @JsonKey(name: 'total_amount', fromJson: _cartSafeStr)
  final String totalAmount;
  @JsonKey(name: 'discount_amount', fromJson: _cartSafeStr)
  final String discountAmount;
  @JsonKey(name: 'final_amount', fromJson: _cartSafeStr)
  final String finalAmount;
  @JsonKey(name: 'shipping_options', fromJson: _shippingOptionsFromJson)
  final Map<String, double> shippingOptions;
  @JsonKey(name: 'promo_code')
  final PromoCode? promoCode;
  @JsonKey(name: 'created_at', fromJson: _cartSafeDateTime)
  final DateTime createdAt;
  @JsonKey(name: 'updated_at', fromJson: _cartSafeDateTime)
  final DateTime updatedAt;

  Cart({
    required this.id,
    this.user,
    this.sessionKey,
    required this.currency,
    required this.items,
    required this.itemsCount,
    required this.totalAmount,
    required this.discountAmount,
    required this.finalAmount,
    this.shippingOptions = const <String, double>{},
    this.promoCode,
    required this.createdAt,
    required this.updatedAt,
  });

  factory Cart.fromJson(Map<String, dynamic> json) => _$CartFromJson(json);
  Map<String, dynamic> toJson() => _$CartToJson(this);
}

@JsonSerializable()
class CartItem {
  @JsonKey(fromJson: _cartSafeInt)
  final int id;
  @JsonKey(fromJson: _cartSafeInt)
  final int product;
  @JsonKey(name: 'product_name', fromJson: _cartSafeStr)
  final String productName;
  @JsonKey(name: 'product_slug', fromJson: _cartSafeStr)
  final String productSlug;
  @JsonKey(name: 'product_type')
  final String? productType;
  @JsonKey(name: 'product_image_url')
  final String? productImageUrl;
  @JsonKey(name: 'product_video_url')
  final String? productVideoUrl;
  @JsonKey(name: 'product_translations', fromJson: _cartSafeDynamicStr)
  final String? productTranslations;
  @JsonKey(fromJson: _cartSafeInt)
  final int quantity;
  @JsonKey(fromJson: _cartSafeStr)
  final String price;
  @JsonKey(fromJson: _cartSafeStr)
  final String currency;
  @JsonKey(name: 'old_price', fromJson: _cartSafeDynamicStr)
  final String? oldPrice;
  @JsonKey(name: 'old_price_formatted', fromJson: _cartSafeDynamicStr)
  final String? oldPriceFormatted;
  @JsonKey(name: 'chosen_size')
  final String? chosenSize;
  @JsonKey(name: 'created_at', fromJson: _cartSafeDateTime)
  final DateTime createdAt;
  @JsonKey(name: 'updated_at', fromJson: _cartSafeDateTime)
  final DateTime updatedAt;
  @JsonKey(name: 'converted_price_rub', fromJson: _cartSafeDynamicStr)
  final String? convertedPriceRub;
  @JsonKey(name: 'converted_price_usd', fromJson: _cartSafeDynamicStr)
  final String? convertedPriceUsd;
  @JsonKey(name: 'final_price_rub', fromJson: _cartSafeDynamicStr)
  final String? finalPriceRub;
  @JsonKey(name: 'final_price_usd', fromJson: _cartSafeDynamicStr)
  final String? finalPriceUsd;
  @JsonKey(name: 'margin_percent_applied', fromJson: _cartSafeDynamicStr)
  final String? marginPercentApplied;
  @JsonKey(name: 'prices_in_currencies', fromJson: _cartSafeDynamicStr)
  final String? pricesInCurrencies;
  @JsonKey(fromJson: _cartSafeStr)
  final String total;

  CartItem({
    required this.id,
    required this.product,
    required this.productName,
    required this.productSlug,
    this.productType,
    this.productImageUrl,
    this.productVideoUrl,
    this.productTranslations,
    required this.quantity,
    required this.price,
    required this.currency,
    this.oldPrice,
    this.oldPriceFormatted,
    this.chosenSize,
    required this.createdAt,
    required this.updatedAt,
    this.convertedPriceRub,
    this.convertedPriceUsd,
    this.finalPriceRub,
    this.finalPriceUsd,
    this.marginPercentApplied,
    this.pricesInCurrencies,
    required this.total,
  });

  factory CartItem.fromJson(Map<String, dynamic> json) => _$CartItemFromJson(json);
  Map<String, dynamic> toJson() => _$CartItemToJson(this);
}

@JsonSerializable()
class PromoCode {
  @JsonKey(fromJson: _cartSafeInt)
  final int id;
  @JsonKey(fromJson: _cartSafeStr)
  final String code;
  @JsonKey(name: 'discount_type', fromJson: _cartSafeStr)
  final String discountType;
  @JsonKey(name: 'discount_value', fromJson: _cartSafeStr)
  final String discountValue;

  PromoCode({
    required this.id,
    required this.code,
    required this.discountType,
    required this.discountValue,
  });

  factory PromoCode.fromJson(Map<String, dynamic> json) => _$PromoCodeFromJson(json);
  Map<String, dynamic> toJson() => _$PromoCodeToJson(this);
}

@JsonSerializable(includeIfNull: false)
class AddToCartRequest {
  @JsonKey(name: 'product_id')
  final int? productId;
  @JsonKey(name: 'product_type')
  final String? productType;
  @JsonKey(name: 'product_slug')
  final String? productSlug;
  final String? size;
  final int quantity;

  AddToCartRequest({
    this.productId,
    this.productType,
    this.productSlug,
    this.size,
    this.quantity = 1,
  });

  factory AddToCartRequest.fromJson(Map<String, dynamic> json) => _$AddToCartRequestFromJson(json);
  Map<String, dynamic> toJson() => _$AddToCartRequestToJson(this);
}

@JsonSerializable()
class UpdateCartItemRequest {
  final int quantity;

  UpdateCartItemRequest({
    required this.quantity,
  });

  factory UpdateCartItemRequest.fromJson(Map<String, dynamic> json) => _$UpdateCartItemRequestFromJson(json);
  Map<String, dynamic> toJson() => _$UpdateCartItemRequestToJson(this);
}

@JsonSerializable()
class ApplyPromoCodeRequest {
  final String code;

  ApplyPromoCodeRequest({
    required this.code,
  });

  factory ApplyPromoCodeRequest.fromJson(Map<String, dynamic> json) => _$ApplyPromoCodeRequestFromJson(json);
  Map<String, dynamic> toJson() => _$ApplyPromoCodeRequestToJson(this);
}

import 'package:json_annotation/json_annotation.dart';

part 'favorite.g.dart';

@JsonSerializable()
class Favorite {
  final int id;
  final FavoriteProduct product;
  @JsonKey(name: 'created_at')
  final DateTime createdAt;

  Favorite({
    required this.id,
    required this.product,
    required this.createdAt,
  });

  factory Favorite.fromJson(Map<String, dynamic> json) => _$FavoriteFromJson(json);
  Map<String, dynamic> toJson() => _$FavoriteToJson(this);
}

String _favoriteSafeStr(dynamic v) {
  if (v == null) return '0';
  if (v is String) return v;
  return v.toString();
}

String? _favoriteOptStr(dynamic v) {
  if (v == null) return null;
  if (v is String) return v.isEmpty ? null : v;
  return v.toString();
}

@JsonSerializable()
class FavoriteProduct {
  final int id;
  final String name;
  final String slug;
  @JsonKey(fromJson: _favoriteSafeStr)
  final String price;
  @JsonKey(fromJson: _favoriteSafeStr)
  final String currency;
  @JsonKey(name: 'main_image_url')
  final String? mainImageUrl;

  FavoriteProduct({
    required this.id,
    required this.name,
    required this.slug,
    required this.price,
    required this.currency,
    this.mainImageUrl,
  });

  factory FavoriteProduct.fromJson(Map<String, dynamic> json) => _$FavoriteProductFromJson(json);
  Map<String, dynamic> toJson() => _$FavoriteProductToJson(this);
}

@JsonSerializable()
class AddToFavoriteRequest {
  final int productId;
  final String? productType;

  AddToFavoriteRequest({
    required this.productId,
    this.productType,
  });

  factory AddToFavoriteRequest.fromJson(Map<String, dynamic> json) => _$AddToFavoriteRequestFromJson(json);
  Map<String, dynamic> toJson() => _$AddToFavoriteRequestToJson(this);
}

@JsonSerializable()
class FavoriteCheckResponse {
  final bool isFavorite;

  FavoriteCheckResponse({
    required this.isFavorite,
  });

  factory FavoriteCheckResponse.fromJson(Map<String, dynamic> json) => _$FavoriteCheckResponseFromJson(json);
  Map<String, dynamic> toJson() => _$FavoriteCheckResponseToJson(this);
}

@JsonSerializable()
class FavoriteCountResponse {
  final int count;

  FavoriteCountResponse({
    required this.count,
  });

  factory FavoriteCountResponse.fromJson(Map<String, dynamic> json) => _$FavoriteCountResponseFromJson(json);
  Map<String, dynamic> toJson() => _$FavoriteCountResponseToJson(this);
}

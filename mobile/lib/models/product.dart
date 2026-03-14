import 'package:json_annotation/json_annotation.dart';

part 'product.g.dart';

String _intOrStringToStr(dynamic v) => v?.toString() ?? '0';
String _safeStr(dynamic v) => v?.toString() ?? '';
int _safeInt(dynamic v) => (v as num?)?.toInt() ?? 0;
bool _safeBool(dynamic v) => v == null ? false : v == true || v == 'true' || v == 1;
DateTime _safeDateTime(dynamic v) {
  if (v == null) return DateTime.now();
  try {
    return DateTime.parse(v.toString());
  } catch (_) {
    return DateTime.now();
  }
}

@JsonSerializable()
class Product {
  @JsonKey(fromJson: _safeInt)
  final int id;
  @JsonKey(fromJson: _safeStr)
  final String name;
  @JsonKey(fromJson: _safeStr)
  final String slug;
  final String? description;
  final Category? category;
  final Brand? brand;
  @JsonKey(fromJson: _safeStr)
  final String? price;
  @JsonKey(name: 'price_formatted', fromJson: _safeStr)
  final String? priceFormatted;
  @JsonKey(name: 'old_price', fromJson: _safeStr)
  final String? oldPrice;
  @JsonKey(name: 'old_price_formatted', fromJson: _safeStr)
  final String? oldPriceFormatted;
  @JsonKey(fromJson: _safeStr)
  final String currency;
  @JsonKey(name: 'is_available', defaultValue: true)
  final bool isAvailable;
  @JsonKey(name: 'stock_quantity')
  final int? stockQuantity;
  @JsonKey(name: 'main_image')
  final String? mainImage;
  @JsonKey(name: 'main_image_url')
  final String? mainImageUrl;
  @JsonKey(name: 'is_new', defaultValue: false)
  final bool isNew;
  @JsonKey(name: 'is_featured', defaultValue: false)
  final bool isFeatured;
  @JsonKey(name: 'created_at', fromJson: _safeDateTime)
  final DateTime createdAt;
  @JsonKey(name: 'updated_at', fromJson: _safeDateTime)
  final DateTime updatedAt;
  final List<ProductTranslation>? translations;
  @JsonKey(name: 'meta_title')
  final String? metaTitle;
  @JsonKey(name: 'meta_description')
  final String? metaDescription;
  @JsonKey(name: 'meta_keywords')
  final String? metaKeywords;
  @JsonKey(name: 'video_url')
  final String? videoUrl;

  Product({
    required this.id,
    required this.name,
    required this.slug,
    this.description,
    this.category,
    this.brand,
    this.price,
    this.priceFormatted,
    this.oldPrice,
    this.oldPriceFormatted,
    required this.currency,
    required this.isAvailable,
    this.stockQuantity,
    this.mainImage,
    this.mainImageUrl,
    required this.isNew,
    required this.isFeatured,
    required this.createdAt,
    required this.updatedAt,
    this.translations,
    this.metaTitle,
    this.metaDescription,
    this.metaKeywords,
    this.videoUrl,
  });

  factory Product.fromJson(Map<String, dynamic> json) => _$ProductFromJson(json);
  Map<String, dynamic> toJson() => _$ProductToJson(this);
}

@JsonSerializable()
class ProductDetail extends Product {
  final List<ProductImage>? images;
  final List<ProductVariant>? variants;
  @JsonKey(name: 'dynamic_attributes')
  final List<ProductAttribute>? dynamicAttributes;
  @JsonKey(name: 'similar_products')
  final List<Product>? similarProducts;

  ProductDetail({
    required super.id,
    required super.name,
    required super.slug,
    super.description,
    super.category,
    super.brand,
    super.price,
    super.priceFormatted,
    super.oldPrice,
    super.oldPriceFormatted,
    required super.currency,
    required super.isAvailable,
    super.stockQuantity,
    super.mainImage,
    super.mainImageUrl,
    super.videoUrl,
    required super.isNew,
    required super.isFeatured,
    required super.createdAt,
    required super.updatedAt,
    super.translations,
    super.metaTitle,
    super.metaDescription,
    super.metaKeywords,
    this.images,
    this.variants,
    this.dynamicAttributes,
    this.similarProducts,
  });

  factory ProductDetail.fromJson(Map<String, dynamic> json) => _$ProductDetailFromJson(json);
  @override
  Map<String, dynamic> toJson() => _$ProductDetailToJson(this);
}

@JsonSerializable()
class ProductImage {
  final int id;
  @JsonKey(name: 'image_url', fromJson: _safeStr)
  final String image;
  @JsonKey(name: 'video_url', fromJson: _safeStr)
  final String? videoUrl;
  @JsonKey(name: 'is_main', defaultValue: false)
  final bool isMain;
  @JsonKey(name: 'created_at', fromJson: _safeDateTime)
  final DateTime createdAt;

  ProductImage({
    required this.id,
    required this.image,
    this.videoUrl,
    required this.isMain,
    required this.createdAt,
  });

  /// URL для отображения: изображение или видео (для видео image часто пустое)
  String? get displayUrl => (image.isNotEmpty ? image : null) ?? videoUrl;

  factory ProductImage.fromJson(Map<String, dynamic> json) => _$ProductImageFromJson(json);
  Map<String, dynamic> toJson() => _$ProductImageToJson(this);
}

@JsonSerializable()
class ProductVariant {
  final int id;
  final String? sku;
  @JsonKey(fromJson: _safeStr)
  final String? price;
  @JsonKey(name: 'old_price', fromJson: _safeStr)
  final String? oldPrice;
  @JsonKey(name: 'stock_quantity', fromJson: _safeInt)
  final int stockQuantity;
  @JsonKey(name: 'is_available', defaultValue: true)
  final bool isAvailable;
  final List<ProductVariantImage>? images;

  ProductVariant({
    required this.id,
    this.sku,
    this.price,
    this.oldPrice,
    required this.stockQuantity,
    required this.isAvailable,
    this.images,
  });

  factory ProductVariant.fromJson(Map<String, dynamic> json) => _$ProductVariantFromJson(json);
  Map<String, dynamic> toJson() => _$ProductVariantToJson(this);
}

@JsonSerializable()
class ProductVariantImage {
  final int id;
  @JsonKey(name: 'image_url', fromJson: _safeStr)
  final String image;
  @JsonKey(name: 'is_main', defaultValue: false)
  final bool isMain;
  @JsonKey(name: 'created_at', fromJson: _safeDateTime)
  final DateTime createdAt;

  ProductVariantImage({
    required this.id,
    required this.image,
    required this.isMain,
    required this.createdAt,
  });

  factory ProductVariantImage.fromJson(Map<String, dynamic> json) => _$ProductVariantImageFromJson(json);
  Map<String, dynamic> toJson() => _$ProductVariantImageToJson(this);
}

@JsonSerializable()
class ProductAttribute {
  final String name;
  @JsonKey(fromJson: _safeStr)
  final String value;
  @JsonKey(name: 'display_name')
  final String? displayName;

  ProductAttribute({
    required this.name,
    required this.value,
    this.displayName,
  });

  factory ProductAttribute.fromJson(Map<String, dynamic> json) => _$ProductAttributeFromJson(json);
  Map<String, dynamic> toJson() => _$ProductAttributeToJson(this);
}

@JsonSerializable()
class ProductTranslation {
  final String locale;
  final String name;
  final String? description;

  ProductTranslation({
    required this.locale,
    required this.name,
    this.description,
  });

  factory ProductTranslation.fromJson(Map<String, dynamic> json) => _$ProductTranslationFromJson(json);
  Map<String, dynamic> toJson() => _$ProductTranslationToJson(this);
}

@JsonSerializable()
class Category {
  @JsonKey(fromJson: _safeInt)
  final int id;
  @JsonKey(fromJson: _safeStr)
  final String name;
  @JsonKey(fromJson: _safeStr)
  final String slug;
  final String? description;
  @JsonKey(name: 'card_media_url')
  final String? cardMediaUrl;
  final int? parent;
  @JsonKey(name: 'external_id')
  final String? externalId;
  @JsonKey(name: 'is_active', defaultValue: true)
  final bool isActive;
  @JsonKey(name: 'sort_order', fromJson: _safeInt)
  final int sortOrder;
  @JsonKey(name: 'children_count', fromJson: _intOrStringToStr)
  final String childrenCount;
  @JsonKey(name: 'products_count', fromJson: _intOrStringToStr)
  final String productsCount;
  @JsonKey(name: 'created_at', fromJson: _safeDateTime)
  final DateTime createdAt;
  @JsonKey(name: 'updated_at', fromJson: _safeDateTime)
  final DateTime updatedAt;
  @JsonKey(name: 'category_type')
  final String? categoryType;
  @JsonKey(name: 'category_type_slug')
  final String? categoryTypeSlug;
  final List<CategoryTranslation>? translations;
  final String? gender;
  @JsonKey(name: 'gender_display')
  final String? genderDisplay;

  Category({
    required this.id,
    required this.name,
    required this.slug,
    this.description,
    this.cardMediaUrl,
    this.parent,
    this.externalId,
    required this.isActive,
    required this.sortOrder,
    required this.childrenCount,
    required this.productsCount,
    required this.createdAt,
    required this.updatedAt,
    this.categoryType,
    this.categoryTypeSlug,
    this.translations,
    this.gender,
    this.genderDisplay,
  });

  factory Category.fromJson(Map<String, dynamic> json) => _$CategoryFromJson(json);
  Map<String, dynamic> toJson() => _$CategoryToJson(this);
}

@JsonSerializable()
class CategoryTranslation {
  final String locale;
  final String name;
  final String? description;

  CategoryTranslation({
    required this.locale,
    required this.name,
    this.description,
  });

  factory CategoryTranslation.fromJson(Map<String, dynamic> json) => _$CategoryTranslationFromJson(json);
  Map<String, dynamic> toJson() => _$CategoryTranslationToJson(this);
}

@JsonSerializable()
class Brand {
  @JsonKey(fromJson: _safeInt)
  final int id;
  @JsonKey(fromJson: _safeStr)
  final String name;
  @JsonKey(fromJson: _safeStr)
  final String slug;
  final String? description;
  final String? logo;
  final String? website;
  @JsonKey(name: 'card_media_url')
  final String? cardMediaUrl;
  @JsonKey(name: 'primary_category_slug')
  final String? primaryCategorySlug;
  @JsonKey(name: 'external_id')
  final String? externalId;
  @JsonKey(name: 'is_active', defaultValue: true)
  final bool isActive;
  @JsonKey(name: 'products_count', fromJson: _intOrStringToStr)
  final String productsCount;
  final List<BrandTranslation>? translations;
  @JsonKey(name: 'created_at', fromJson: _safeDateTime)
  final DateTime createdAt;
  @JsonKey(name: 'updated_at', fromJson: _safeDateTime)
  final DateTime updatedAt;

  Brand({
    required this.id,
    required this.name,
    required this.slug,
    this.description,
    this.logo,
    this.website,
    this.cardMediaUrl,
    this.primaryCategorySlug,
    this.externalId,
    required this.isActive,
    required this.productsCount,
    this.translations,
    required this.createdAt,
    required this.updatedAt,
  });

  factory Brand.fromJson(Map<String, dynamic> json) => _$BrandFromJson(json);
  Map<String, dynamic> toJson() => _$BrandToJson(this);
}

@JsonSerializable()
class BrandTranslation {
  final String locale;
  final String name;
  final String? description;

  BrandTranslation({
    required this.locale,
    required this.name,
    this.description,
  });

  factory BrandTranslation.fromJson(Map<String, dynamic> json) => _$BrandTranslationFromJson(json);
  Map<String, dynamic> toJson() => _$BrandTranslationToJson(this);
}

@JsonSerializable(genericArgumentFactories: true, createFactory: false)
class PaginatedResponse<T> {
  final int count;
  final String? next;
  final String? previous;
  final List<T> results;

  PaginatedResponse({
    required this.count,
    this.next,
    this.previous,
    required this.results,
  });

  factory PaginatedResponse.fromJson(
    Map<String, dynamic> json,
    T Function(Object? json) fromJsonT,
  ) {
    final resultsRaw = json['results'];
    final resultsList = resultsRaw is List
        ? resultsRaw.map((e) => fromJsonT(e)).toList()
        : <T>[];
    return PaginatedResponse<T>(
      count: (json['count'] as num?)?.toInt() ?? 0,
      next: json['next'] as String?,
      previous: json['previous'] as String?,
      results: resultsList,
    );
  }

  Map<String, dynamic> toJson(Object? Function(T value) toJsonT) =>
      _$PaginatedResponseToJson(this, toJsonT);
}

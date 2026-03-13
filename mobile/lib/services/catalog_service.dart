import 'package:dio/dio.dart';
import 'api_client.dart';
import '../models/models.dart';

class CatalogService {
  final ApiClient _apiClient = ApiClient();

  // Products
  Future<PaginatedResponse<Product>> getProducts({
    int? page,
    int? pageSize,
    String? search,
    String? categorySlug,
    int? categoryId,
    int? brandId,
    String? productType,
    double? minPrice,
    double? maxPrice,
    bool? isAvailable,
    bool? isNew,
    String? ordering,
    String? availabilityStatus,
    String? countryOfOrigin,
  }) async {
    try {
      final queryParams = <String, dynamic>{};
      if (page != null) queryParams['page'] = page;
      if (pageSize != null) queryParams['page_size'] = pageSize;
      if (search != null) queryParams['search'] = search;
      if (categorySlug != null) queryParams['category_slug'] = categorySlug;
      if (categoryId != null) queryParams['category_id'] = categoryId;
      if (brandId != null) queryParams['brand_id'] = brandId;
      if (productType != null) queryParams['product_type'] = productType;
      if (minPrice != null) queryParams['min_price'] = minPrice;
      if (maxPrice != null) queryParams['max_price'] = maxPrice;
      if (isAvailable != null) queryParams['is_available'] = isAvailable;
      if (isNew != null) queryParams['is_new'] = isNew;
      if (ordering != null) queryParams['ordering'] = ordering;
      if (availabilityStatus != null) queryParams['availability_status'] = availabilityStatus;
      if (countryOfOrigin != null) queryParams['country_of_origin'] = countryOfOrigin;

      final response = await _apiClient.dio.get(
        '/catalog/products',
        queryParameters: queryParams.isNotEmpty ? queryParams : null,
      );

      return PaginatedResponse.fromJson(
        response.data,
        (json) => Product.fromJson(json as Map<String, dynamic>),
      );
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<ProductDetail> getProductDetail(String slug) async {
    try {
      final response = await _apiClient.dio.get('/catalog/products/$slug');
      return ProductDetail.fromJson(response.data);
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<List<Product>> getFeaturedProducts() async {
    try {
      final response = await _apiClient.dio.get('/catalog/products/featured');
      return (response.data as List)
          .map((json) => Product.fromJson(json))
          .toList();
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<List<Product>> searchProducts(String query) async {
    try {
      final response = await _apiClient.dio.get(
        '/catalog/products/search',
        queryParameters: {'q': query},
      );
      return (response.data as List)
          .map((json) => Product.fromJson(json))
          .toList();
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<List<Product>> getSimilarProducts(String slug) async {
    try {
      final response = await _apiClient.dio.get('/catalog/products/$slug/similar');
      return (response.data as List)
          .map((json) => Product.fromJson(json))
          .toList();
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<List<Product>> getVisuallySimilarProducts(String slug) async {
    try {
      final response = await _apiClient.dio.get('/catalog/products/$slug/visually_similar');
      return (response.data as List)
          .map((json) => Product.fromJson(json))
          .toList();
    } catch (e) {
      throw _handleError(e);
    }
  }

  // Categories
  Future<PaginatedResponse<Category>> getCategories({
    int? page,
    int? pageSize,
    bool? topLevel,
    int? parentId,
    String? parentSlug,
    String? slug,
    bool? all,
    bool? includeChildren,
    String? categorySlug,
  }) async {
    try {
      final queryParams = <String, dynamic>{};
      if (page != null) queryParams['page'] = page;
      if (pageSize != null) queryParams['page_size'] = pageSize;
      if (topLevel != null) queryParams['top_level'] = topLevel;
      if (parentId != null) queryParams['parent_id'] = parentId;
      if (parentSlug != null) queryParams['parent_slug'] = parentSlug;
      if (slug != null) queryParams['slug'] = slug;
      if (all != null) queryParams['all'] = all;
      if (includeChildren != null) queryParams['include_children'] = includeChildren;
      if (categorySlug != null) queryParams['category_slug'] = categorySlug;

      final response = await _apiClient.dio.get(
        '/catalog/categories',
        queryParameters: queryParams.isNotEmpty ? queryParams : null,
      );

      return PaginatedResponse.fromJson(
        response.data,
        (json) => Category.fromJson(json as Map<String, dynamic>),
      );
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<Category> getCategory(int id) async {
    try {
      final response = await _apiClient.dio.get('/catalog/categories/$id');
      return Category.fromJson(response.data);
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<Category> getCategoryChildren(int id) async {
    try {
      final response = await _apiClient.dio.get('/catalog/categories/$id/children');
      return Category.fromJson(response.data);
    } catch (e) {
      throw _handleError(e);
    }
  }

  // Brands
  Future<PaginatedResponse<Brand>> getBrands({
    int? page,
    int? pageSize,
    String? productType,
    String? categorySlug,
    int? categoryId,
    String? primaryCategorySlug,
    bool? inStock,
  }) async {
    try {
      final queryParams = <String, dynamic>{};
      if (page != null) queryParams['page'] = page;
      if (pageSize != null) queryParams['page_size'] = pageSize;
      if (productType != null) queryParams['product_type'] = productType;
      if (categorySlug != null) queryParams['category_slug'] = categorySlug;
      if (categoryId != null) queryParams['category_id'] = categoryId;
      if (primaryCategorySlug != null) queryParams['primary_category_slug'] = primaryCategorySlug;
      if (inStock != null) queryParams['in_stock'] = inStock;

      final response = await _apiClient.dio.get(
        '/catalog/brands',
        queryParameters: queryParams.isNotEmpty ? queryParams : null,
      );

      return PaginatedResponse.fromJson(
        response.data,
        (json) => Brand.fromJson(json as Map<String, dynamic>),
      );
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<Brand> getBrand(int id) async {
    try {
      final response = await _apiClient.dio.get('/catalog/brands/$id');
      return Brand.fromJson(response.data);
    } catch (e) {
      throw _handleError(e);
    }
  }

  // Banners
  Future<List<Banner>> getBanners({String? position}) async {
    try {
      final queryParams = <String, dynamic>{};
      if (position != null) queryParams['position'] = position;

      final response = await _apiClient.dio.get(
        '/catalog/banners',
        queryParameters: queryParams.isNotEmpty ? queryParams : null,
      );
      return (response.data as List)
          .map((json) => Banner.fromJson(json))
          .toList();
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<Banner> getBanner(int id) async {
    try {
      final response = await _apiClient.dio.get('/catalog/banners/$id');
      return Banner.fromJson(response.data);
    } catch (e) {
      throw _handleError(e);
    }
  }

  // Product Type Specific Endpoints
  Future<PaginatedResponse<Product>> getClothingProducts({
    int? page,
    int? pageSize,
    String? search,
    String? categorySlug,
    int? categoryId,
    int? brandId,
    String? gender,
    String? color,
    String? size,
    String? material,
    String? season,
    double? minPrice,
    double? maxPrice,
    bool? isNew,
    String? ordering,
  }) async {
    try {
      final queryParams = <String, dynamic>{};
      if (page != null) queryParams['page'] = page;
      if (pageSize != null) queryParams['page_size'] = pageSize;
      if (search != null) queryParams['search'] = search;
      if (categorySlug != null) queryParams['category_slug'] = categorySlug;
      if (categoryId != null) queryParams['category_id'] = categoryId;
      if (brandId != null) queryParams['brand_id'] = brandId;
      if (gender != null) queryParams['gender'] = gender;
      if (color != null) queryParams['color'] = color;
      if (size != null) queryParams['size'] = size;
      if (material != null) queryParams['material'] = material;
      if (season != null) queryParams['season'] = season;
      if (minPrice != null) queryParams['min_price'] = minPrice;
      if (maxPrice != null) queryParams['max_price'] = maxPrice;
      if (isNew != null) queryParams['is_new'] = isNew;
      if (ordering != null) queryParams['ordering'] = ordering;

      final response = await _apiClient.dio.get(
        '/catalog/clothing/products',
        queryParameters: queryParams.isNotEmpty ? queryParams : null,
      );

      return PaginatedResponse.fromJson(
        response.data,
        (json) => Product.fromJson(json as Map<String, dynamic>),
      );
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<PaginatedResponse<Product>> getShoesProducts({
    int? page,
    int? pageSize,
    String? search,
    String? categorySlug,
    int? categoryId,
    int? brandId,
    String? gender,
    String? color,
    String? size,
    String? material,
    String? shoeType,
    String? heelHeight,
    double? minPrice,
    double? maxPrice,
    bool? isNew,
    String? ordering,
  }) async {
    try {
      final queryParams = <String, dynamic>{};
      if (page != null) queryParams['page'] = page;
      if (pageSize != null) queryParams['page_size'] = pageSize;
      if (search != null) queryParams['search'] = search;
      if (categorySlug != null) queryParams['category_slug'] = categorySlug;
      if (categoryId != null) queryParams['category_id'] = categoryId;
      if (brandId != null) queryParams['brand_id'] = brandId;
      if (gender != null) queryParams['gender'] = gender;
      if (color != null) queryParams['color'] = color;
      if (size != null) queryParams['size'] = size;
      if (material != null) queryParams['material'] = material;
      if (shoeType != null) queryParams['shoe_type'] = shoeType;
      if (heelHeight != null) queryParams['heel_height'] = heelHeight;
      if (minPrice != null) queryParams['min_price'] = minPrice;
      if (maxPrice != null) queryParams['max_price'] = maxPrice;
      if (isNew != null) queryParams['is_new'] = isNew;
      if (ordering != null) queryParams['ordering'] = ordering;

      final response = await _apiClient.dio.get(
        '/catalog/shoes/products',
        queryParameters: queryParams.isNotEmpty ? queryParams : null,
      );

      return PaginatedResponse.fromJson(
        response.data,
        (json) => Product.fromJson(json as Map<String, dynamic>),
      );
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<PaginatedResponse<Product>> getElectronicsProducts({
    int? page,
    int? pageSize,
    String? search,
    String? categorySlug,
    int? categoryId,
    int? brandId,
    String? model,
    double? minPrice,
    double? maxPrice,
    bool? isNew,
    String? ordering,
  }) async {
    try {
      final queryParams = <String, dynamic>{};
      if (page != null) queryParams['page'] = page;
      if (pageSize != null) queryParams['page_size'] = pageSize;
      if (search != null) queryParams['search'] = search;
      if (categorySlug != null) queryParams['category_slug'] = categorySlug;
      if (categoryId != null) queryParams['category_id'] = categoryId;
      if (brandId != null) queryParams['brand_id'] = brandId;
      if (model != null) queryParams['model'] = model;
      if (minPrice != null) queryParams['min_price'] = minPrice;
      if (maxPrice != null) queryParams['max_price'] = maxPrice;
      if (isNew != null) queryParams['is_new'] = isNew;
      if (ordering != null) queryParams['ordering'] = ordering;

      final response = await _apiClient.dio.get(
        '/catalog/electronics/products',
        queryParameters: queryParams.isNotEmpty ? queryParams : null,
      );

      return PaginatedResponse.fromJson(
        response.data,
        (json) => Product.fromJson(json as Map<String, dynamic>),
      );
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
        }
        return 'Ошибка сервера: ${error.response!.statusCode}';
      }
      return 'Ошибка соединения: ${error.message}';
    }
    return 'Неизвестная ошибка: $error';
  }
}

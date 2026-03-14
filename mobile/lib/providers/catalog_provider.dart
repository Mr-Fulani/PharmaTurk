import 'package:flutter/foundation.dart' hide Category;
import '../models/models.dart';
import '../services/services.dart';

class CatalogProvider extends ChangeNotifier {
  final CatalogService _catalogService = CatalogService();

  // Products
  List<Product> _products = [];
  ProductDetail? _selectedProduct;
  List<Product> _featuredProducts = [];
  List<Product> _similarProducts = [];
  List<Product> _searchResults = [];
  List<Product> _visualSearchResults = [];
  bool _isLoadingProducts = false;
  bool _isLoadingVisualSearch = false;
  String? _visualSearchError;
  bool _isLoadingProductDetail = false;
  bool _hasMoreProducts = true;
  int _currentPage = 1;
  String? _productsError;

  // Categories
  List<Category> _categories = [];
  Category? _selectedCategory;
  bool _isLoadingCategories = false;
  String? _categoriesError;

  // Brands
  List<Brand> _brands = [];
  Brand? _selectedBrand;
  bool _isLoadingBrands = false;
  String? _brandsError;

  // Banners
  List<Banner> _banners = [];
  bool _isLoadingBanners = false;
  String? _bannersError;

  // Filters
  String? _selectedCategorySlug;
  int? _selectedBrandId;
  double? _minPrice;
  double? _maxPrice;
  String? _searchQuery;
  String? _ordering;
  bool? _isNew;
  bool? _isAvailable;

  // Getters
  List<Product> get products => _products;
  ProductDetail? get selectedProduct => _selectedProduct;
  List<Product> get featuredProducts => _featuredProducts;
  List<Product> get similarProducts => _similarProducts;
  List<Product> get searchResults => _searchResults;
  List<Product> get visualSearchResults => _visualSearchResults;
  bool get isLoadingProducts => _isLoadingProducts;
  bool get isLoadingVisualSearch => _isLoadingVisualSearch;
  String? get visualSearchError => _visualSearchError;
  bool get isLoadingProductDetail => _isLoadingProductDetail;
  bool get hasMoreProducts => _hasMoreProducts;
  String? get productsError => _productsError;

  List<Category> get categories => _categories;
  Category? get selectedCategory => _selectedCategory;
  bool get isLoadingCategories => _isLoadingCategories;
  String? get categoriesError => _categoriesError;

  List<Brand> get brands => _brands;
  Brand? get selectedBrand => _selectedBrand;
  bool get isLoadingBrands => _isLoadingBrands;
  String? get brandsError => _brandsError;

  List<Banner> get banners => _banners;
  bool get isLoadingBanners => _isLoadingBanners;
  String? get bannersError => _bannersError;

  // Filter getters
  String? get selectedCategorySlug => _selectedCategorySlug;
  int? get selectedBrandId => _selectedBrandId;
  double? get minPrice => _minPrice;
  double? get maxPrice => _maxPrice;
  String? get searchQuery => _searchQuery;
  String? get ordering => _ordering;
  bool? get isNewFilter => _isNew;
  bool? get isAvailableFilter => _isAvailable;

  // Products
  Future<void> getProducts({
    bool refresh = false,
    int page = 1,
    int pageSize = 20,
    String? search,
    String? categorySlug,
    int? brandId,
    double? minPrice,
    double? maxPrice,
    bool? isNew,
    bool? isAvailable,
    String? ordering,
  }) async {
    if (refresh) {
      _products = [];
      _currentPage = 1;
      _hasMoreProducts = true;
    }

    if (!_hasMoreProducts && !refresh) return;

    _isLoadingProducts = true;
    _productsError = null;
    notifyListeners();

    try {
      final response = await _catalogService.getProducts(
        page: page,
        pageSize: pageSize,
        search: search ?? _searchQuery,
        categorySlug: categorySlug ?? _selectedCategorySlug,
        brandId: brandId ?? _selectedBrandId,
        minPrice: minPrice ?? _minPrice,
        maxPrice: maxPrice ?? _maxPrice,
        isNew: isNew ?? _isNew,
        isAvailable: isAvailable ?? _isAvailable,
        ordering: ordering ?? _ordering,
      );

      if (refresh) {
        _products = response.results;
      } else {
        _products.addAll(response.results);
      }

      _hasMoreProducts = response.next != null;
      _currentPage = page;
      _isLoadingProducts = false;
      notifyListeners();
    } catch (e) {
      _productsError = e.toString();
      _isLoadingProducts = false;
      notifyListeners();
    }
  }

  Future<void> loadMoreProducts() async {
    if (_isLoadingProducts || !_hasMoreProducts) return;
    await getProducts(page: _currentPage + 1);
  }

  Future<void> getProductDetail(String slug) async {
    _isLoadingProductDetail = true;
    _productsError = null;
    notifyListeners();

    try {
      _selectedProduct = await _catalogService.getProductDetail(slug);
      _isLoadingProductDetail = false;
      notifyListeners();
      
      // Load similar products
      await getSimilarProducts(slug);
    } catch (e) {
      _productsError = e.toString();
      _isLoadingProductDetail = false;
      notifyListeners();
    }
  }

  Future<void> getFeaturedProducts() async {
    try {
      _featuredProducts = await _catalogService.getFeaturedProducts();
      notifyListeners();
    } catch (e) {
      _productsError = e.toString();
    }
  }

  Future<void> getSimilarProducts(String slug) async {
    try {
      _similarProducts = await _catalogService.getSimilarProducts(slug);
      notifyListeners();
    } catch (e) {
      // Don't show error for similar products
    }
  }

  Future<void> searchProducts(String query) async {
    _searchQuery = query;
    _isLoadingProducts = true;
    _productsError = null;
    notifyListeners();

    try {
      _searchResults = await _catalogService.searchProducts(query);
      _isLoadingProducts = false;
      notifyListeners();
    } catch (e) {
      _productsError = e.toString();
      _isLoadingProducts = false;
      notifyListeners();
    }
  }

  /// Поиск по фото: загрузка файла + search_by_image или только по URL.
  Future<void> searchByImage(String imageUrl) async {
    _visualSearchResults = [];
    _visualSearchError = null;
    _isLoadingVisualSearch = true;
    notifyListeners();

    try {
      _visualSearchResults = await _catalogService.searchByImage(imageUrl, limit: 12);
      _isLoadingVisualSearch = false;
      notifyListeners();
    } catch (e) {
      _visualSearchError = e.toString();
      _visualSearchResults = [];
      _isLoadingVisualSearch = false;
      notifyListeners();
    }
  }

  /// Загрузка фото и поиск по нему.
  Future<void> searchByImageFile(String filePath) async {
    _visualSearchResults = [];
    _visualSearchError = null;
    _isLoadingVisualSearch = true;
    notifyListeners();

    try {
      final url = await _catalogService.uploadTempImage(filePath);
      await searchByImage(url);
    } catch (e) {
      _visualSearchError = e.toString();
      _visualSearchResults = [];
      _isLoadingVisualSearch = false;
      notifyListeners();
    }
  }

  void clearVisualSearch() {
    _visualSearchResults = [];
    _visualSearchError = null;
    notifyListeners();
  }

  // Categories
  Future<void> getCategories({
    bool topLevel = false,
    int? parentId,
    bool? all,
  }) async {
    _isLoadingCategories = true;
    _categoriesError = null;
    notifyListeners();

    try {
      final response = await _catalogService.getCategories(
        topLevel: topLevel,
        parentId: parentId,
        all: all,
      );
      _categories = response.results;
      _isLoadingCategories = false;
      notifyListeners();
    } catch (e) {
      _categoriesError = e.toString();
      _isLoadingCategories = false;
      notifyListeners();
    }
  }

  Future<void> getCategory(int id) async {
    try {
      _selectedCategory = await _catalogService.getCategory(id);
      notifyListeners();
    } catch (e) {
      _categoriesError = e.toString();
    }
  }

  // Brands
  Future<void> getBrands({
    String? productType,
    String? categorySlug,
    bool? inStock,
  }) async {
    _isLoadingBrands = true;
    _brandsError = null;
    notifyListeners();

    try {
      final response = await _catalogService.getBrands(
        productType: productType,
        categorySlug: categorySlug,
        inStock: inStock,
      );
      _brands = response.results;
      _isLoadingBrands = false;
      notifyListeners();
    } catch (e) {
      _brandsError = e.toString();
      _isLoadingBrands = false;
      notifyListeners();
    }
  }

  Future<void> getBrand(int id) async {
    try {
      _selectedBrand = await _catalogService.getBrand(id);
      notifyListeners();
    } catch (e) {
      _brandsError = e.toString();
    }
  }

  // Banners
  Future<void> getBanners({String? position}) async {
    _isLoadingBanners = true;
    _bannersError = null;
    notifyListeners();

    try {
      _banners = await _catalogService.getBanners(position: position);
      _isLoadingBanners = false;
      notifyListeners();
    } catch (e) {
      _bannersError = e.toString();
      _isLoadingBanners = false;
      notifyListeners();
    }
  }

  // Filter methods
  void setCategoryFilter(String? slug) {
    _selectedCategorySlug = slug;
    notifyListeners();
  }

  void setBrandFilter(int? id) {
    _selectedBrandId = id;
    notifyListeners();
  }

  void setPriceRange(double? min, double? max) {
    _minPrice = min;
    _maxPrice = max;
    notifyListeners();
  }

  void setOrdering(String? ordering) {
    _ordering = ordering;
    notifyListeners();
  }

  void setIsNewFilter(bool? value) {
    _isNew = value;
    notifyListeners();
  }

  void setIsAvailableFilter(bool? value) {
    _isAvailable = value;
    notifyListeners();
  }

  void clearFilters() {
    _selectedCategorySlug = null;
    _selectedBrandId = null;
    _minPrice = null;
    _maxPrice = null;
    _searchQuery = null;
    _ordering = null;
    _isNew = null;
    _isAvailable = null;
    notifyListeners();
  }

  void clearSelectedProduct() {
    _selectedProduct = null;
    _similarProducts = [];
    notifyListeners();
  }

  void clearError() {
    _productsError = null;
    _categoriesError = null;
    _brandsError = null;
    _bannersError = null;
    notifyListeners();
  }
}

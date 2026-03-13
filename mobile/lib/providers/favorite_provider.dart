import 'package:flutter/foundation.dart';
import '../models/models.dart';
import '../services/services.dart';

class FavoriteProvider extends ChangeNotifier {
  final FavoriteService _favoriteService = FavoriteService();

  List<Favorite> _favorites = [];
  bool _isLoading = false;
  String? _error;
  int _favoritesCount = 0;
  final Set<int> _favoriteProductIds = {};

  List<Favorite> get favorites => _favorites;
  bool get isLoading => _isLoading;
  String? get error => _error;
  int get favoritesCount => _favoritesCount;
  Set<int> get favoriteProductIds => _favoriteProductIds;

  Future<void> getFavorites() async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      _favorites = await _favoriteService.getFavorites();
      _favoriteProductIds.clear();
      for (final favorite in _favorites) {
        _favoriteProductIds.add(favorite.product.id);
      }
      _favoritesCount = _favorites.length;
      _isLoading = false;
      notifyListeners();
    } catch (e) {
      _error = e.toString();
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<bool> addToFavorite(int productId, {String? productType}) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final favorite = await _favoriteService.addToFavorite(productId, productType: productType);
      _favorites.add(favorite);
      _favoriteProductIds.add(productId);
      _favoritesCount = _favorites.length;
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

  Future<bool> removeFromFavorite(int productId) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      await _favoriteService.removeFromFavorite(productId);
      _favorites.removeWhere((f) => f.product.id == productId);
      _favoriteProductIds.remove(productId);
      _favoritesCount = _favorites.length;
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

  Future<void> toggleFavorite(int productId, {String? productType}) async {
    if (_favoriteProductIds.contains(productId)) {
      await removeFromFavorite(productId);
    } else {
      await addToFavorite(productId, productType: productType);
    }
  }

  Future<void> checkIsFavorite(int productId) async {
    try {
      final isFavorite = await _favoriteService.checkIsFavorite(productId);
      if (isFavorite) {
        _favoriteProductIds.add(productId);
      } else {
        _favoriteProductIds.remove(productId);
      }
      notifyListeners();
    } catch (e) {
      // Silently fail
    }
  }

  Future<void> getFavoritesCount() async {
    try {
      _favoritesCount = await _favoriteService.getFavoritesCount();
      notifyListeners();
    } catch (e) {
      // Silently fail
    }
  }

  bool isFavorite(int productId) {
    return _favoriteProductIds.contains(productId);
  }

  void clearError() {
    _error = null;
    notifyListeners();
  }
}

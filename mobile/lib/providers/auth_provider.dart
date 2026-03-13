import 'package:flutter/foundation.dart';
import '../models/models.dart';
import '../services/services.dart';

class AuthProvider extends ChangeNotifier {
  final AuthService _authService = AuthService();
  final ApiClient _apiClient = ApiClient();

  User? _user;
  bool _isLoading = false;
  String? _error;
  UserStats? _userStats;

  User? get user => _user;
  bool get isLoading => _isLoading;
  String? get error => _error;
  UserStats? get userStats => _userStats;
  bool get isAuthenticated => _user != null;
  bool get isEmailVerified => _user?.isEmailVerified ?? false;

  Future<void> checkAuthStatus() async {
    if (_apiClient.isAuthenticated) {
      await getCurrentUser();
    }
  }

  Future<bool> login(String email, String password) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final response = await _authService.login(email, password);
      _user = response.user;
      if (_user?.preferredCurrency != null) {
        await _apiClient.setCurrency(_user!.preferredCurrency);
      }
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

  Future<bool> register(UserRegistration registration) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final response = await _authService.register(registration);
      _user = response.user;
      if (_user?.preferredCurrency != null) {
        await _apiClient.setCurrency(_user!.preferredCurrency);
      }
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

  Future<void> logout() async {
    _isLoading = true;
    notifyListeners();

    try {
      await _authService.logout();
      _user = null;
      _userStats = null;
      _error = null;
    } catch (e) {
      _error = e.toString();
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> getCurrentUser() async {
    try {
      _user = await _authService.getCurrentUser();
      if (_user?.preferredCurrency != null) {
        await _apiClient.setCurrency(_user!.preferredCurrency);
      }
      notifyListeners();
    } catch (e) {
      _error = e.toString();
    }
  }

  Future<bool> updateProfile(Map<String, dynamic> data) async {
    if (_user == null) return false;

    _isLoading = true;
    notifyListeners();

    try {
      final updatedUser = await _authService.updateProfile(_user!.id, data);
      _user = updatedUser;
      if (data.containsKey('currency')) {
        await _apiClient.setCurrency(updatedUser.preferredCurrency);
      }
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

  Future<bool> changePassword(String oldPassword, String newPassword, String confirmPassword) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      await _authService.changePassword(UserPasswordChange(
        oldPassword: oldPassword,
        newPassword: newPassword,
        newPasswordConfirm: confirmPassword,
      ));
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

  Future<bool> verifyEmail(String email, String code) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      await _authService.verifyEmail(email, code);
      if (_user != null) {
        _user = User(
          id: _user!.id,
          email: _user!.email,
          username: _user!.username,
          firstName: _user!.firstName,
          lastName: _user!.lastName,
          phoneNumber: _user!.phoneNumber,
          avatar: _user!.avatar,
          isEmailVerified: true,
          isPhoneVerified: _user!.isPhoneVerified,
          dateJoined: _user!.dateJoined,
          lastLogin: _user!.lastLogin,
          preferredLanguage: _user!.preferredLanguage,
          preferredCurrency: _user!.preferredCurrency,
          telegramUsername: _user!.telegramUsername,
          telegramBound: _user!.telegramBound,
        );
      }
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

  Future<bool> socialAuth(String provider, String token) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final response = await _authService.socialAuth(SocialAuth(
        provider: provider,
        accessToken: token,
      ));
      _user = response.user;
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

  Future<void> getUserStats() async {
    try {
      _userStats = await _authService.getUserStats();
      notifyListeners();
    } catch (e) {
      _error = e.toString();
    }
  }

  Future<List<UserAddress>> getAddresses() async {
    try {
      return await _authService.getAddresses();
    } catch (e) {
      _error = e.toString();
      return [];
    }
  }

  Future<UserAddress?> createAddress(UserAddress address) async {
    try {
      return await _authService.createAddress(address);
    } catch (e) {
      _error = e.toString();
      return null;
    }
  }

  Future<UserAddress?> updateAddress(String id, UserAddress address) async {
    try {
      return await _authService.updateAddress(id, address);
    } catch (e) {
      _error = e.toString();
      return null;
    }
  }

  Future<void> deleteAddress(String id) async {
    try {
      await _authService.deleteAddress(id);
    } catch (e) {
      _error = e.toString();
    }
  }

  void clearError() {
    _error = null;
    notifyListeners();
  }
}

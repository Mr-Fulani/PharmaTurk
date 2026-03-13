import 'package:dio/dio.dart';
import 'api_client.dart';
import '../models/models.dart';

class AuthService {
  final ApiClient _apiClient = ApiClient();

  Future<AuthResponse> login(String email, String password) async {
    try {
      final response = await _apiClient.dio.post(
        '/users/login/',
        data: {
          'email': email,
          'password': password,
        },
      );

      final authResponse = AuthResponse.fromJson(response.data);
      await _apiClient.saveTokens(
        authResponse.tokens.access,
        authResponse.tokens.refresh,
      );
      return authResponse;
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<AuthResponse> register(UserRegistration registration) async {
    try {
      final data = <String, dynamic>{
        'email': registration.email,
        'username': registration.username,
        'password': registration.password,
        'password_confirm': registration.passwordConfirm,
        if (registration.firstName != null && registration.firstName!.isNotEmpty)
          'first_name': registration.firstName,
        if (registration.lastName != null && registration.lastName!.isNotEmpty)
          'last_name': registration.lastName,
        if (registration.phoneNumber != null && registration.phoneNumber!.isNotEmpty)
          'phone_number': registration.phoneNumber,
      };
      final response = await _apiClient.dio.post(
        '/users/register/',
        data: data,
      );

      final authResponse = AuthResponse.fromJson(response.data);
      await _apiClient.saveTokens(
        authResponse.tokens.access,
        authResponse.tokens.refresh,
      );
      return authResponse;
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<void> logout() async {
    try {
      await _apiClient.dio.post('/users/logout/');
      await _apiClient.clearTokens();
    } catch (e) {
      await _apiClient.clearTokens();
      throw _handleError(e);
    }
  }

  Future<User> getCurrentUser() async {
    try {
      final response = await _apiClient.dio.get('/users/profile/me');
      return User.fromJson(response.data);
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<User> updateProfile(int userId, Map<String, dynamic> data) async {
    try {
      final response = await _apiClient.dio.patch(
        '/users/profile/$userId',
        data: data,
      );
      return User.fromJson(response.data);
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<void> changePassword(UserPasswordChange passwordChange) async {
    try {
      await _apiClient.dio.post(
        '/users/change-password/',
        data: passwordChange.toJson(),
      );
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<void> verifyEmail(String email, String code) async {
    try {
      await _apiClient.dio.post(
        '/users/verify-email/',
        data: {
          'email': email,
          'code': code,
        },
      );
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<AuthResponse> socialAuth(SocialAuth socialAuth) async {
    try {
      final response = await _apiClient.dio.post(
        '/users/social-auth/',
        data: socialAuth.toJson(),
      );

      final authResponse = AuthResponse.fromJson(response.data);
      await _apiClient.saveTokens(
        authResponse.tokens.access,
        authResponse.tokens.refresh,
      );
      return authResponse;
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<AuthResponse> telegramLogin(Map<String, dynamic> telegramData) async {
    try {
      final response = await _apiClient.dio.post(
        '/users/telegram/login/',
        data: telegramData,
      );

      final authResponse = AuthResponse.fromJson(response.data);
      await _apiClient.saveTokens(
        authResponse.tokens.access,
        authResponse.tokens.refresh,
      );
      return authResponse;
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<void> sendSMSCode(String phoneNumber) async {
    try {
      await _apiClient.dio.post(
        '/users/sms/send-code/',
        data: {'phone_number': phoneNumber},
      );
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<AuthResponse> verifySMSCode(String phoneNumber, String code) async {
    try {
      final response = await _apiClient.dio.post(
        '/users/sms/verify/',
        data: {
          'phone_number': phoneNumber,
          'code': code,
        },
      );

      final authResponse = AuthResponse.fromJson(response.data);
      await _apiClient.saveTokens(
        authResponse.tokens.access,
        authResponse.tokens.refresh,
      );
      return authResponse;
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<UserStats> getUserStats() async {
    try {
      final response = await _apiClient.dio.get('/users/stats/');
      return UserStats.fromJson(response.data);
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<List<UserAddress>> getAddresses() async {
    try {
      final response = await _apiClient.dio.get('/users/addresses');
      return (response.data as List)
          .map((json) => UserAddress.fromJson(json))
          .toList();
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<UserAddress> createAddress(UserAddress address) async {
    try {
      final response = await _apiClient.dio.post(
        '/users/addresses',
        data: address.toJson(),
      );
      return UserAddress.fromJson(response.data);
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<UserAddress> updateAddress(String id, UserAddress address) async {
    try {
      final response = await _apiClient.dio.put(
        '/users/addresses/$id',
        data: address.toJson(),
      );
      return UserAddress.fromJson(response.data);
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<void> deleteAddress(String id) async {
    try {
      await _apiClient.dio.delete('/users/addresses/$id');
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<String> getTelegramBindLink() async {
    try {
      final response = await _apiClient.dio.get('/users/profile/telegram-bind-link');
      return response.data['link'];
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<User> uploadAvatar(String filePath) async {
    try {
      final formData = FormData.fromMap({
        'avatar': await MultipartFile.fromFile(filePath),
      });
      final response = await _apiClient.dio.post(
        '/users/profile/upload-avatar',
        data: formData,
      );
      return User.fromJson(response.data);
    } catch (e) {
      throw _handleError(e);
    }
  }

  Future<PublicUserProfile> getPublicProfile({String? username, int? testimonialId}) async {
    try {
      final queryParams = <String, dynamic>{};
      if (username != null) queryParams['username'] = username;
      if (testimonialId != null) queryParams['testimonial_id'] = testimonialId;

      final response = await _apiClient.dio.get(
        '/users/public-profile',
        queryParameters: queryParams.isNotEmpty ? queryParams : null,
      );
      return PublicUserProfile.fromJson(response.data);
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
          if (data.containsKey('error')) {
            return data['error'].toString();
          }
          final errors = <String>[];
          data.forEach((key, value) {
            if (value is List) {
              errors.add('$key: ${value.join(', ')}');
            } else {
              errors.add('$key: $value');
            }
          });
          if (errors.isNotEmpty) {
            return errors.join('\n');
          }
        }
        return 'Ошибка сервера: ${error.response!.statusCode}';
      }
      return 'Ошибка соединения: ${error.message}';
    }
    return 'Неизвестная ошибка: $error';
  }
}

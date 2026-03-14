import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../constants/env.dart';

class ApiClient {
  static final ApiClient _instance = ApiClient._internal();
  factory ApiClient() => _instance;
  ApiClient._internal();

  late Dio _dio;
  String? _accessToken;
  String? _refreshToken;
  String? _sessionKey;
  String? _currency;
  String? _language;
  Future<bool>? _refreshFuture;

  static const String apiPrefix = '/api';

  Dio get dio => _dio;

  Future<void> initialize() async {
    _dio = Dio(BaseOptions(
      baseUrl: '${Env.apiBaseUrl}$apiPrefix/',
      connectTimeout: const Duration(seconds: 30),
      receiveTimeout: const Duration(seconds: 30),
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
    ));

    await _loadTokens();
    _setupInterceptors();
  }

  void _setupInterceptors() {
    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) async {
        if (_accessToken != null) {
          options.headers['Authorization'] = 'Bearer $_accessToken';
        }
        if (_sessionKey != null) {
          options.headers['X-Cart-Session'] = _sessionKey;
        }
        if (_currency != null) {
          options.headers['X-Currency'] = _currency!;
        }
        if (_language != null) {
          options.headers['X-Language'] = _language!;
        }
        if (kDebugMode) {
          final safeHeaders = Map<String, dynamic>.from(options.headers);
          if (safeHeaders.containsKey('Authorization')) {
            safeHeaders['Authorization'] = 'Bearer ***';
          }
          print('REQUEST: ${options.method} ${options.path}');
          print('HEADERS: $safeHeaders');
        }
        return handler.next(options);
      },
      onResponse: (response, handler) {
        if (kDebugMode) {
          print('RESPONSE: ${response.statusCode} ${response.requestOptions.path}');
        }
        return handler.next(response);
      },
      onError: (error, handler) async {
        if (kDebugMode) {
          print('ERROR: ${error.response?.statusCode} ${error.requestOptions.path}');
          print('ERROR BODY: ${error.response?.data}');
        }

        if (error.response?.statusCode == 401) {
          final path = error.requestOptions.path;
          if (path.contains('token/refresh')) {
            _refreshFuture = null;
            await clearTokens();
            return handler.next(error);
          }
          _refreshFuture ??= _refreshAccessToken();
          final refreshed = await _refreshFuture!;
          if (!refreshed) _refreshFuture = null;
          if (refreshed) {
            final opts = error.requestOptions;
            opts.headers['Authorization'] = 'Bearer $_accessToken';
            final cloneReq = await _dio.fetch(opts);
            return handler.resolve(cloneReq);
          }
        }
        return handler.next(error);
      },
    ));

    // LogInterceptor не добавляем: логирует тела запросов (в т.ч. пароли при login)
  }

  Future<void> _loadTokens() async {
    final prefs = await SharedPreferences.getInstance();
    _accessToken = prefs.getString('access_token');
    _refreshToken = prefs.getString('refresh_token');
    _sessionKey = prefs.getString('session_key');
    _currency = prefs.getString('currency') ?? 'RUB';
    _language = prefs.getString('app_locale');
    if (prefs.getString('currency') == null) {
      await prefs.setString('currency', _currency!);
    }
  }

  void setLanguage(String? languageCode) {
    _language = (languageCode == 'ru' || languageCode == 'en') ? languageCode : null;
  }

  Future<void> saveTokens(String access, String refresh) async {
    _accessToken = access;
    _refreshToken = refresh;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('access_token', access);
    await prefs.setString('refresh_token', refresh);
  }

  Future<void> saveSessionKey(String sessionKey) async {
    _sessionKey = sessionKey;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('session_key', sessionKey);
  }

  Future<void> clearTokens() async {
    _accessToken = null;
    _refreshToken = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('access_token');
    await prefs.remove('refresh_token');
  }

  Future<bool> _refreshAccessToken() async {
    if (_refreshToken == null) return false;
    try {
      final response = await _dio.post(
        '/users/token/refresh/',
        data: {'refresh': _refreshToken},
      );
      _accessToken = response.data['access'];
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('access_token', _accessToken!);
      return true;
    } catch (e) {
      await clearTokens();
      return false;
    }
  }

  Future<void> setCurrency(String? currency) async {
    _currency = currency;
    final prefs = await SharedPreferences.getInstance();
    if (currency != null) {
      await prefs.setString('currency', currency);
    } else {
      await prefs.remove('currency');
    }
  }

  String? get currency => _currency;

  bool get isAuthenticated => _accessToken != null;
  String? get accessToken => _accessToken;
  String? get sessionKey => _sessionKey;
}

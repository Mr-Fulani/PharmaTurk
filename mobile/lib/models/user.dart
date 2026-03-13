import 'package:json_annotation/json_annotation.dart';

part 'user.g.dart';

@JsonSerializable()
class User {
  final int id;
  final String email;
  final String username;
  @JsonKey(name: 'first_name')
  final String? firstName;
  @JsonKey(name: 'last_name')
  final String? lastName;
  @JsonKey(name: 'phone_number')
  final String? phoneNumber;
  @JsonKey(name: 'avatar_url')
  final String? avatar;
  @JsonKey(name: 'is_verified')
  final bool isEmailVerified;
  @JsonKey(name: 'is_phone_verified', defaultValue: false)
  final bool isPhoneVerified;
  @JsonKey(name: 'date_joined')
  final DateTime dateJoined;
  @JsonKey(name: 'last_login')
  final DateTime? lastLogin;
  @JsonKey(name: 'language')
  final String? preferredLanguage;
  @JsonKey(name: 'currency')
  final String? preferredCurrency;
  @JsonKey(name: 'telegram_username')
  final String? telegramUsername;
  @JsonKey(name: 'telegram_id', fromJson: _telegramBoundFromJson)
  final bool telegramBound;

  static bool _telegramBoundFromJson(dynamic v) =>
      v != null && v.toString().trim().isNotEmpty;

  User({
    required this.id,
    required this.email,
    required this.username,
    this.firstName,
    this.lastName,
    this.phoneNumber,
    this.avatar,
    required this.isEmailVerified,
    required this.isPhoneVerified,
    required this.dateJoined,
    this.lastLogin,
    this.preferredLanguage,
    this.preferredCurrency,
    this.telegramUsername,
    required this.telegramBound,
  });

  factory User.fromJson(Map<String, dynamic> json) => _$UserFromJson(json);
  Map<String, dynamic> toJson() => _$UserToJson(this);

  String get fullName {
    if (firstName != null && lastName != null) {
      return '$firstName $lastName';
    } else if (firstName != null) {
      return firstName!;
    } else if (lastName != null) {
      return lastName!;
    }
    return username;
  }
}

@JsonSerializable(createFactory: false, createToJson: false)
class UserAddress {
  final int id;
  final String name;
  final String? recipientName;
  final String? phone;
  final String addressText;
  final String? city;
  final String? postalCode;
  final String? country;
  final String addressType;
  final bool isDefault;
  final bool isActive;
  final DateTime createdAt;
  final DateTime updatedAt;

  UserAddress({
    required this.id,
    required this.name,
    this.recipientName,
    this.phone,
    required this.addressText,
    this.city,
    this.postalCode,
    this.country,
    required this.addressType,
    required this.isDefault,
    required this.isActive,
    required this.createdAt,
    required this.updatedAt,
  });

  /// Парсинг из snake_case API (contact_name, contact_phone, street, house, apartment и т.д.)
  factory UserAddress.fromJson(Map<String, dynamic> json) {
    final contactName = json['contact_name'] as String? ?? '';
    final street = json['street'] as String? ?? '';
    final house = json['house'] as String? ?? '';
    final apartment = json['apartment'] as String? ?? '';
    final city = json['city'] as String? ?? '';
    final country = json['country'] as String? ?? '';
    final parts = <String>[];
    if (street.isNotEmpty) parts.add(street);
    if (house.isNotEmpty) parts.add('д. $house');
    if (apartment.isNotEmpty) parts.add('кв. $apartment');
    final addrPart = parts.join(', ');
    final locParts = <String>[];
    if (city.isNotEmpty) locParts.add(city);
    if (country.isNotEmpty) locParts.add(country);
    final locPart = locParts.join(', ');
    final addressText = [addrPart, locPart].where((s) => s.isNotEmpty).join(', ');
    return UserAddress(
      id: (json['id'] as num).toInt(),
      name: contactName.isNotEmpty ? contactName : (json['name'] as String? ?? 'Адрес'),
      recipientName: contactName.isNotEmpty ? contactName : json['recipientName'] as String?,
      phone: json['contact_phone'] as String? ?? json['phone'] as String?,
      addressText: addressText.isNotEmpty ? addressText : (json['addressText'] as String? ?? ''),
      city: city.isNotEmpty ? city : json['city'] as String?,
      postalCode: json['postal_code'] as String? ?? json['postalCode'] as String?,
      country: country.isNotEmpty ? country : json['country'] as String?,
      addressType: json['address_type'] as String? ?? json['addressType'] as String? ?? 'home',
      isDefault: json['is_default'] as bool? ?? json['isDefault'] as bool? ?? false,
      isActive: json['is_active'] as bool? ?? json['isActive'] as bool? ?? true,
      createdAt: DateTime.parse(json['created_at'] as String? ?? json['createdAt'] as String? ?? DateTime.now().toIso8601String()),
      updatedAt: DateTime.parse(json['updated_at'] as String? ?? json['updatedAt'] as String? ?? DateTime.now().toIso8601String()),
    );
  }

  /// Отправка в API в snake_case (contact_name, contact_phone, street, house, apartment)
  Map<String, dynamic> toJson() {
    final parts = addressText.split(',').map((s) => s.trim()).where((s) => s.isNotEmpty).toList();
    String street = addressText;
    String house = '1';
    String apartment = '';
    if (parts.length >= 2) {
      street = parts.first.replaceFirst(RegExp(r'^д\.\s*'), '');
      house = parts[1].replaceFirst(RegExp(r'^д\.\s*'), '').replaceFirst(RegExp(r'^кв\.\s*'), '');
      if (parts.length >= 3) apartment = parts[2].replaceFirst(RegExp(r'^кв\.\s*'), '');
    } else if (parts.length == 1) {
      street = parts.first;
    }
    return {
      if (id > 0) 'id': id,
      'address_type': addressType,
      'contact_name': recipientName ?? name,
      'contact_phone': phone ?? '',
      'country': country ?? 'Турция',
      'city': city ?? '',
      'postal_code': postalCode ?? '',
      'street': street,
      'house': house,
      'apartment': apartment,
      'is_default': isDefault,
      'is_active': isActive,
    };
  }
}

@JsonSerializable(fieldRename: FieldRename.snake)
class UserRegistration {
  final String email;
  final String username;
  final String password;
  final String passwordConfirm;
  final String? firstName;
  final String? lastName;
  final String? phoneNumber;

  UserRegistration({
    required this.email,
    required this.username,
    required this.password,
    required this.passwordConfirm,
    this.firstName,
    this.lastName,
    this.phoneNumber,
  });

  factory UserRegistration.fromJson(Map<String, dynamic> json) => _$UserRegistrationFromJson(json);
  Map<String, dynamic> toJson() => _$UserRegistrationToJson(this);
}

@JsonSerializable()
class UserLogin {
  final String email;
  final String password;

  UserLogin({
    required this.email,
    required this.password,
  });

  factory UserLogin.fromJson(Map<String, dynamic> json) => _$UserLoginFromJson(json);
  Map<String, dynamic> toJson() => _$UserLoginToJson(this);
}

@JsonSerializable()
class AuthResponse {
  final User user;
  final Tokens tokens;
  final String message;

  AuthResponse({
    required this.user,
    required this.tokens,
    required this.message,
  });

  factory AuthResponse.fromJson(Map<String, dynamic> json) => _$AuthResponseFromJson(json);
  Map<String, dynamic> toJson() => _$AuthResponseToJson(this);
}

@JsonSerializable()
class Tokens {
  final String access;
  final String refresh;

  Tokens({
    required this.access,
    required this.refresh,
  });

  factory Tokens.fromJson(Map<String, dynamic> json) => _$TokensFromJson(json);
  Map<String, dynamic> toJson() => _$TokensToJson(this);
}

@JsonSerializable()
class TokenRefresh {
  final String refresh;
  String? access;

  TokenRefresh({
    required this.refresh,
    this.access,
  });

  factory TokenRefresh.fromJson(Map<String, dynamic> json) => _$TokenRefreshFromJson(json);
  Map<String, dynamic> toJson() => _$TokenRefreshToJson(this);
}

@JsonSerializable()
class UserPasswordChange {
  final String oldPassword;
  final String newPassword;
  final String newPasswordConfirm;

  UserPasswordChange({
    required this.oldPassword,
    required this.newPassword,
    required this.newPasswordConfirm,
  });

  factory UserPasswordChange.fromJson(Map<String, dynamic> json) => _$UserPasswordChangeFromJson(json);
  Map<String, dynamic> toJson() => _$UserPasswordChangeToJson(this);
}

@JsonSerializable()
class UserEmailVerification {
  final String email;
  final String code;

  UserEmailVerification({
    required this.email,
    required this.code,
  });

  factory UserEmailVerification.fromJson(Map<String, dynamic> json) => _$UserEmailVerificationFromJson(json);
  Map<String, dynamic> toJson() => _$UserEmailVerificationToJson(this);
}

@JsonSerializable()
class UserStats {
  final int ordersCount;
  final String totalSpent;
  final int favoritesCount;
  final int reviewsCount;
  final DateTime? lastOrderDate;

  UserStats({
    required this.ordersCount,
    required this.totalSpent,
    required this.favoritesCount,
    required this.reviewsCount,
    this.lastOrderDate,
  });

  factory UserStats.fromJson(Map<String, dynamic> json) => _$UserStatsFromJson(json);
  Map<String, dynamic> toJson() => _$UserStatsToJson(this);
}

@JsonSerializable()
class PublicUserProfile {
  final int id;
  final String username;
  final String? firstName;
  final String? lastName;
  final String? avatar;
  final DateTime dateJoined;

  PublicUserProfile({
    required this.id,
    required this.username,
    this.firstName,
    this.lastName,
    this.avatar,
    required this.dateJoined,
  });

  factory PublicUserProfile.fromJson(Map<String, dynamic> json) => _$PublicUserProfileFromJson(json);
  Map<String, dynamic> toJson() => _$PublicUserProfileToJson(this);

  String get displayName {
    if (firstName != null && lastName != null) {
      return '$firstName $lastName';
    } else if (firstName != null) {
      return firstName!;
    }
    return username;
  }
}

@JsonSerializable()
class SocialAuth {
  final String provider;
  final String? credential;
  final String? accessToken;
  final String? vkUserId;

  SocialAuth({
    required this.provider,
    this.credential,
    this.accessToken,
    this.vkUserId,
  });

  factory SocialAuth.fromJson(Map<String, dynamic> json) => _$SocialAuthFromJson(json);
  Map<String, dynamic> toJson() => _$SocialAuthToJson(this);
}

@JsonSerializable()
class SMSSendCode {
  final String phoneNumber;

  SMSSendCode({
    required this.phoneNumber,
  });

  factory SMSSendCode.fromJson(Map<String, dynamic> json) => _$SMSSendCodeFromJson(json);
  Map<String, dynamic> toJson() => _$SMSSendCodeToJson(this);
}

@JsonSerializable()
class SMSVerifyCode {
  final String phoneNumber;
  final String code;

  SMSVerifyCode({
    required this.phoneNumber,
    required this.code,
  });

  factory SMSVerifyCode.fromJson(Map<String, dynamic> json) => _$SMSVerifyCodeFromJson(json);
  Map<String, dynamic> toJson() => _$SMSVerifyCodeToJson(this);
}

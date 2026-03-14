/// Модель настроек футера (контакты, соцсети, URL сайта).
class FooterSettings {
  final String? phone;
  final String? email;
  final String? location;
  final String? telegramUrl;
  final String? whatsappUrl;
  final String? vkUrl;
  final String? instagramUrl;
  final String? cryptoPaymentText;
  final String siteUrl;

  const FooterSettings({
    this.phone,
    this.email,
    this.location,
    this.telegramUrl,
    this.whatsappUrl,
    this.vkUrl,
    this.instagramUrl,
    this.cryptoPaymentText,
    this.siteUrl = '',
  });

  factory FooterSettings.fromJson(Map<String, dynamic> json) {
    return FooterSettings(
      phone: json['phone'] as String?,
      email: json['email'] as String?,
      location: json['location'] as String?,
      telegramUrl: json['telegram_url'] as String?,
      whatsappUrl: json['whatsapp_url'] as String?,
      vkUrl: json['vk_url'] as String?,
      instagramUrl: json['instagram_url'] as String?,
      cryptoPaymentText: json['crypto_payment_text'] as String?,
      siteUrl: (json['site_url'] as String?)?.replaceAll(RegExp(r'/+$'), '') ?? '',
    );
  }

  String get privacyUrl => '$siteUrl/privacy';
  /// Условия использования. Пока ведёт на политику (отдельная страница /terms может быть добавлена).
  String get termsUrl => '$siteUrl/privacy';
  String get deliveryUrl => '$siteUrl/delivery';
  String get returnsUrl => '$siteUrl/returns';

  bool get hasSocialLinks =>
      (telegramUrl?.isNotEmpty ?? false) ||
      (whatsappUrl?.isNotEmpty ?? false) ||
      (vkUrl?.isNotEmpty ?? false) ||
      (instagramUrl?.isNotEmpty ?? false);

  bool get hasEmail => email != null && email!.isNotEmpty;
}

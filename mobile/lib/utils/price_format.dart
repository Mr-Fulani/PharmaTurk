/// Проверяет, что старая цена задана и больше нуля (не показывать "0 ₽").
bool hasValidOldPrice(String? oldPrice) {
  if (oldPrice == null || oldPrice.isEmpty) return false;
  final v = double.tryParse(oldPrice.replaceAll(',', '.'));
  return v != null && v > 0;
}

/// Форматирует цену: убирает лишние нули после запятой.
/// Примеры: "690.0000" → "690", "12.50" → "12.50", "0.00" → "0"
String formatPrice(String? price) {
  if (price == null || price.isEmpty) return '0';
  final v = double.tryParse(price.replaceAll(',', '.'));
  if (v == null) return price;
  if (v == v.truncateToDouble()) return v.toInt().toString();
  return v.toStringAsFixed(2).replaceAll(RegExp(r'0+$'), '').replaceAll(RegExp(r'\.$'), '');
}

/// Форматирует цену с валютой: "690.0000" + "RUB" → "690 ₽" или "690 RUB"
String formatPriceWithCurrency(String? price, String? currency) {
  final formatted = formatPrice(price);
  if (currency == null || currency.isEmpty) return formatted;
  final symbol = _currencySymbol(currency);
  return symbol != null ? '$formatted $symbol' : '$formatted $currency';
}

String? _currencySymbol(String code) {
  switch (code.toUpperCase()) {
    case 'RUB':
      return '₽';
    case 'USD':
      return '\$';
    case 'EUR':
      return '€';
    case 'TRY':
      return '₺';
    default:
      return null;
  }
}

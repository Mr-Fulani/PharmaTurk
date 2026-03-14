import 'package:flutter/material.dart';
import '../models/models.dart';
import '../l10n/app_localizations.dart';
import 'main_screen.dart';

class OrderSuccessScreen extends StatelessWidget {
  final Order order;

  const OrderSuccessScreen({
    super.key,
    required this.order,
  });

  @override
  Widget build(BuildContext context) {
    return WillPopScope(
      onWillPop: () async => false,
      child: Scaffold(
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(24.0),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Spacer(),
                Container(
                  width: 120,
                  height: 120,
                  decoration: BoxDecoration(
                    color: Colors.green.withOpacity(0.1),
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(
                    Icons.check_circle,
                    size: 80,
                    color: Colors.green,
                  ),
                ),
                const SizedBox(height: 32),
                Text(
                  context.tr('order_placed'),
                  style: TextStyle(
                    fontSize: 28,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 16),
                Text(
                  '${context.tr('order_receipt')}${order.number}',
                  style: const TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  '${context.tr('order_amount')}: ${order.totalAmount} ${order.currency}',
                  style: const TextStyle(
                    fontSize: 20,
                    fontWeight: FontWeight.bold,
                    color: Colors.teal,
                  ),
                ),
                const SizedBox(height: 24),
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: Colors.grey[100],
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      _buildInfoRow(context.tr('status'), order.statusDisplay),
                      const SizedBox(height: 8),
                      _buildInfoRow(
                        context.tr('date'),
                        '${order.createdAt.day}.${order.createdAt.month}.${order.createdAt.year}',
                      ),
                      const SizedBox(height: 8),
                      _buildInfoRow(context.tr('items_count'), '${order.items.length}'),
                      if (order.shippingMethod != null && order.shippingMethod!.isNotEmpty) ...[
                        const SizedBox(height: 8),
                        _buildInfoRow(context.tr('delivery'), _shippingDisplay(context, order.shippingMethod!)),
                      ],
                      if (order.shippingAmount != '0' && order.shippingAmount != '0.00') ...[
                        const SizedBox(height: 8),
                        _buildInfoRow(context.tr('shipping_cost'), '${order.shippingAmount} ${order.currency}'),
                      ],
                      if (order.shippingAddressText != null && order.shippingAddressText!.isNotEmpty) ...[
                        const SizedBox(height: 8),
                        _buildInfoRow(context.tr('delivery_address'), order.shippingAddressText!),
                      ],
                      if (order.paymentMethod != null && order.paymentMethod!.isNotEmpty) ...[
                        const SizedBox(height: 8),
                        _buildInfoRow(context.tr('payment_method'), _paymentDisplay(context, order.paymentMethod!)),
                      ],
                      if (order.subtotalAmount != '0' && order.subtotalAmount != '0.00') ...[
                        const SizedBox(height: 8),
                        _buildInfoRow(context.tr('subtotal'), '${order.subtotalAmount} ${order.currency}'),
                      ],
                      if (order.discountAmount != '0' && order.discountAmount != '0.00') ...[
                        const SizedBox(height: 8),
                        _buildInfoRow(context.tr('discount'), '-${order.discountAmount} ${order.currency}'),
                      ],
                    ],
                  ),
                ),
                const Spacer(),
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton(
                    onPressed: () {
                      Navigator.pushAndRemoveUntil(
                        context,
                        MaterialPageRoute(
                          builder: (_) => const MainScreen(initialIndex: 2),
                        ),
                        (route) => false,
                      );
                    },
                    style: ElevatedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 16),
                      backgroundColor: Colors.teal,
                    ),
                    child: Text(
                      context.tr('orders'),
                      style: TextStyle(fontSize: 16),
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton(
                    onPressed: () {
                      Navigator.pushAndRemoveUntil(
                        context,
                        MaterialPageRoute(
                          builder: (_) => const MainScreen(),
                        ),
                        (route) => false,
                      );
                    },
                    style: OutlinedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 16),
                    ),
                    child: Text(
                      context.tr('go_home'),
                      style: TextStyle(fontSize: 16),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  String _shippingDisplay(BuildContext context, String method) {
    final m = method.toLowerCase();
    if (m.contains('air') || m.contains('авиа')) return context.tr('shipping_air');
    if (m.contains('sea') || m.contains('мор')) return context.tr('shipping_sea');
    if (m.contains('ground') || m.contains('назем')) return context.tr('shipping_ground');
    return method;
  }

  String _paymentDisplay(BuildContext context, String method) {
    final m = method.toLowerCase();
    if (m == 'cod') return context.tr('payment_cod');
    if (m == 'card') return context.tr('payment_card');
    if (m == 'crypto') return context.tr('payment_crypto');
    return method;
  }

  Widget _buildInfoRow(String label, String value) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(
          label,
          style: TextStyle(
            color: Colors.grey[600],
          ),
        ),
        Text(
          value,
          style: const TextStyle(
            fontWeight: FontWeight.w500,
          ),
        ),
      ],
    );
  }
}

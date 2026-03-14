import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/providers.dart';
import '../l10n/app_localizations.dart';
import '../models/models.dart';

class OrderDetailScreen extends StatefulWidget {
  final String orderId;

  const OrderDetailScreen({
    super.key,
    required this.orderId,
  });

  @override
  State<OrderDetailScreen> createState() => _OrderDetailScreenState();
}

class _OrderDetailScreenState extends State<OrderDetailScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<OrderProvider>().getOrder(widget.orderId);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(context.tr('order_details')),
      ),
      body: Consumer<OrderProvider>(
        builder: (context, provider, child) {
          if (provider.isLoading) {
            return const Center(child: CircularProgressIndicator());
          }

          if (provider.error != null) {
            return Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(provider.error!),
                  const SizedBox(height: 16),
                  ElevatedButton(
                    onPressed: () => provider.getOrder(widget.orderId),
                    child: Text(context.tr('retry')),
                  ),
                ],
              ),
            );
          }

          final order = provider.selectedOrder;
          if (order == null) {
            return Center(child: Text(context.tr('order_not_found')));
          }

          return SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _buildOrderHeader(context, order),
                const SizedBox(height: 24),
                _buildStatusSection(context, order),
                const SizedBox(height: 24),
                _buildItemsSection(context, order),
                const SizedBox(height: 24),
                _buildDeliverySection(context, order),
                const SizedBox(height: 24),
                _buildPaymentSection(context, order),
                const SizedBox(height: 24),
                _buildTotalSection(context, order),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _buildOrderHeader(BuildContext context, Order order) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  '${context.tr('order_number')}${order.number}',
                  style: const TextStyle(
                    fontSize: 20,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                _buildStatusBadge(context, order.status),
              ],
            ),
            const SizedBox(height: 12),
            Text(
              '${context.tr('created')}: ${order.createdAt.day}.${order.createdAt.month}.${order.createdAt.year}',
              style: TextStyle(color: Colors.grey[600]),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildStatusSection(BuildContext context, Order order) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              context.tr('order_status'),
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 16),
            _buildStatusTimeline(context, order.status),
          ],
        ),
      ),
    );
  }

  Widget _buildStatusTimeline(BuildContext context, String currentStatus) {
    final statuses = [
      {'key': 'new', 'label': context.tr('status_new')},
      {'key': 'processing', 'label': context.tr('status_processing')},
      {'key': 'shipped', 'label': context.tr('status_shipped')},
      {'key': 'delivered', 'label': context.tr('status_delivered')},
    ];

    final currentIndex = statuses.indexWhere((s) => s['key'] == currentStatus);

    return Column(
      children: statuses.asMap().entries.map((entry) {
        final index = entry.key;
        final status = entry.value;
        final isActive = index <= currentIndex;
        final isCurrent = index == currentIndex;

        return Row(
          children: [
            Container(
              width: 24,
              height: 24,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: isActive ? Colors.teal : Colors.grey[300],
                border: isCurrent
                    ? Border.all(color: Colors.teal, width: 3)
                    : null,
              ),
              child: isActive
                  ? const Icon(Icons.check, size: 16, color: Colors.white)
                  : null,
            ),
            if (index < statuses.length - 1)
              Container(
                width: 2,
                height: 30,
                color: index < currentIndex ? Colors.teal : Colors.grey[300],
                margin: const EdgeInsets.only(left: 11),
              ),
            const SizedBox(width: 12),
            Text(
              status['label']!,
              style: TextStyle(
                fontWeight: isCurrent ? FontWeight.bold : FontWeight.normal,
                color: isActive ? Colors.black : Colors.grey,
              ),
            ),
          ],
        );
      }).toList(),
    );
  }

  Widget _buildItemsSection(BuildContext context, Order order) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              context.tr('items'),
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 16),
            ...order.items.map((item) {
              return Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            item.productName,
                            style: const TextStyle(fontWeight: FontWeight.w500),
                          ),
                          Text(
                            '${item.quantity} шт.',
                            style: TextStyle(
                              color: Colors.grey[600],
                              fontSize: 12,
                            ),
                          ),
                        ],
                      ),
                    ),
                    Text(
                      '${item.total} ${order.currency}',
                      style: const TextStyle(fontWeight: FontWeight.bold),
                    ),
                  ],
                ),
              );
            }),
          ],
        ),
      ),
    );
  }

  Widget _buildDeliverySection(BuildContext context, Order order) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              context.tr('delivery'),
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 16),
            if (order.shippingMethod != null && order.shippingMethod!.isNotEmpty)
              _buildInfoRow(context.tr('shipping_method'), _getShippingMethodText(context, order.shippingMethod!)),
            if (order.contactName != null)
              _buildInfoRow(context.tr('recipient'), order.contactName!),
            if (order.contactPhone != null)
              _buildInfoRow(context.tr('phone'), order.contactPhone!),
            if (order.shippingAddressText != null && order.shippingAddressText!.isNotEmpty)
              _buildInfoRow(context.tr('address'), order.shippingAddressText!),
          ],
        ),
      ),
    );
  }

  String _getShippingMethodText(BuildContext context, String method) {
    final m = method.toLowerCase();
    if (m.contains('air') || m.contains('авиа')) return context.tr('shipping_air');
    if (m.contains('sea') || m.contains('мор')) return context.tr('shipping_sea');
    if (m.contains('ground') || m.contains('назем')) return context.tr('shipping_ground');
    if (m.contains('pickup') || m.contains('самовывоз')) return context.tr('shipping_pickup');
    return method;
  }

  Widget _buildPaymentSection(BuildContext context, Order order) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Оплата',
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 16),
            _buildInfoRow(
              context.tr('payment_method'),
              _getPaymentMethodText(context, order.paymentMethod),
            ),
            _buildInfoRow(context.tr('status'), context.tr('paid')),
          ],
        ),
      ),
    );
  }

  Widget _buildTotalSection(BuildContext context, Order order) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            _buildTotalRow(context.tr('items'), '${order.subtotalAmount} ${order.currency}'),
            if (order.discountAmount != '0.00')
              _buildTotalRow(
                context.tr('discount'),
                '-${order.discountAmount} ${order.currency}',
                valueColor: Colors.green,
              ),
            _buildTotalRow(
              context.tr('delivery'),
              order.shippingAmount == '0.00'
                  ? context.tr('free')
                  : '${order.shippingAmount} ${order.currency}',
            ),
            const Divider(height: 24),
            _buildTotalRow(
              context.tr('total'),
              '${order.totalAmount} ${order.currency}',
              isBold: true,
              valueSize: 20,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildInfoRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            flex: 2,
            child: Text(
              label,
              style: TextStyle(color: Colors.grey[600]),
            ),
          ),
          Expanded(
            flex: 3,
            child: Text(
              value,
              style: const TextStyle(fontWeight: FontWeight.w500),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTotalRow(
    String label,
    String value, {
    bool isBold = false,
    double valueSize = 16,
    Color? valueColor,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            label,
            style: TextStyle(
              fontWeight: isBold ? FontWeight.bold : FontWeight.normal,
            ),
          ),
          Text(
            value,
            style: TextStyle(
              fontSize: valueSize,
              fontWeight: isBold ? FontWeight.bold : FontWeight.normal,
              color: valueColor,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildStatusBadge(BuildContext context, String status) {
    Color color;
    switch (status) {
      case 'new':
        color = Colors.blue;
        break;
      case 'processing':
        color = Colors.orange;
        break;
      case 'shipped':
        color = Colors.purple;
        break;
      case 'delivered':
        color = Colors.green;
        break;
      case 'cancelled':
        color = Colors.red;
        break;
      default:
        color = Colors.grey;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: color.withOpacity(0.1),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(
        _getStatusText(context, status),
        style: TextStyle(
          color: color,
          fontSize: 12,
          fontWeight: FontWeight.w500,
        ),
      ),
    );
  }

  String _getStatusText(BuildContext context, String status) {
    switch (status) {
      case 'new':
        return context.tr('status_new');
      case 'processing':
        return context.tr('status_processing');
      case 'shipped':
        return context.tr('status_shipped');
      case 'delivered':
        return context.tr('status_delivered');
      case 'cancelled':
        return context.tr('status_cancelled');
      case 'refunded':
        return context.tr('status_refunded');
      default:
        return status;
    }
  }

  String _getPaymentMethodText(BuildContext context, String? method) {
    if (method == null || method.isEmpty) return context.tr('payment_not_specified');
    switch (method.toLowerCase()) {
      case 'cod':
        return context.tr('payment_cod');
      case 'card':
        return context.tr('payment_card');
      case 'cash':
        return context.tr('payment_cod'); // fallback
      case 'crypto':
        return context.tr('payment_crypto');
      default:
        return method;
    }
  }
}

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/providers.dart';
import '../l10n/app_localizations.dart';
import 'order_success_screen.dart';

class CheckoutScreen extends StatefulWidget {
  const CheckoutScreen({super.key});

  @override
  State<CheckoutScreen> createState() => _CheckoutScreenState();
}

class _CheckoutScreenState extends State<CheckoutScreen> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _phoneController = TextEditingController();
  final _emailController = TextEditingController();
  final _addressController = TextEditingController();
  final _commentController = TextEditingController();

  String _paymentMethod = 'cod';
  String _shippingMethod = 'ground';

  List<Map<String, dynamic>> _getPaymentMethods(BuildContext context) => [
    {'value': 'cod', 'label': context.tr('payment_cod'), 'icon': Icons.money},
    {'value': 'card', 'label': context.tr('payment_card'), 'icon': Icons.credit_card},
    {'value': 'crypto', 'label': context.tr('payment_crypto'), 'icon': Icons.currency_bitcoin},
  ];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _fillFromUserProfile());
  }

  Future<void> _fillFromUserProfile() async {
    final authProvider = context.read<AuthProvider>();
    if (!authProvider.isAuthenticated || authProvider.user == null) return;

    final user = authProvider.user!;
    if (_nameController.text.isEmpty && user.fullName.isNotEmpty) {
      _nameController.text = user.fullName;
    }
    if (_emailController.text.isEmpty && (user.email.isNotEmpty)) {
      _emailController.text = user.email;
    }
    if (_phoneController.text.isEmpty && (user.phoneNumber ?? '').isNotEmpty) {
      _phoneController.text = user.phoneNumber!;
    }

    final addresses = await authProvider.getAddresses();
    if (_addressController.text.isEmpty && addresses.isNotEmpty) {
      final defaultAddrs = addresses.where((a) => a.isDefault).toList();
      final defaultAddr = defaultAddrs.isNotEmpty ? defaultAddrs.first : addresses.first;
      if (defaultAddr.addressText.isNotEmpty) {
        _addressController.text = defaultAddr.addressText;
      }
      if (_nameController.text.isEmpty && (defaultAddr.name.isNotEmpty || defaultAddr.recipientName != null)) {
        _nameController.text = defaultAddr.recipientName ?? defaultAddr.name;
      }
      if (_phoneController.text.isEmpty && (defaultAddr.phone ?? '').isNotEmpty) {
        _phoneController.text = defaultAddr.phone!;
      }
    }
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    _nameController.dispose();
    _phoneController.dispose();
    _emailController.dispose();
    _addressController.dispose();
    _commentController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(context.tr('checkout')),
      ),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            _buildSectionTitle(context.tr('contact_info')),
            const SizedBox(height: 16),
            TextFormField(
              controller: _nameController,
              decoration: InputDecoration(
                labelText: context.tr('name_required'),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(8),
                ),
                prefixIcon: const Icon(Icons.person_outline),
              ),
              validator: (value) {
                if (value == null || value.isEmpty) {
                  return context.tr('enter_name');
                }
                return null;
              },
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _phoneController,
              decoration: InputDecoration(
                labelText: context.tr('phone_required'),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(8),
                ),
                prefixIcon: const Icon(Icons.phone_outlined),
              ),
              keyboardType: TextInputType.phone,
              validator: (value) {
                if (value == null || value.isEmpty) {
                  return context.tr('enter_phone');
                }
                return null;
              },
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _emailController,
              decoration: InputDecoration(
                labelText: 'Email',
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(8),
                ),
                prefixIcon: const Icon(Icons.email_outlined),
              ),
              keyboardType: TextInputType.emailAddress,
            ),
            const SizedBox(height: 24),
            _buildSectionTitle(context.tr('delivery_address')),
            const SizedBox(height: 16),
            TextFormField(
              controller: _addressController,
              decoration: InputDecoration(
                labelText: context.tr('address_required'),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(8),
                ),
                prefixIcon: const Icon(Icons.location_on_outlined),
              ),
              maxLines: 3,
              validator: (value) {
                if (value == null || value.isEmpty) {
                  return context.tr('enter_address');
                }
                return null;
              },
            ),
            const SizedBox(height: 24),
            _buildSectionTitle(context.tr('shipping_method')),
            const SizedBox(height: 16),
            _buildShippingMethodSection(),
            const SizedBox(height: 24),
            _buildSectionTitle(context.tr('payment_method')),
            const SizedBox(height: 16),
            ..._getPaymentMethods(context).map((method) {
              return RadioListTile<String>(
                value: method['value'],
                groupValue: _paymentMethod,
                onChanged: (value) {
                  setState(() {
                    _paymentMethod = value!;
                  });
                },
                title: Text(method['label']),
                secondary: Icon(method['icon']),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(8),
                  side: BorderSide(color: Colors.grey[300]!),
                ),
              );
            }),
            const SizedBox(height: 24),
            _buildSectionTitle(context.tr('comment')),
            const SizedBox(height: 16),
            TextFormField(
              controller: _commentController,
              decoration: InputDecoration(
                labelText: context.tr('comment_placeholder'),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(8),
                ),
                prefixIcon: const Icon(Icons.comment_outlined),
              ),
              maxLines: 3,
            ),
            const SizedBox(height: 24),
            _buildOrderSummary(),
            const SizedBox(height: 100),
          ],
        ),
      ),
      bottomNavigationBar: _buildBottomBar(),
    );
  }

  Widget _buildShippingMethodSection() {
    return Consumer<CartProvider>(
      builder: (context, cartProvider, _) {
        final opts = cartProvider.shippingOptions;
        final currency = cartProvider.cart?.currency ?? 'USD';
        final options = [
          ('ground', context.tr('shipping_ground'), context.tr('shipping_ground_desc'), opts['ground'] ?? 0),
          ('air', context.tr('shipping_air'), context.tr('shipping_air_desc'), opts['air'] ?? 0),
          ('sea', context.tr('shipping_sea'), context.tr('shipping_sea_desc'), opts['sea'] ?? 0),
        ];
        return Column(
          children: options.map((opt) {
            final (key, label, desc, cost) = opt;
            return RadioListTile<String>(
              value: key,
              groupValue: _shippingMethod,
              onChanged: (v) => setState(() => _shippingMethod = v!),
              title: Text(label),
              subtitle: Text(
                desc,
                style: TextStyle(fontSize: 12, color: Colors.grey[600]),
              ),
              secondary: Text(
                cost > 0 ? '+${cost.toStringAsFixed(2)} $currency' : 'Бесплатно',
                style: const TextStyle(fontWeight: FontWeight.w600),
              ),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(8),
                side: BorderSide(color: Colors.grey[300]!),
              ),
            );
          }).toList(),
        );
      },
    );
  }

  Widget _buildSectionTitle(String title) {
    return Text(
      title,
      style: const TextStyle(
        fontSize: 18,
        fontWeight: FontWeight.bold,
      ),
    );
  }

  Widget _buildOrderSummary() {
    return Consumer<CartProvider>(
      builder: (context, provider, child) {
        return Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: Colors.grey[100],
            borderRadius: BorderRadius.circular(12),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                context.tr('your_order'),
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 16),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text('${context.tr('items')} (${provider.cartItemCount}):'),
                  Text('${provider.totalAmount} ${provider.cart?.currency ?? 'RUB'}'),
                ],
              ),
              if (provider.discountAmount != '0.00') ...[
                const SizedBox(height: 8),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(context.tr('discount') + ':'),
                    Text(
                      '-${provider.discountAmount} ${provider.cart?.currency ?? 'RUB'}',
                      style: const TextStyle(color: Colors.green),
                    ),
                  ],
                ),
              ],
              const SizedBox(height: 8),
              Builder(
                builder: (_) {
                  final opts = provider.shippingOptions;
                  final cost = opts[_shippingMethod] ?? 0.0;
                  final currency = provider.cart?.currency ?? 'USD';
                  return Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(context.tr('delivery') + ':'),
                      Text(cost > 0 ? '+${cost.toStringAsFixed(2)} $currency' : context.tr('free')),
                    ],
                  );
                },
              ),
              const Divider(height: 24),
              Builder(
                builder: (_) {
                  final opts = provider.shippingOptions;
                  final shippingCost = opts[_shippingMethod] ?? 0.0;
                  final finalVal = double.tryParse(provider.finalAmount) ?? 0.0;
                  final total = finalVal + shippingCost;
                  final currency = provider.cart?.currency ?? 'RUB';
                  return Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        context.tr('total') + ':',
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      Text(
                        '${total.toStringAsFixed(2)} $currency',
                        style: const TextStyle(
                          fontSize: 20,
                          fontWeight: FontWeight.bold,
                          color: Colors.teal,
                        ),
                      ),
                    ],
                  );
                },
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildBottomBar() {
    return Consumer<OrderProvider>(
      builder: (context, orderProvider, child) {
        return Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: Colors.white,
            boxShadow: [
              BoxShadow(
                color: Colors.black.withOpacity(0.1),
                blurRadius: 8,
                offset: const Offset(0, -2),
              ),
            ],
          ),
          child: SafeArea(
            child: SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: orderProvider.isCreatingOrder ? null : _createOrder,
                style: ElevatedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  backgroundColor: Colors.teal,
                ),
                child: orderProvider.isCreatingOrder
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                        ),
                      )
                    : Text(
                        context.tr('confirm_order'),
                        style: TextStyle(fontSize: 16),
                      ),
              ),
            ),
          ),
        );
      },
    );
  }

  Future<void> _createOrder() async {
    if (!_formKey.currentState!.validate()) return;

    final orderProvider = context.read<OrderProvider>();
    final cartProvider = context.read<CartProvider>();

    final order = await orderProvider.createOrder(
      contactName: _nameController.text,
      contactPhone: _phoneController.text,
      contactEmail: _emailController.text.isEmpty ? null : _emailController.text,
      shippingAddressText: _addressController.text,
      paymentMethod: _paymentMethod,
      shippingMethod: _shippingMethod,
      comment: _commentController.text.isEmpty ? null : _commentController.text,
    );

    if (order != null && mounted) {
      await cartProvider.getCart();
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(
          builder: (_) => OrderSuccessScreen(order: order),
        ),
      );
    } else if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(orderProvider.error ?? context.tr('order_error')),
          backgroundColor: Colors.red,
        ),
      );
    }
  }
}

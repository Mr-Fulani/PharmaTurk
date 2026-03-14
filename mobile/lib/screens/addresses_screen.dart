import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/providers.dart';
import '../l10n/app_localizations.dart';
import '../models/models.dart';

class AddressesScreen extends StatefulWidget {
  const AddressesScreen({super.key});

  @override
  State<AddressesScreen> createState() => _AddressesScreenState();
}

class _AddressesScreenState extends State<AddressesScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<AuthProvider>().getAddresses();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(context.tr('addresses')),
      ),
      body: Consumer<AuthProvider>(
        builder: (context, provider, child) {
          if (provider.isLoading) {
            return const Center(child: CircularProgressIndicator());
          }

          return FutureBuilder<List<UserAddress>>(
            future: provider.getAddresses(),
            builder: (context, snapshot) {
              if (snapshot.connectionState == ConnectionState.waiting) {
                return const Center(child: CircularProgressIndicator());
              }

              final addresses = snapshot.data ?? [];

              if (addresses.isEmpty) {
                return _buildEmptyAddresses();
              }

              return ListView.builder(
                padding: const EdgeInsets.all(16),
                itemCount: addresses.length,
                itemBuilder: (context, index) {
                  final address = addresses[index];
                  return _AddressCard(
                    address: address,
                    onEdit: () => _showAddressDialog(address),
                    onDelete: () => _showDeleteDialog(address),
                  );
                },
              );
            },
          );
        },
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () => _showAddressDialog(null),
        backgroundColor: Colors.teal,
        child: const Icon(Icons.add),
      ),
    );
  }

  Widget _buildEmptyAddresses() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.location_on_outlined,
            size: 100,
            color: Colors.grey[400],
          ),
          const SizedBox(height: 24),
          Text(
            context.tr('no_addresses'),
            style: TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.bold,
              color: Colors.grey[600],
            ),
          ),
          const SizedBox(height: 8),
          Text(
            context.tr('add_address_hint'),
            style: TextStyle(
              fontSize: 16,
              color: Colors.grey[500],
            ),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }

  void _showAddressDialog(UserAddress? address) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (context) {
        return _AddressForm(
          address: address,
          onSave: (newAddress) async {
            final authProvider = context.read<AuthProvider>();
            if (address == null) {
              await authProvider.createAddress(newAddress);
            } else {
              await authProvider.updateAddress(address.id.toString(), newAddress);
            }
            if (mounted) {
              setState(() {});
            }
          },
        );
      },
    );
  }

  void _showDeleteDialog(UserAddress address) {
    showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: Text(context.tr('delete_address')),
          content: Text(context.tr('delete_address_confirm')),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: Text(context.tr('cancel')),
            ),
            ElevatedButton(
              onPressed: () async {
                Navigator.pop(context);
                await context.read<AuthProvider>().deleteAddress(address.id.toString());
                if (mounted) {
                  setState(() {});
                }
              },
              style: ElevatedButton.styleFrom(backgroundColor: Colors.red),
              child: Text(context.tr('remove')),
            ),
          ],
        );
      },
    );
  }
}

class _AddressCard extends StatelessWidget {
  final UserAddress address;
  final VoidCallback onEdit;
  final VoidCallback onDelete;

  const _AddressCard({
    required this.address,
    required this.onEdit,
    required this.onDelete,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Row(
                  children: [
                    Icon(
                      _getAddressTypeIcon(address.addressType),
                      color: Colors.teal,
                    ),
                    const SizedBox(width: 8),
                    Text(
                      address.name,
                      style: const TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    if (address.isDefault) ...[
                      const SizedBox(width: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 8,
                          vertical: 4,
                        ),
                        decoration: BoxDecoration(
                          color: Colors.teal.withOpacity(0.1),
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: Text(
                          context.tr('default_address_label'),
                          style: const TextStyle(
                            fontSize: 10,
                            color: Colors.teal,
                          ),
                        ),
                      ),
                    ],
                  ],
                ),
                PopupMenuButton<String>(
                  onSelected: (value) {
                    if (value == 'edit') {
                      onEdit();
                    } else if (value == 'delete') {
                      onDelete();
                    }
                  },
                  itemBuilder: (ctx) => [
                    PopupMenuItem(
                      value: 'edit',
                      child: Row(
                        children: [
                          const Icon(Icons.edit_outlined),
                          const SizedBox(width: 8),
                          Text(ctx.tr('edit')),
                        ],
                      ),
                    ),
                    PopupMenuItem(
                      value: 'delete',
                      child: Row(
                        children: [
                          const Icon(Icons.delete_outline, color: Colors.red),
                          const SizedBox(width: 8),
                          Text(ctx.tr('remove'), style: const TextStyle(color: Colors.red)),
                        ],
                      ),
                    ),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 12),
            Text(address.addressText),
            if (address.recipientName != null) ...[
              const SizedBox(height: 8),
              Text(
                '${context.tr('recipient')}: ${address.recipientName}',
                style: TextStyle(color: Colors.grey[600]),
              ),
            ],
            if (address.phone != null) ...[
              const SizedBox(height: 4),
              Text(
                '${context.tr('phone')}: ${address.phone}',
                style: TextStyle(color: Colors.grey[600]),
              ),
            ],
          ],
        ),
      ),
    );
  }

  IconData _getAddressTypeIcon(String type) {
    switch (type) {
      case 'home':
        return Icons.home_outlined;
      case 'work':
        return Icons.work_outline;
      default:
        return Icons.location_on_outlined;
    }
  }
}

class _AddressForm extends StatefulWidget {
  final UserAddress? address;
  final Function(UserAddress) onSave;

  const _AddressForm({
    this.address,
    required this.onSave,
  });

  @override
  State<_AddressForm> createState() => _AddressFormState();
}

class _AddressFormState extends State<_AddressForm> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _recipientController = TextEditingController();
  final _phoneController = TextEditingController();
  final _addressController = TextEditingController();
  String _addressType = 'home';
  bool _isDefault = false;

  @override
  void initState() {
    super.initState();
    if (widget.address != null) {
      _nameController.text = widget.address!.name;
      _recipientController.text = widget.address!.recipientName ?? '';
      _phoneController.text = widget.address!.phone ?? '';
      _addressController.text = widget.address!.addressText;
      _addressType = widget.address!.addressType;
      _isDefault = widget.address!.isDefault;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).viewInsets.bottom,
        left: 24,
        right: 24,
        top: 24,
      ),
      child: Form(
        key: _formKey,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              widget.address == null ? context.tr('new_address') : context.tr('edit_address'),
              style: const TextStyle(
                fontSize: 20,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 24),
            TextFormField(
              controller: _nameController,
              decoration: InputDecoration(
                labelText: context.tr('address_name'),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
              validator: (value) {
                if (value == null || value.isEmpty) {
                  return context.tr('enter_address_name');
                }
                return null;
              },
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _addressController,
              decoration: InputDecoration(
                labelText: context.tr('address_required'),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
              maxLines: 3,
              validator: (value) {
                if (value == null || value.isEmpty) {
                  return context.tr('enter_address_value');
                }
                return null;
              },
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _recipientController,
              decoration: InputDecoration(
                labelText: context.tr('recipient'),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _phoneController,
              decoration: InputDecoration(
                labelText: context.tr('phone'),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
              keyboardType: TextInputType.phone,
            ),
            const SizedBox(height: 16),
            Text(context.tr('address_type')),
            const SizedBox(height: 8),
            SegmentedButton<String>(
              segments: [
                ButtonSegment(
                  value: 'home',
                  label: Text(context.tr('address_type_home')),
                  icon: const Icon(Icons.home_outlined),
                ),
                ButtonSegment(
                  value: 'work',
                  label: Text(context.tr('address_type_work')),
                  icon: const Icon(Icons.work_outline),
                ),
                ButtonSegment(
                  value: 'other',
                  label: Text(context.tr('address_type_other')),
                  icon: const Icon(Icons.location_on_outlined),
                ),
              ],
              selected: {_addressType},
              onSelectionChanged: (value) {
                setState(() {
                  _addressType = value.first;
                });
              },
            ),
            const SizedBox(height: 16),
            CheckboxListTile(
              value: _isDefault,
              onChanged: (value) {
                setState(() {
                  _isDefault = value ?? false;
                });
              },
              title: const Text('Адрес по умолчанию'),
              contentPadding: EdgeInsets.zero,
            ),
            const SizedBox(height: 24),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: _save,
                style: ElevatedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  backgroundColor: Colors.teal,
                ),
                child: Text(context.tr('save')),
              ),
            ),
            const SizedBox(height: 24),
          ],
        ),
      ),
    );
  }

  void _save() {
    if (!_formKey.currentState!.validate()) return;

    final address = UserAddress(
      id: widget.address?.id ?? 0,
      name: _nameController.text,
      addressText: _addressController.text,
      recipientName: _recipientController.text.isEmpty
          ? null
          : _recipientController.text,
      phone: _phoneController.text.isEmpty ? null : _phoneController.text,
      addressType: _addressType,
      isDefault: _isDefault,
      isActive: true,
      createdAt: widget.address?.createdAt ?? DateTime.now(),
      updatedAt: DateTime.now(),
    );

    widget.onSave(address);
    Navigator.pop(context);
  }
}

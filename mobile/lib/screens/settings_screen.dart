import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/providers.dart';
import '../l10n/app_localizations.dart';

const _currencies = [
  ('RUB', 'Рубли (₽)'),
  ('USD', 'Доллары (\$)'),
  ('EUR', 'Евро (€)'),
  ('TRY', 'Турецкая лира (₺)'),
  ('KZT', 'Тенге (₸)'),
  ('USDT', 'USDT'),
];

const _languages = [
  ('ru', 'Русский'),
  ('en', 'English'),
];

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(context.tr('settings')),
      ),
      body: ListView(
        children: [
          _buildSectionTitle(context.tr('general')),
          Consumer<AuthProvider>(
            builder: (context, auth, _) => _buildSettingsTile(
              icon: Icons.language_outlined,
              title: context.tr('language'),
              subtitle: _getLanguageLabel(auth.user?.preferredLanguage ?? 'ru'),
              onTap: () => _showLanguagePicker(context, auth),
            ),
          ),
          Consumer<AuthProvider>(
            builder: (context, auth, _) => _buildSettingsTile(
              icon: Icons.currency_exchange_outlined,
              title: context.tr('currency'),
              subtitle: auth.user?.preferredCurrency ?? 'RUB',
              onTap: () => _showCurrencyPicker(context, auth),
            ),
          ),
          _buildSettingsTile(
            icon: Icons.notifications_outlined,
            title: context.tr('notifications'),
            subtitle: context.tr('notifications_on'),
            onTap: () {
              // TODO: Notification settings
            },
          ),
          _buildSectionTitle(context.tr('security')),
          _buildSettingsTile(
            icon: Icons.lock_outlined,
            title: context.tr('change_password'),
            onTap: () {
              _showChangePasswordDialog(context);
            },
          ),
          _buildSettingsTile(
            icon: Icons.verified_user_outlined,
            title: context.tr('2fa'),
            subtitle: context.tr('2fa_off'),
            onTap: () {
              // TODO: 2FA settings
            },
          ),
          _buildSectionTitle(context.tr('about')),
          _buildSettingsTile(
            icon: Icons.info_outlined,
            title: context.tr('version'),
            subtitle: '1.0.0',
            onTap: () {},
          ),
          _buildSettingsTile(
            icon: Icons.policy_outlined,
            title: context.tr('privacy'),
            onTap: () {
              // TODO: Open privacy policy
            },
          ),
          _buildSettingsTile(
            icon: Icons.description_outlined,
            title: context.tr('terms'),
            onTap: () {
              // TODO: Open terms
            },
          ),
          _buildSettingsTile(
            icon: Icons.support_agent_outlined,
            title: context.tr('support'),
            onTap: () {
              // TODO: Contact support
            },
          ),
        ],
      ),
    );
  }

  Widget _buildSectionTitle(String title) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 24, 16, 8),
      child: Text(
        title,
        style: TextStyle(
          fontSize: 14,
          fontWeight: FontWeight.bold,
          color: Colors.grey[600],
        ),
      ),
    );
  }

  String _getLanguageLabel(String code) {
    return _languages.firstWhere(
      (e) => e.$1 == code,
      orElse: () => ('ru', 'Русский'),
    ).$2;
  }

  void _showLanguagePicker(BuildContext context, AuthProvider auth) {
    final current = auth.user?.preferredLanguage ?? 'ru';
    showModalBottomSheet(
      context: context,
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsets.all(16),
              child: Text(
                ctx.tr('select_language'),
                style: Theme.of(ctx).textTheme.titleLarge,
              ),
            ),
            ..._languages.map((e) {
              final code = e.$1;
              final label = e.$2;
              return ListTile(
                title: Text(label),
                trailing: current == code ? const Icon(Icons.check, color: Colors.teal) : null,
                onTap: () async {
                  Navigator.pop(ctx);
                  final localeProvider = ctx.read<LocaleProvider>();
                  await localeProvider.setLocale(code);
                  final ok = await auth.updateProfile({'language': code});
                  if (ctx.mounted) {
                    ScaffoldMessenger.of(ctx).showSnackBar(
                      SnackBar(
                        content: Text(ok ? '${ctx.tr('language_changed')} $label' : (auth.error ?? ctx.tr('error'))),
                        backgroundColor: ok ? null : Colors.red,
                      ),
                    );
                  }
                },
              );
            }),
          ],
        ),
      ),
    );
  }

  Widget _buildSettingsTile({
    required IconData icon,
    required String title,
    String? subtitle,
    required VoidCallback onTap,
  }) {
    return ListTile(
      leading: Icon(icon, color: Colors.teal),
      title: Text(title),
      subtitle: subtitle != null ? Text(subtitle) : null,
      trailing: const Icon(Icons.chevron_right),
      onTap: onTap,
    );
  }

  void _showCurrencyPicker(BuildContext context, AuthProvider auth) {
    final current = auth.user?.preferredCurrency ?? 'RUB';
    showModalBottomSheet(
      context: context,
      builder: (context) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsets.all(16),
              child: Text(
                context.tr('select_currency'),
                style: Theme.of(context).textTheme.titleLarge,
              ),
            ),
            ..._currencies.map((e) {
              final code = e.$1;
              final label = e.$2;
              return ListTile(
                title: Text(label),
                subtitle: Text(code),
                trailing: current == code ? const Icon(Icons.check, color: Colors.teal) : null,
                onTap: () async {
                  Navigator.pop(context);
                  final ok = await auth.updateProfile({'currency': code});
                  if (context.mounted) {
                    if (ok) {
                      await context.read<CartProvider>().getCart();
                      final catalog = context.read<CatalogProvider>();
                      await catalog.getProducts(refresh: true);
                      await catalog.getFeaturedProducts();
                      final slug = catalog.selectedProduct?.slug;
                      if (slug != null) {
                        await catalog.getProductDetail(slug);
                      }
                    }
                    if (context.mounted) {
                      ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: Text(ok ? '${context.tr('currency_changed')} $code' : (auth.error ?? context.tr('error'))),
                          backgroundColor: ok ? null : Colors.red,
                        ),
                      );
                    }
                  }
                },
              );
            }),
          ],
        ),
      ),
    );
  }

  void _showChangePasswordDialog(BuildContext context) {
    final formKey = GlobalKey<FormState>();
    final oldPasswordController = TextEditingController();
    final newPasswordController = TextEditingController();
    final confirmPasswordController = TextEditingController();

    showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: Text(context.tr('change_password')),
          content: Form(
            key: formKey,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextFormField(
                  controller: oldPasswordController,
                  decoration: InputDecoration(
                    labelText: context.tr('old_password'),
                  ),
                  obscureText: true,
                  validator: (value) {
                    if (value == null || value.isEmpty) {
                      return context.tr('enter_old_password');
                    }
                    return null;
                  },
                ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: newPasswordController,
                  decoration: InputDecoration(
                    labelText: context.tr('new_password'),
                  ),
                  obscureText: true,
                  validator: (value) {
                    if (value == null || value.isEmpty) {
                      return context.tr('enter_new_password');
                    }
                    if (value.length < 6) {
                      return context.tr('password_min_length');
                    }
                    return null;
                  },
                ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: confirmPasswordController,
                  decoration: InputDecoration(
                    labelText: context.tr('confirm_password'),
                  ),
                  obscureText: true,
                  validator: (value) {
                    if (value == null || value.isEmpty) {
                      return context.tr('confirm_password_required');
                    }
                    if (value != newPasswordController.text) {
                      return context.tr('passwords_mismatch');
                    }
                    return null;
                  },
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: Text(context.tr('cancel')),
            ),
            ElevatedButton(
              onPressed: () async {
                if (!formKey.currentState!.validate()) return;

                final success = await context.read<AuthProvider>().changePassword(
                  oldPasswordController.text,
                  newPasswordController.text,
                  confirmPasswordController.text,
                );

                if (success && context.mounted) {
                  Navigator.pop(context);
                  ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(
                    content: Text(context.tr('password_changed')),
                  ),
                  );
                } else if (context.mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text(
                        context.read<AuthProvider>().error ?? context.tr('error'),
                      ),
                      backgroundColor: Colors.red,
                    ),
                  );
                }
              },
              child: Text(context.tr('save')),
            ),
          ],
        );
      },
    );
  }
}

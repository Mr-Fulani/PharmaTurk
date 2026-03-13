import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/providers.dart';

const _currencies = [
  ('RUB', 'Рубли (₽)'),
  ('USD', 'Доллары (\$)'),
  ('EUR', 'Евро (€)'),
  ('TRY', 'Турецкая лира (₺)'),
  ('KZT', 'Тенге (₸)'),
  ('USDT', 'USDT'),
];

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Настройки'),
      ),
      body: ListView(
        children: [
          _buildSectionTitle('Общие'),
          _buildSettingsTile(
            icon: Icons.language_outlined,
            title: 'Язык',
            subtitle: 'Русский',
            onTap: () {
              // TODO: Change language
            },
          ),
          Consumer<AuthProvider>(
            builder: (context, auth, _) => _buildSettingsTile(
              icon: Icons.currency_exchange_outlined,
              title: 'Валюта',
              subtitle: auth.user?.preferredCurrency ?? 'RUB',
              onTap: () => _showCurrencyPicker(context, auth),
            ),
          ),
          _buildSettingsTile(
            icon: Icons.notifications_outlined,
            title: 'Уведомления',
            subtitle: 'Включены',
            onTap: () {
              // TODO: Notification settings
            },
          ),
          _buildSectionTitle('Безопасность'),
          _buildSettingsTile(
            icon: Icons.lock_outlined,
            title: 'Изменить пароль',
            onTap: () {
              _showChangePasswordDialog(context);
            },
          ),
          _buildSettingsTile(
            icon: Icons.verified_user_outlined,
            title: 'Двухфакторная аутентификация',
            subtitle: 'Отключена',
            onTap: () {
              // TODO: 2FA settings
            },
          ),
          _buildSectionTitle('О приложении'),
          _buildSettingsTile(
            icon: Icons.info_outlined,
            title: 'Версия приложения',
            subtitle: '1.0.0',
            onTap: () {},
          ),
          _buildSettingsTile(
            icon: Icons.policy_outlined,
            title: 'Политика конфиденциальности',
            onTap: () {
              // TODO: Open privacy policy
            },
          ),
          _buildSettingsTile(
            icon: Icons.description_outlined,
            title: 'Условия использования',
            onTap: () {
              // TODO: Open terms
            },
          ),
          _buildSettingsTile(
            icon: Icons.support_agent_outlined,
            title: 'Поддержка',
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
                'Выберите валюту',
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
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: Text(ok ? 'Валюта изменена на $code' : (auth.error ?? 'Ошибка')),
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

  void _showChangePasswordDialog(BuildContext context) {
    final formKey = GlobalKey<FormState>();
    final oldPasswordController = TextEditingController();
    final newPasswordController = TextEditingController();
    final confirmPasswordController = TextEditingController();

    showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: const Text('Изменить пароль'),
          content: Form(
            key: formKey,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextFormField(
                  controller: oldPasswordController,
                  decoration: const InputDecoration(
                    labelText: 'Текущий пароль',
                  ),
                  obscureText: true,
                  validator: (value) {
                    if (value == null || value.isEmpty) {
                      return 'Введите текущий пароль';
                    }
                    return null;
                  },
                ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: newPasswordController,
                  decoration: const InputDecoration(
                    labelText: 'Новый пароль',
                  ),
                  obscureText: true,
                  validator: (value) {
                    if (value == null || value.isEmpty) {
                      return 'Введите новый пароль';
                    }
                    if (value.length < 6) {
                      return 'Пароль должен быть не менее 6 символов';
                    }
                    return null;
                  },
                ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: confirmPasswordController,
                  decoration: const InputDecoration(
                    labelText: 'Подтвердите новый пароль',
                  ),
                  obscureText: true,
                  validator: (value) {
                    if (value == null || value.isEmpty) {
                      return 'Подтвердите пароль';
                    }
                    if (value != newPasswordController.text) {
                      return 'Пароли не совпадают';
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
              child: const Text('Отмена'),
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
                    const SnackBar(
                      content: Text('Пароль успешно изменен'),
                    ),
                  );
                } else if (context.mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text(
                        context.read<AuthProvider>().error ?? 'Ошибка',
                      ),
                      backgroundColor: Colors.red,
                    ),
                  );
                }
              },
              child: const Text('Сохранить'),
            ),
          ],
        );
      },
    );
  }
}

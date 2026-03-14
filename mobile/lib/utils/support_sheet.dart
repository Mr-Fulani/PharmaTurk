import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:open_mail_launcher/open_mail_launcher.dart';
import 'package:url_launcher/url_launcher.dart';
import '../l10n/app_localizations.dart';
import '../models/footer_settings.dart';

/// Показывает bottom sheet с контактами: email и соцсети (Telegram, WhatsApp, VK, Instagram).
void showSupportSheet(BuildContext context, FooterSettings? fs) {
  final hasEmail = fs?.hasEmail ?? false;
  final hasSocial = fs?.hasSocialLinks ?? false;
  if (!hasEmail && !hasSocial) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(context.tr('no_contacts_configured'))),
    );
    return;
  }
  showModalBottomSheet(
    context: context,
    builder: (ctx) => SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              context.tr('contact_support'),
              style: Theme.of(ctx).textTheme.titleLarge,
            ),
            const SizedBox(height: 16),
            if (hasEmail)
              ListTile(
                leading: const Icon(Icons.email_outlined),
                title: Text(context.tr('email_support')),
                subtitle: Text(fs!.email ?? ''),
                onTap: () {
                  Navigator.pop(ctx);
                  _openMail(context, fs.email!);
                },
              ),
            if (fs?.telegramUrl != null && fs!.telegramUrl!.isNotEmpty)
              ListTile(
                leading: const Icon(Icons.send_outlined),
                title: const Text('Telegram'),
                onTap: () {
                  Navigator.pop(ctx);
                  _openUrl(ctx, fs.telegramUrl!);
                },
              ),
            if (fs?.whatsappUrl != null && fs!.whatsappUrl!.isNotEmpty)
              ListTile(
                leading: const Icon(Icons.chat_outlined),
                title: const Text('WhatsApp'),
                onTap: () {
                  Navigator.pop(ctx);
                  _openUrl(ctx, fs.whatsappUrl!);
                },
              ),
            if (fs?.vkUrl != null && fs!.vkUrl!.isNotEmpty)
              ListTile(
                leading: const Icon(Icons.group_outlined),
                title: const Text('VK'),
                onTap: () {
                  Navigator.pop(ctx);
                  _openUrl(ctx, fs.vkUrl!);
                },
              ),
            if (fs?.instagramUrl != null && fs!.instagramUrl!.isNotEmpty)
              ListTile(
                leading: const Icon(Icons.camera_alt_outlined),
                title: const Text('Instagram'),
                onTap: () {
                  Navigator.pop(ctx);
                  _openUrl(ctx, fs.instagramUrl!);
                },
              ),
          ],
        ),
      ),
    ),
  );
}

Future<void> _openMail(BuildContext context, String email) async {
  final messenger = ScaffoldMessenger.of(context);
  final msg = context.tr('email_copied');
  final trimmed = email.trim();
  final mailto = Uri.parse('mailto:$trimmed');

  try {
    final content = EmailContent(to: [trimmed]);
    final result = await OpenMailLauncher.openMailApp(emailContent: content);
    if (result.didOpen) return;
    if (result.hasMultipleOptions && context.mounted) {
      final selected = await OpenMailLauncher.showMailAppPicker(
        context: context,
        mailApps: result.options,
        title: context.tr('email_support'),
      );
      if (selected != null) {
        final opened = await OpenMailLauncher.openSpecificMailApp(
          mailApp: selected,
          emailContent: content,
        );
        if (opened) return;
      }
    }
  } catch (_) {}

  try {
    if (await launchUrl(mailto)) return;
  } catch (_) {}

  if (!context.mounted) return;
  _showEmailActionsSheet(
    context, trimmed, mailto, messenger, msg, context.tr('mail_not_available'),
  );
}

void _showEmailActionsSheet(
  BuildContext context,
  String email,
  Uri mailto,
  ScaffoldMessengerState messenger,
  String copiedMsg,
  String mailNotAvailableMsg,
) {
  showModalBottomSheet(
    context: context,
    builder: (ctx) => SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          ListTile(
            leading: const Icon(Icons.email_outlined),
            title: Text(email),
            subtitle: Text(context.tr('email_support')),
          ),
          ListTile(
            leading: const Icon(Icons.open_in_new),
            title: Text(context.tr('open_in_mail')),
            onTap: () async {
              bool opened = false;
              for (final mode in [
                LaunchMode.platformDefault,
                LaunchMode.externalApplication,
                LaunchMode.externalNonBrowserApplication,
              ]) {
                try {
                  opened = await launchUrl(mailto, mode: mode);
                  if (opened) break;
                } catch (_) {}
              }
              if (!opened) {
                try {
                  final content = EmailContent(to: [email]);
                  final result = await OpenMailLauncher.openMailApp(emailContent: content);
                  opened = result.didOpen;
                  if (!opened && result.hasMultipleOptions && ctx.mounted) {
                    final selected = await OpenMailLauncher.showMailAppPicker(
                      context: ctx,
                      mailApps: result.options,
                      title: context.tr('email_support'),
                    );
                    if (selected != null) {
                      opened = await OpenMailLauncher.openSpecificMailApp(
                        mailApp: selected,
                        emailContent: content,
                      );
                    }
                  }
                } catch (_) {}
              }
              if (!ctx.mounted) return;
              Navigator.pop(ctx);
              if (!opened) {
                messenger.showSnackBar(
                  SnackBar(content: Text(mailNotAvailableMsg)),
                );
              }
            },
          ),
          ListTile(
            leading: const Icon(Icons.copy),
            title: Text(context.tr('copy_email')),
            onTap: () async {
              Navigator.pop(ctx);
              await Clipboard.setData(ClipboardData(text: email));
              messenger.showSnackBar(SnackBar(content: Text(copiedMsg)));
            },
          ),
        ],
      ),
    ),
  );
}

Future<void> _openUrl(BuildContext context, String url) async {
  final uri = Uri.tryParse(url);
  if (uri == null) return;
  try {
    await launchUrl(uri, mode: LaunchMode.externalApplication);
  } catch (_) {
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(context.tr('error'))),
      );
    }
  }
}

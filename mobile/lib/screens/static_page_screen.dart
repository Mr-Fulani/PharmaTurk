import 'package:flutter/material.dart';
import 'package:flutter_html/flutter_html.dart';
import 'package:provider/provider.dart';
import '../l10n/app_localizations.dart';
import '../providers/locale_provider.dart';
import '../services/page_service.dart';

/// Экран статической страницы (политика, доставка, возврат) — контент из API.
class StaticPageScreen extends StatelessWidget {
  final String slug;
  final String? titleOverride;

  const StaticPageScreen({
    super.key,
    required this.slug,
    this.titleOverride,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(titleOverride ?? slug),
      ),
      body: _PageBody(slug: slug, titleOverride: titleOverride),
    );
  }
}

class _PageBody extends StatelessWidget {
  final String slug;
  final String? titleOverride;

  const _PageBody({required this.slug, this.titleOverride});

  @override
  Widget build(BuildContext context) {
      return FutureBuilder<StaticPage?>(
        future: PageService().getPage(slug, lang: _getLang(context)),
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          final page = snapshot.data;
          if (page == null) {
            return Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.error_outline, size: 48, color: Colors.grey[600]),
                  const SizedBox(height: 16),
                  Text(
                    context.tr('page_not_found'),
                    style: TextStyle(color: Colors.grey[600]),
                  ),
                ],
              ),
            );
          }
          return SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (page.content.isNotEmpty)
                  Html(
                    data: _stripDuplicateTitle(page.content, page.title),
                    style: {
                      'body': Style(margin: Margins.zero, padding: HtmlPaddings.zero),
                      'h2': Style(fontWeight: FontWeight.bold),
                      'h3': Style(fontWeight: FontWeight.w600),
                      'p': Style(lineHeight: const LineHeight(1.5)),
                    },
                  )
                else
                  Text(
                    context.tr('no_content'),
                    style: TextStyle(color: Colors.grey[600]),
                  ),
              ],
            ),
          );
        },
      );
  }

  String _getLang(BuildContext context) {
    try {
      final locale = context.read<LocaleProvider>().locale;
      return locale.languageCode;
    } catch (_) {
      return 'ru';
    }
  }

  /// Убирает первый h2, если он совпадает с заголовком (заголовок уже в AppBar).
  String _stripDuplicateTitle(String content, String title) {
    if (title.isEmpty) return content;
    final escaped = RegExp.escape(title);
    final pattern = RegExp(
      r'<h2[^>]*>\s*' + escaped + r'\s*</h2>',
      caseSensitive: false,
      dotAll: true,
    );
    return content.replaceFirst(pattern, '').trim();
  }
}

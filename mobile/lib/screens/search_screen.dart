import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:cached_network_image/cached_network_image.dart';
import '../providers/providers.dart';
import '../l10n/app_localizations.dart';
import '../models/models.dart';
import '../utils/image_url.dart';
import '../utils/price_format.dart';
import 'product_detail_screen.dart';

/// Экран поиска товаров. Открывается через showSearch.
class ProductSearchScreen extends SearchDelegate<Product?> {
  ProductSearchScreen({String? searchHint}) : super(searchFieldLabel: searchHint ?? '');

  @override
  List<Widget> buildActions(BuildContext context) {
    return [
      if (query.isNotEmpty)
        IconButton(
          icon: const Icon(Icons.clear),
          onPressed: () => query = '',
        ),
    ];
  }

  @override
  Widget buildLeading(BuildContext context) {
    return IconButton(
      icon: const Icon(Icons.arrow_back),
      onPressed: () => close(context, null),
    );
  }

  @override
  Widget buildResults(BuildContext context) {
    if (query.isEmpty) {
      return const Center(child: Text(''));
    }
    return _SearchResults(query: query);
  }

  @override
  Widget buildSuggestions(BuildContext context) {
    if (query.isEmpty) {
      return Center(
        child: Text(
          context.tr('search_placeholder'),
          style: TextStyle(color: Colors.grey[600]),
        ),
      );
    }
    return _SearchResults(query: query);
  }
}

class _SearchResults extends StatefulWidget {
  final String query;

  const _SearchResults({required this.query});

  @override
  State<_SearchResults> createState() => _SearchResultsState();
}

class _SearchResultsState extends State<_SearchResults> {
  Timer? _debounce;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _doSearch());
  }

  @override
  void didUpdateWidget(_SearchResults oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.query != widget.query) {
      _debounce?.cancel();
      _debounce = Timer(const Duration(milliseconds: 400), _doSearch);
    }
  }

  void _doSearch() {
    if (widget.query.isEmpty) return;
    context.read<CatalogProvider>().searchProducts(widget.query);
  }

  @override
  void dispose() {
    _debounce?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<CatalogProvider>(
      builder: (context, provider, _) {
        if (provider.isLoadingProducts && provider.searchResults.isEmpty) {
          return const Center(child: CircularProgressIndicator());
        }

        if (provider.productsError != null && provider.searchResults.isEmpty) {
          return Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(provider.productsError!),
                const SizedBox(height: 16),
                ElevatedButton(
                  onPressed: () => provider.searchProducts(widget.query),
                  child: Text(context.tr('retry')),
                ),
              ],
            ),
          );
        }

        if (provider.searchResults.isEmpty) {
          return Center(
            child: Text(
              context.tr('products_not_found'),
              style: TextStyle(color: Colors.grey[600]),
            ),
          );
        }

        return ListView.builder(
          padding: const EdgeInsets.all(16),
          itemCount: provider.searchResults.length,
          itemBuilder: (context, index) {
            final product = provider.searchResults[index];
            return _SearchResultTile(product: product);
          },
        );
      },
    );
  }
}

class _SearchResultTile extends StatelessWidget {
  final Product product;

  const _SearchResultTile({required this.product});

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: product.mainImageUrl != null && product.mainImageUrl!.isNotEmpty
          ? ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: CachedNetworkImage(
                imageUrl: resolveImageUrl(product.mainImageUrl),
                width: 56,
                height: 56,
                fit: BoxFit.cover,
                errorWidget: (_, __, ___) => Container(
                  width: 56,
                  height: 56,
                  color: Colors.grey[200],
                  child: const Icon(Icons.image_not_supported),
                ),
              ),
            )
          : Container(
              width: 56,
              height: 56,
              color: Colors.grey[200],
              child: const Icon(Icons.image_not_supported),
            ),
      title: Text(
        product.name,
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
      ),
      subtitle: Text(
        formatPriceWithCurrency(product.price, product.currency),
        style: TextStyle(
          fontWeight: FontWeight.bold,
          color: Colors.teal[700],
        ),
      ),
      onTap: () {
        Navigator.push(
          context,
          MaterialPageRoute(
            builder: (_) => ProductDetailScreen(slug: product.slug),
          ),
        );
      },
    );
  }
}

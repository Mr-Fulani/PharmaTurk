import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:cached_network_image/cached_network_image.dart';
import '../utils/image_url.dart';
import '../utils/price_format.dart';
import '../providers/providers.dart';
import '../l10n/app_localizations.dart';
import '../models/models.dart';

class ProductDetailScreen extends StatefulWidget {
  final String slug;

  const ProductDetailScreen({
    super.key,
    required this.slug,
  });

  @override
  State<ProductDetailScreen> createState() => _ProductDetailScreenState();
}

class _ProductDetailScreenState extends State<ProductDetailScreen> {
  int _currentImageIndex = 0;
  int _quantity = 1;
  late PageController _pageController;

  @override
  void initState() {
    super.initState();
    _pageController = PageController();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadProduct();
    });
  }

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  Future<void> _loadProduct() async {
    await context.read<CatalogProvider>().getProductDetail(widget.slug);
    if (!mounted) return;
    final product = context.read<CatalogProvider>().selectedProduct;
    if (product != null) {
      await context.read<FavoriteProvider>().checkIsFavorite(product.id);
      if (!mounted) return;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Consumer<CatalogProvider>(
        builder: (context, provider, child) {
          if (provider.isLoadingProductDetail) {
            return const Center(child: CircularProgressIndicator());
          }

          if (provider.productsError != null) {
            return Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(provider.productsError!),
                  const SizedBox(height: 16),
                  ElevatedButton(
                    onPressed: _loadProduct,
                    child: Text(context.tr('retry')),
                  ),
                ],
              ),
            );
          }

          final product = provider.selectedProduct;
          if (product == null) {
            return Center(child: Text(context.tr('product_not_found')));
          }

          return CustomScrollView(
            slivers: [
              _buildAppBar(product),
              _buildImageGallery(product),
              _buildProductInfo(product),
              _buildDescription(product),
              _buildAttributes(product),
              if (provider.similarProducts.isNotEmpty)
                _buildSimilarProducts(provider.similarProducts),
              const SliverToBoxAdapter(child: SizedBox(height: 100)),
            ],
          );
        },
      ),
      bottomNavigationBar: _buildBottomBar(),
    );
  }

  Widget _buildAppBar(ProductDetail product) {
    return SliverAppBar(
      floating: true,
      actions: [
        Consumer<FavoriteProvider>(
          builder: (context, favoriteProvider, child) {
            final isFavorite = favoriteProvider.isFavorite(product.id);
            return IconButton(
              icon: Icon(
                isFavorite ? Icons.favorite : Icons.favorite_outline,
                color: isFavorite ? Colors.red : null,
              ),
              onPressed: () {
                favoriteProvider.toggleFavorite(product.id);
              },
            );
          },
        ),
        IconButton(
          icon: const Icon(Icons.share_outlined),
          onPressed: () {
            // TODO: Share product
          },
        ),
      ],
    );
  }

  Widget _buildImageGallery(ProductDetail product) {
    final images = product.images ?? [];
    final mainImage = product.mainImageUrl ?? product.videoUrl;
    if (images.isEmpty && mainImage == null) {
      return const SliverToBoxAdapter(child: SizedBox.shrink());
    }

    // Собираем все медиа: изображения и видео (image_url или video_url)
    final allMedia = images.isNotEmpty
        ? images
            .map((i) => _MediaItem(
                  imageUrl: i.image.isNotEmpty ? i.image : null,
                  videoUrl: i.videoUrl,
                ))
            .where((m) => m.imageUrl != null || m.videoUrl != null)
            .toList()
        : [_MediaItem(imageUrl: product.mainImageUrl, videoUrl: product.videoUrl)];

    if (allMedia.isEmpty) {
      return const SliverToBoxAdapter(child: SizedBox.shrink());
    }

    return SliverToBoxAdapter(
      child: Column(
        children: [
          Container(
            height: 350,
            color: Colors.grey[100],
            child: PageView.builder(
              controller: _pageController,
              itemCount: allMedia.length,
              onPageChanged: (index) {
                setState(() {
                  _currentImageIndex = index;
                });
              },
              itemBuilder: (context, index) {
                final m = allMedia[index];
                final imageUrl = resolveImageUrlOrNull(m.imageUrl);
                if (m.videoUrl != null && imageUrl == null) {
                  return _VideoPlaceholder(videoUrl: m.videoUrl!);
                }
                if (imageUrl == null) {
                  return Container(
                    color: Colors.grey[200],
                    child: const Center(child: Icon(Icons.image_not_supported, size: 64)),
                  );
                }
                return CachedNetworkImage(
                  imageUrl: imageUrl,
                  fit: BoxFit.contain,
                  placeholder: (_, __) => Container(
                    color: Colors.grey[200],
                    child: const Center(child: CircularProgressIndicator()),
                  ),
                  errorWidget: (_, __, ___) => Container(
                    color: Colors.grey[200],
                    child: const Icon(Icons.image_not_supported, size: 64),
                  ),
                );
              },
            ),
          ),
          if (allMedia.length > 1)
            Padding(
              padding: const EdgeInsets.all(16.0),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: allMedia.asMap().entries.map((entry) {
                  final index = entry.key;
                  final isActive = _currentImageIndex == index;
                  return GestureDetector(
                    onTap: () {
                      _pageController.animateToPage(
                        index,
                        duration: const Duration(milliseconds: 300),
                        curve: Curves.easeInOut,
                      );
                    },
                    behavior: HitTestBehavior.opaque,
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 200),
                      width: isActive ? 10 : 8,
                      height: 8,
                      margin: const EdgeInsets.symmetric(horizontal: 4),
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: isActive ? Colors.teal : Colors.grey[300],
                      ),
                    ),
                  );
                }).toList(),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildProductInfo(ProductDetail product) {
    return SliverToBoxAdapter(
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (product.brand != null)
              Text(
                product.brand!.name,
                style: TextStyle(
                  fontSize: 14,
                  color: Colors.grey[600],
                ),
              ),
            const SizedBox(height: 8),
            Text(
              product.name,
              style: const TextStyle(
                fontSize: 24,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Text(
                  formatPriceWithCurrency(product.price, product.currency),
                  style: const TextStyle(
                    fontSize: 28,
                    fontWeight: FontWeight.bold,
                    color: Colors.teal,
                  ),
                ),
                if (hasValidOldPrice(product.oldPrice)) ...[
                  const SizedBox(width: 12),
                  Text(
                    formatPriceWithCurrency(product.oldPrice, product.currency),
                    style: TextStyle(
                      fontSize: 20,
                      decoration: TextDecoration.lineThrough,
                      color: Colors.grey[600],
                    ),
                  ),
                ],
              ],
            ),
            const SizedBox(height: 16),
            if (product.isAvailable)
              Row(
                children: [
                  Container(
                    width: 8,
                    height: 8,
                    decoration: const BoxDecoration(
                      shape: BoxShape.circle,
                      color: Colors.green,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Text(
                    context.tr('in_stock'),
                    style: TextStyle(color: Colors.green),
                  ),
                  if (product.stockQuantity != null) ...[
                    const SizedBox(width: 8),
                    Text(
                      '(${product.stockQuantity} шт.)',
                      style: TextStyle(color: Colors.grey[600]),
                    ),
                  ],
                ],
              )
            else
              Row(
                children: [
                  Container(
                    width: 8,
                    height: 8,
                    decoration: const BoxDecoration(
                      shape: BoxShape.circle,
                      color: Colors.red,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Text(
                    context.tr('out_of_stock'),
                    style: TextStyle(color: Colors.red),
                  ),
                ],
              ),
            const SizedBox(height: 24),
            Text(
              context.tr('quantity'),
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w500,
              ),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                _QuantityButton(
                  icon: Icons.remove,
                  onPressed: _quantity > 1
                      ? () => setState(() => _quantity--)
                      : null,
                ),
                Container(
                  width: 60,
                  alignment: Alignment.center,
                  child: Text(
                    '$_quantity',
                    style: const TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
                _QuantityButton(
                  icon: Icons.add,
                  onPressed: () => setState(() => _quantity++),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildDescription(ProductDetail product) {
    if (product.description == null || product.description!.isEmpty) {
      return const SliverToBoxAdapter(child: SizedBox.shrink());
    }

    return SliverToBoxAdapter(
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              context.tr('description'),
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 12),
            Text(
              product.description!,
              style: TextStyle(
                fontSize: 14,
                color: Colors.grey[800],
                height: 1.5,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAttributes(ProductDetail product) {
    final attributes = product.dynamicAttributes;
    if (attributes == null || attributes.isEmpty) {
      return const SliverToBoxAdapter(child: SizedBox.shrink());
    }

    return SliverToBoxAdapter(
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Характеристики',
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 12),
            ...attributes.map((attr) {
              return _AttributeRow(
                name: attr.displayName ?? attr.name,
                value: attr.value,
              );
            }),
          ],
        ),
      ),
    );
  }

  Widget _buildSimilarProducts(List<Product> products) {
    return SliverToBoxAdapter(
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Похожие товары',
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 16),
            SizedBox(
              height: 200,
              child: ListView.builder(
                scrollDirection: Axis.horizontal,
                itemCount: products.length,
                itemBuilder: (context, index) {
                  final product = products[index];
                  return _SimilarProductCard(product: product);
                },
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildBottomBar() {
    return Consumer<CatalogProvider>(
      builder: (context, provider, child) {
        final product = provider.selectedProduct;
        if (product == null) return const SizedBox.shrink();

        return Container(
          padding: const EdgeInsets.all(16.0),
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
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Итого:',
                        style: TextStyle(
                          fontSize: 14,
                          color: Colors.grey,
                        ),
                      ),
                      Text(
                        formatPriceWithCurrency(
                          ((double.tryParse(product.price ?? '0') ?? 0) * _quantity).toString(),
                          product.currency,
                        ),
                        style: const TextStyle(
                          fontSize: 20,
                          fontWeight: FontWeight.bold,
                          color: Colors.teal,
                        ),
                      ),
                    ],
                  ),
                ),
                Expanded(
                  flex: 2,
                  child: ElevatedButton(
                    onPressed: product.isAvailable
                        ? () => _addToCart(product)
                        : null,
                    style: ElevatedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 16),
                      backgroundColor: Colors.teal,
                    ),
                    child: Text(
                      product.isAvailable ? 'В корзину' : 'Нет в наличии',
                      style: const TextStyle(fontSize: 16),
                    ),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Future<void> _addToCart(ProductDetail product) async {
    final success = await context.read<CartProvider>().addToCart(
      productId: product.id,
      quantity: _quantity,
    );

    if (success && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(context.tr('product_added')),
          duration: Duration(seconds: 2),
        ),
      );
    } else if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(context.read<CartProvider>().error ?? context.tr('error')),
          backgroundColor: Colors.red,
        ),
      );
    }
  }
}

class _QuantityButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback? onPressed;

  const _QuantityButton({
    required this.icon,
    this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onPressed,
      child: Container(
        width: 40,
        height: 40,
        decoration: BoxDecoration(
          border: Border.all(color: Colors.grey[300]!),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Icon(icon, size: 20),
      ),
    );
  }
}

class _AttributeRow extends StatelessWidget {
  final String name;
  final String value;

  const _AttributeRow({
    required this.name,
    required this.value,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8.0),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            flex: 2,
            child: Text(
              name,
              style: TextStyle(
                fontSize: 14,
                color: Colors.grey[600],
              ),
            ),
          ),
          Expanded(
            flex: 3,
            child: Text(
              value,
              style: const TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SimilarProductCard extends StatelessWidget {
  final Product product;

  const _SimilarProductCard({required this.product});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () {
        Navigator.pushReplacement(
          context,
          MaterialPageRoute(
            builder: (_) => ProductDetailScreen(slug: product.slug),
          ),
        );
      },
      child: Container(
        width: 140,
        margin: const EdgeInsets.only(right: 12),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: Colors.grey[200]!),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: ClipRRect(
                borderRadius: const BorderRadius.vertical(top: Radius.circular(8)),
                child: (product.mainImageUrl != null || product.videoUrl != null)
                    ? (() {
                        final url = resolveImageUrlOrNull(product.mainImageUrl);
                        return url != null
                            ? CachedNetworkImage(
                                imageUrl: url,
                                fit: BoxFit.cover,
                                width: double.infinity,
                                errorWidget: (_, __, ___) => Container(
                                  color: Colors.grey[200],
                                  child: const Icon(Icons.image_not_supported),
                                ),
                              )
                            : Container(
                                color: Colors.grey[200],
                                child: Center(
                                  child: Icon(Icons.play_circle_fill, size: 48, color: Colors.teal[300]),
                                ),
                              );
                      }())
                    : Container(
                        color: Colors.grey[200],
                        child: const Icon(Icons.image_not_supported),
                      ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(8.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    product.name,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 12),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    formatPriceWithCurrency(product.price, product.currency),
                    style: const TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.bold,
                      color: Colors.teal,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _MediaItem {
  final String? imageUrl;
  final String? videoUrl;
  _MediaItem({this.imageUrl, this.videoUrl});
}

class _VideoPlaceholder extends StatelessWidget {
  final String videoUrl;

  const _VideoPlaceholder({required this.videoUrl});

  @override
  Widget build(BuildContext context) {
    return Container(
      color: Colors.grey[200],
      child: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.play_circle_fill, size: 80, color: Colors.teal[300]),
            const SizedBox(height: 8),
            Text(
              'Видео',
              style: TextStyle(color: Colors.grey[600], fontSize: 16),
            ),
          ],
        ),
      ),
    );
  }
}

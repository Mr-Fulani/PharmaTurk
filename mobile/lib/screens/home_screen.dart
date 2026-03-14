import 'package:flutter/material.dart' hide Banner;
import 'package:provider/provider.dart';
import 'package:cached_network_image/cached_network_image.dart';
import '../utils/image_url.dart';
import '../utils/price_format.dart';
import '../providers/providers.dart';
import '../l10n/app_localizations.dart';
import '../models/models.dart';
import 'product_detail_screen.dart';
import 'catalog_screen.dart';
import 'search_screen.dart';
import 'visual_search_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  String? _lastLocale;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadData();
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final locale = context.read<LocaleProvider>().locale.languageCode;
    if (_lastLocale != null && _lastLocale != locale) {
      _lastLocale = locale;
      WidgetsBinding.instance.addPostFrameCallback((_) => _loadData());
    } else if (_lastLocale == null) {
      _lastLocale = locale;
    }
  }

  Future<void> _loadData() async {
    final catalogProvider = context.read<CatalogProvider>();
    await Future.wait([
      catalogProvider.getBanners(position: 'main'),
      catalogProvider.getFeaturedProducts(),
      catalogProvider.getCategories(topLevel: true),
      catalogProvider.getBrands(),
    ]);
  }

  Future<void> _refresh() async {
    await _loadData();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: CustomScrollView(
          slivers: [
            _buildAppBar(),
            _buildSearchBar(),
            _buildBanners(),
            _buildCategories(),
            _buildFeaturedProducts(),
            _buildBrands(),
            const SliverToBoxAdapter(
              child: SizedBox(height: 32),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAppBar() {
    return SliverAppBar(
      floating: true,
      title: const Text(
        'Turk Export',
        style: TextStyle(
          fontWeight: FontWeight.bold,
          color: Colors.teal,
        ),
      ),
      actions: [
        IconButton(
          icon: const Icon(Icons.notifications_outlined),
          onPressed: () {
            // TODO: Navigate to notifications
          },
        ),
        IconButton(
          icon: const Icon(Icons.favorite_outline),
          onPressed: () {
            // TODO: Navigate to favorites
          },
        ),
      ],
    );
  }

  Widget _buildSearchBar() {
    return SliverToBoxAdapter(
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Row(
          children: [
            Expanded(
              child: GestureDetector(
                onTap: () {
                  showSearch(
                    context: context,
                    delegate: ProductSearchScreen(
                      searchHint: context.tr('search_placeholder'),
                    ),
                  );
                },
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  decoration: BoxDecoration(
                    color: Colors.grey[200],
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Row(
                    children: [
                      Icon(Icons.search, color: Colors.grey[600]),
                      const SizedBox(width: 12),
                      Text(
                        context.tr('search_placeholder'),
                        style: TextStyle(color: Colors.grey[600]),
                      ),
                    ],
                  ),
                ),
              ),
            ),
            const SizedBox(width: 8),
            Material(
              color: Colors.teal,
              borderRadius: BorderRadius.circular(12),
              child: InkWell(
                onTap: () {
                  Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (_) => const VisualSearchScreen(),
                    ),
                  );
                },
                borderRadius: BorderRadius.circular(12),
                child: const Padding(
                  padding: EdgeInsets.all(12),
                  child: Icon(Icons.camera_alt, color: Colors.white),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildBanners() {
    return Consumer<CatalogProvider>(
      builder: (context, provider, child) {
        if (provider.isLoadingBanners) {
          return const SliverToBoxAdapter(
            child: SizedBox(
              height: 180,
              child: Center(child: CircularProgressIndicator()),
            ),
          );
        }

        if (provider.banners.isEmpty) {
          return const SliverToBoxAdapter(child: SizedBox.shrink());
        }

        return SliverToBoxAdapter(
          child: SizedBox(
            height: 180,
            child: PageView.builder(
              itemCount: provider.banners.length,
              itemBuilder: (context, index) {
                final banner = provider.banners[index];
                return _BannerCard(banner: banner);
              },
            ),
          ),
        );
      },
    );
  }

  Widget _buildCategories() {
    return Consumer<CatalogProvider>(
      builder: (context, provider, child) {
        if (provider.isLoadingCategories) {
          return const SliverToBoxAdapter(
            child: SizedBox(
              height: 120,
              child: Center(child: CircularProgressIndicator()),
            ),
          );
        }

        if (provider.categories.isEmpty) {
          return const SliverToBoxAdapter(child: SizedBox.shrink());
        }

        return SliverToBoxAdapter(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.all(16.0),
                child: Text(
                  context.tr('categories'),
                  style: TextStyle(
                    fontSize: 20,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
              SizedBox(
                height: 100,
                child: ListView.builder(
                  scrollDirection: Axis.horizontal,
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  itemCount: provider.categories.length,
                  itemBuilder: (context, index) {
                    final category = provider.categories[index];
                    return _CategoryCard(category: category);
                  },
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildFeaturedProducts() {
    return Consumer<CatalogProvider>(
      builder: (context, provider, child) {
        if (provider.featuredProducts.isEmpty) {
          return const SliverToBoxAdapter(child: SizedBox.shrink());
        }

        return SliverToBoxAdapter(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.all(16.0),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      context.tr('recommended'),
                      style: TextStyle(
                        fontSize: 20,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    TextButton(
                      onPressed: () {
                        Navigator.push(
                          context,
                          MaterialPageRoute(
                            builder: (_) => const CatalogScreen(),
                          ),
                        );
                      },
                      child: Text(context.tr('all')),
                    ),
                  ],
                ),
              ),
              SizedBox(
                height: 280,
                child: ListView.builder(
                  scrollDirection: Axis.horizontal,
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  itemCount: provider.featuredProducts.length,
                  itemBuilder: (context, index) {
                    final product = provider.featuredProducts[index];
                    return _ProductCard(product: product);
                  },
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildBrands() {
    return Consumer<CatalogProvider>(
      builder: (context, provider, child) {
        if (provider.isLoadingBrands) {
          return const SliverToBoxAdapter(child: SizedBox.shrink());
        }

        if (provider.brands.isEmpty) {
          return const SliverToBoxAdapter(child: SizedBox.shrink());
        }

        return SliverToBoxAdapter(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.all(16.0),
                child: Text(
                  context.tr('popular_brands'),
                  style: TextStyle(
                    fontSize: 20,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
              SizedBox(
                height: 80,
                child: ListView.builder(
                  scrollDirection: Axis.horizontal,
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  itemCount: provider.brands.length,
                  itemBuilder: (context, index) {
                    final brand = provider.brands[index];
                    return _BrandCard(brand: brand);
                  },
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _BannerCard extends StatelessWidget {
  final Banner banner;

  const _BannerCard({required this.banner});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () {
        if (banner.linkUrl != null) {
          // TODO: Handle banner click
        }
      },
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 16),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(12),
          color: Colors.grey[300],
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(12),
          child: banner.mainImageUrl != null
              ? CachedNetworkImage(
                  imageUrl: resolveImageUrl(banner.mainImageUrl),
                  fit: BoxFit.cover,
                  width: double.infinity,
                  height: double.infinity,
                  errorWidget: (_, __, ___) => Container(
                    color: Colors.grey[300],
                    child: Center(
                      child: Text(
                        banner.title,
                        style: const TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                  ),
                )
              : Center(
                  child: Text(
                    banner.title,
                    style: const TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
        ),
      ),
    );
  }
}

class _CategoryCard extends StatelessWidget {
  final Category category;

  const _CategoryCard({required this.category});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () {
        Navigator.push(
          context,
          MaterialPageRoute(
            builder: (_) => CatalogScreen(
              categorySlug: category.slug,
              categoryName: category.name,
            ),
          ),
        );
      },
      child: Container(
        width: 80,
        margin: const EdgeInsets.only(right: 12),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ClipOval(
              child: category.cardMediaUrl != null
                  ? CachedNetworkImage(
                      imageUrl: resolveImageUrl(category.cardMediaUrl),
                      width: 56,
                      height: 56,
                      fit: BoxFit.cover,
                      errorWidget: (_, __, ___) => Container(
                        width: 56,
                        height: 56,
                        color: Colors.grey[200],
                        child: const Icon(Icons.category, color: Colors.grey),
                      ),
                    )
                  : Container(
                      width: 56,
                      height: 56,
                      color: Colors.grey[200],
                      child: const Icon(Icons.category, color: Colors.grey),
                    ),
            ),
            const SizedBox(height: 6),
            Flexible(
              child: Text(
                category.name,
                textAlign: TextAlign.center,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 11),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ProductCard extends StatelessWidget {
  final Product product;

  const _ProductCard({required this.product});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () {
        Navigator.push(
          context,
          MaterialPageRoute(
            builder: (_) => ProductDetailScreen(slug: product.slug),
          ),
        );
      },
      child: Container(
        width: 160,
        margin: const EdgeInsets.only(right: 12),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(12),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.05),
              blurRadius: 8,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            ClipRRect(
              borderRadius: const BorderRadius.vertical(top: Radius.circular(12)),
              child: AspectRatio(
                aspectRatio: 1,
                child: (product.mainImageUrl != null || product.videoUrl != null)
                    ? (product.mainImageUrl != null && product.mainImageUrl!.isNotEmpty
                        ? CachedNetworkImage(
                            imageUrl: resolveImageUrl(product.mainImageUrl),
                            fit: BoxFit.cover,
                            placeholder: (_, __) => Container(
                              color: Colors.grey[200],
                              child: const Center(child: CircularProgressIndicator()),
                            ),
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
                          ))
                    : Container(
                        color: Colors.grey[200],
                        child: const Icon(Icons.image_not_supported),
                      ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    product.name,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    formatPriceWithCurrency(product.price, product.currency),
                    style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.bold,
                      color: Colors.teal,
                    ),
                  ),
                  if (product.oldPrice != null)
                    Text(
                      product.oldPriceFormatted ?? '${product.oldPrice} ${product.currency}',
                      style: TextStyle(
                        fontSize: 12,
                        decoration: TextDecoration.lineThrough,
                        color: Colors.grey[600],
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

class _BrandCard extends StatelessWidget {
  final Brand brand;

  const _BrandCard({required this.brand});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () {
        Navigator.push(
          context,
          MaterialPageRoute(
            builder: (_) => CatalogScreen(
              brandId: brand.id,
              brandName: brand.name,
            ),
          ),
        );
      },
      child: Container(
        width: 100,
        margin: const EdgeInsets.only(right: 12),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: Colors.grey[200]!),
        ),
        child: brand.logo != null
            ? ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: CachedNetworkImage(
                  imageUrl: resolveImageUrl(brand.logo),
                  fit: BoxFit.contain,
                  placeholder: (_, __) => Container(
                    color: Colors.grey[100],
                    child: const Center(child: CircularProgressIndicator()),
                  ),
                  errorWidget: (_, __, ___) => Center(
                    child: Text(
                      brand.name,
                      textAlign: TextAlign.center,
                      style: const TextStyle(fontSize: 12),
                    ),
                  ),
                ),
              )
            : Center(
                child: Text(
                  brand.name,
                  textAlign: TextAlign.center,
                  style: const TextStyle(fontSize: 12),
                ),
              ),
      ),
    );
  }
}

import 'package:flutter/material.dart' hide Banner;
import 'package:provider/provider.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:carousel_slider/carousel_slider.dart';
import 'package:flutter/services.dart';
import 'package:video_player/video_player.dart';
import '../utils/image_url.dart';
import '../utils/price_format.dart';
import '../providers/providers.dart';
import '../l10n/app_localizations.dart';
import '../models/models.dart';
import '../services/testimonial_service.dart';
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
      catalogProvider.getBanners(),
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
            _buildBannersAtPosition('main'),
            _sliverGap(24),
            _buildBrands(),
            _buildBannersAtPosition('after_brands'),
            _sliverGap(24),
            _buildCategories(),
            _buildBannersAtPosition('before_footer'),
            _sliverGap(24),
            _buildFeaturedProducts(),
            _buildBannersAtPosition('after_popular_products'),
            _sliverGap(24),
            _buildTestimonials(),
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

  SliverToBoxAdapter _sliverGap(double height) {
    return SliverToBoxAdapter(child: SizedBox(height: height));
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

  Widget _buildBannersAtPosition(String position) {
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

        final bannersWithMedia = provider.banners
            .where((b) =>
                b.position == position &&
                b.mediaFiles != null &&
                b.mediaFiles!.isNotEmpty)
            .toList();
        if (bannersWithMedia.isEmpty) {
          return const SliverToBoxAdapter(child: SizedBox.shrink());
        }

        return SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: SizedBox(
              height: 200,
              child: CarouselSlider.builder(
                itemCount: bannersWithMedia.length,
                itemBuilder: (context, index, _) {
                  return _BannerCard(banner: bannersWithMedia[index]);
                },
                options: CarouselOptions(
                height: 200,
                viewportFraction: 0.92,
                enlargeCenterPage: true,
                enableInfiniteScroll: false,
                autoPlay: true,
                autoPlayInterval: const Duration(seconds: 5),
              ),
            ),
          ),
        ),
        );
      },
    );
  }

  Widget _buildTestimonials() {
    return SliverToBoxAdapter(
      child: FutureBuilder<List<Testimonial>>(
        future: TestimonialService().getTestimonials(),
        builder: (context, snapshot) {
          if (snapshot.hasError) {
            return const SizedBox.shrink();
          }
          final list = snapshot.hasData ? snapshot.data! : <Testimonial>[];
          if (list.isEmpty) {
            return Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    context.tr('reviews'),
                    style: const TextStyle(
                      fontSize: 20,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 12),
                  Text(
                    context.tr('no_reviews'),
                    style: TextStyle(
                      fontSize: 14,
                      color: Colors.grey[600],
                    ),
                  ),
                ],
              ),
            );
          }
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.all(16),
                child: Text(
                  context.tr('reviews'),
                  style: const TextStyle(
                    fontSize: 20,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
              SizedBox(
                height: 140,
                child: ListView.builder(
                  scrollDirection: Axis.horizontal,
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  itemCount: list.length,
                  itemBuilder: (context, i) {
                    final t = list[i];
                    return Container(
                      width: 280,
                      margin: const EdgeInsets.only(right: 12),
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: Colors.grey[100],
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          if (t.authorName.isNotEmpty)
                            Text(
                              t.authorName,
                              style: const TextStyle(
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          const SizedBox(height: 4),
                          Expanded(
                            child: Text(
                              t.content,
                              maxLines: 4,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontSize: 13,
                                color: Colors.grey[700],
                              ),
                            ),
                          ),
                        ],
                      ),
                    );
                  },
                ),
              ),
              const SizedBox(height: 16),
            ],
          );
        },
      ),
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
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
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
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
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
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
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
    final media = banner.mediaFiles ?? [];
    if (media.isEmpty) {
      return _buildFallback(context);
    }

    return GestureDetector(
      onTap: () {
        if (banner.linkUrl != null) {
          // TODO: Handle banner click
        }
      },
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 4),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(12),
          color: Colors.grey[300],
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(12),
          child: media.length == 1
              ? _BannerMediaSlide(
                  url: media.first.file,
                  title: media.first.title ?? banner.title,
                )
              : CarouselSlider.builder(
                  itemCount: media.length,
                  itemBuilder: (context, index, _) {
                    final m = media[index];
                    return _BannerMediaSlide(
                      url: m.file,
                      title: m.title ?? banner.title,
                    );
                  },
                  options: CarouselOptions(
                    height: 200,
                    viewportFraction: 1.0,
                    enableInfiniteScroll: false,
                    autoPlay: media.length > 1,
                    autoPlayInterval: const Duration(seconds: 4),
                  ),
                ),
        ),
      ),
    );
  }

  Widget _buildFallback(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 4),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(12),
        color: Colors.grey[300],
      ),
      child: Center(
        child: Text(
          banner.title,
          style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
        ),
      ),
    );
  }
}

/// Один слайд медиа баннера (изображение или видео).
class _BannerMediaSlide extends StatefulWidget {
  final String url;
  final String title;

  const _BannerMediaSlide({required this.url, required this.title});

  @override
  State<_BannerMediaSlide> createState() => _BannerMediaSlideState();
}

class _BannerMediaSlideState extends State<_BannerMediaSlide> {
  VideoPlayerController? _controller;
  bool _videoError = false;

  @override
  void initState() {
    super.initState();
    final resolved = resolveImageUrlOrNull(widget.url);
    if (resolved != null && isVideoUrl(resolved)) {
      _initVideo(resolved);
    }
  }

  Future<void> _initVideo(String url) async {
    try {
      final ctrl = VideoPlayerController.networkUrl(Uri.parse(url));
      await ctrl.initialize();
      if (mounted) {
        setState(() {
          _controller = ctrl;
          ctrl.setVolume(0); // Без звука по умолчанию
          ctrl.setLooping(true);
          ctrl.play();
        });
      } else {
        ctrl.dispose();
      }
    } on PlatformException catch (_) {
      // iOS симулятор / канал не инициализирован — показываем placeholder
      if (mounted) setState(() => _videoError = true);
    } catch (_) {
      if (mounted) setState(() => _videoError = true);
    }
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final resolved = resolveImageUrlOrNull(widget.url);
    if (resolved == null) {
      return _buildPlaceholder();
    }
    if (isVideoUrl(resolved)) {
      if (_videoError) return _buildVideoPlaceholder();
      if (_controller != null && _controller!.value.isInitialized) {
        return SizedBox.expand(
          child: FittedBox(
            fit: BoxFit.cover,
            child: SizedBox(
              width: _controller!.value.size.width,
              height: _controller!.value.size.height,
              child: VideoPlayer(_controller!),
            ),
          ),
        );
      }
      return _buildVideoPlaceholder();
    }
    return CachedNetworkImage(
      imageUrl: resolved,
      fit: BoxFit.cover,
      width: double.infinity,
      height: double.infinity,
      errorWidget: (_, __, ___) => _buildPlaceholder(),
    );
  }

  Widget _buildPlaceholder() {
    return Center(
      child: Text(
        widget.title,
        style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
        textAlign: TextAlign.center,
      ),
    );
  }

  Widget _buildVideoPlaceholder() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.play_circle_fill, size: 48, color: Colors.teal[300]),
          const SizedBox(height: 8),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Text(
              widget.title,
              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
              textAlign: TextAlign.center,
            ),
          ),
        ],
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
              child: () {
                    final url = resolveImageUrlOrNull(category.cardMediaUrl);
                    return url != null
                        ? CachedNetworkImage(
                            imageUrl: url,
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
                          );
                  }(),
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
                    ? (() {
                        final url = resolveImageUrlOrNull(product.mainImageUrl);
                        return url != null
                            ? CachedNetworkImage(
                                imageUrl: url,
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
                              );
                      }())
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
                  if (hasValidOldPrice(product.oldPrice))
                    Text(
                      formatPriceWithCurrency(product.oldPrice, product.currency),
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

  static bool _isVideoUrl(String? url) {
    if (url == null || url.isEmpty) return false;
    final path = url.split('?').first.toLowerCase();
    return path.endsWith('.mp4') || path.endsWith('.webm') ||
        path.endsWith('.mov') || path.endsWith('.m4v');
  }

  @override
  Widget build(BuildContext context) {
    // cardMediaUrl приоритетнее (как на сайте), fallback на logo
    final mediaUrl = brand.cardMediaUrl ?? brand.logo;
    final url = resolveImageUrlOrNull(mediaUrl);
    final isVideo = _isVideoUrl(mediaUrl);

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
        child: ClipRRect(
          borderRadius: BorderRadius.circular(8),
          child: url != null && !isVideo
              ? CachedNetworkImage(
                  imageUrl: url,
                  fit: BoxFit.contain,
                  width: 100,
                  height: 100,
                  placeholder: (_, __) => Container(
                    color: Colors.grey[100],
                    child: const Center(child: CircularProgressIndicator()),
                  ),
                  errorWidget: (_, __, ___) => _buildFallback(),
                )
              : isVideo && url != null
                  ? Container(
                      color: Colors.grey[200],
                      child: Center(
                        child: Icon(
                          Icons.play_circle_fill,
                          size: 40,
                          color: Colors.teal[300],
                        ),
                      ),
                    )
                  : _buildFallback(),
        ),
      ),
    );
  }

  Widget _buildFallback() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(8),
        child: Text(
          brand.name,
          textAlign: TextAlign.center,
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(fontSize: 12),
        ),
      ),
    );
  }
}

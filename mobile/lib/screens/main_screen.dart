import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/providers.dart';
import '../l10n/app_localizations.dart';
import 'home_screen.dart';
import 'catalog_screen.dart';
import 'cart_screen.dart';
import 'profile_screen.dart';

class MainScreen extends StatefulWidget {
  final int initialIndex;

  const MainScreen({
    super.key,
    this.initialIndex = 0,
  });

  @override
  State<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends State<MainScreen> {
  late int _currentIndex;

  final List<Widget> _screens = [
    const HomeScreen(),
    const CatalogScreen(),
    const CartScreen(),
    const ProfileScreen(),
  ];

  @override
  void initState() {
    super.initState();
    _currentIndex = widget.initialIndex;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<CartProvider>().getCart();
      context.read<FavoriteProvider>().getFavoritesCount();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(
        index: _currentIndex,
        children: _screens,
      ),
      bottomNavigationBar: Consumer2<CartProvider, FavoriteProvider>(
        builder: (context, cartProvider, favoriteProvider, child) {
          return BottomNavigationBar(
            currentIndex: _currentIndex,
            onTap: (index) {
              setState(() {
                _currentIndex = index;
              });
            },
            type: BottomNavigationBarType.fixed,
            selectedItemColor: Colors.teal,
            unselectedItemColor: Colors.grey,
            items: [
              BottomNavigationBarItem(
                icon: const Icon(Icons.home_outlined),
                activeIcon: const Icon(Icons.home),
                label: context.tr('home'),
              ),
              BottomNavigationBarItem(
                icon: const Icon(Icons.category_outlined),
                activeIcon: const Icon(Icons.category),
                label: context.tr('catalog'),
              ),
              BottomNavigationBarItem(
                icon: Badge(
                  isLabelVisible: cartProvider.cartItemCount > 0,
                  label: Text('${cartProvider.cartItemCount}'),
                  child: const Icon(Icons.shopping_cart_outlined),
                ),
                activeIcon: Badge(
                  isLabelVisible: cartProvider.cartItemCount > 0,
                  label: Text('${cartProvider.cartItemCount}'),
                  child: const Icon(Icons.shopping_cart),
                ),
                label: context.tr('cart'),
              ),
              BottomNavigationBarItem(
                icon: const Icon(Icons.person_outline),
                activeIcon: const Icon(Icons.person),
                label: context.tr('profile'),
              ),
            ],
          );
        },
      ),
    );
  }
}

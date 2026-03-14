import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:provider/provider.dart';
import 'services/services.dart';
import 'providers/providers.dart';
import 'screens/screens.dart';
import 'utils/error_logger.dart';
import 'utils/debug_error_overlay.dart';

void main() {
  runZonedGuarded(() async {
    WidgetsFlutterBinding.ensureInitialized();

    // Кастомный экран ошибки — текст можно выделить и копировать
    ErrorWidget.builder = (details) => Material(
      color: Colors.red.shade50,
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: SingleChildScrollView(
            child: SelectionArea(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Ошибка', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Colors.red.shade900)),
                  const SizedBox(height: 8),
                  Text(details.exceptionAsString(), style: const TextStyle(fontSize: 12, fontFamily: 'monospace')),
                ],
              ),
            ),
          ),
        ),
      ),
    );

    FlutterError.onError = (details) {
      FlutterError.presentError(details);
      ErrorLogger.instance.capture(
        details.exception,
        details.stack ?? StackTrace.current,
      );
    };

    await ApiClient().initialize();
    runApp(const MyApp());
  }, (error, stack) {
    ErrorLogger.instance.capture(error, stack);
  });
}

final _navigatorKey = GlobalKey<NavigatorState>();

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => LocaleProvider()),
        ChangeNotifierProvider(create: (_) => AuthProvider()),
        ChangeNotifierProvider(create: (_) => CatalogProvider()),
        ChangeNotifierProvider(create: (_) => CartProvider()),
        ChangeNotifierProvider(create: (_) => FavoriteProvider()),
        ChangeNotifierProvider(create: (_) => OrderProvider()),
        ChangeNotifierProvider(create: (_) => FooterProvider()),
      ],
      child: Consumer<LocaleProvider>(
        builder: (context, localeProvider, _) => MaterialApp(
          key: ValueKey(localeProvider.locale.toString()),
          navigatorKey: _navigatorKey,
          title: 'PharmaTurk',
          debugShowCheckedModeBanner: false,
          locale: localeProvider.locale,
          supportedLocales: const [
            Locale('ru'),
            Locale('en'),
          ],
          localizationsDelegates: const [
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
          ],
          builder: (context, child) => DebugErrorOverlay(
            navigatorKey: _navigatorKey,
            child: child ?? const SizedBox.shrink(),
          ),
          theme: ThemeData(
            colorScheme: ColorScheme.fromSeed(
              seedColor: Colors.teal,
              brightness: Brightness.light,
            ),
            useMaterial3: true,
            appBarTheme: const AppBarTheme(
              centerTitle: true,
              elevation: 0,
            ),
            cardTheme: CardThemeData(
              elevation: 2,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
            elevatedButtonTheme: ElevatedButtonThemeData(
              style: ElevatedButton.styleFrom(
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
            ),
            inputDecorationTheme: InputDecorationTheme(
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
              ),
              filled: true,
              fillColor: Colors.grey[50],
            ),
          ),
          darkTheme: ThemeData(
            colorScheme: ColorScheme.fromSeed(
              seedColor: Colors.teal,
              brightness: Brightness.dark,
            ),
            useMaterial3: true,
          ),
          home: const AppInitializer(),
        ),
      ),
    );
  }
}

class AppInitializer extends StatefulWidget {
  const AppInitializer({super.key});

  @override
  State<AppInitializer> createState() => _AppInitializerState();
}

class _AppInitializerState extends State<AppInitializer> {
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _initialize();
  }

  Future<void> _initialize() async {
    final localeProvider = context.read<LocaleProvider>();
    final authProvider = context.read<AuthProvider>();
    final footerProvider = context.read<FooterProvider>();

    await localeProvider.loadSavedLocale();
    await authProvider.checkAuthStatus();

    if (mounted) {
      localeProvider.syncWithUserLanguage(authProvider.user?.preferredLanguage);
      footerProvider.load();
      setState(() {
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final authProvider = context.watch<AuthProvider>();
    if (authProvider.isAuthenticated && !_isLoading) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          context.read<LocaleProvider>().syncWithUserLanguage(authProvider.user?.preferredLanguage);
        }
      });
    }

    if (_isLoading) {
      return const MaterialApp(
        home: Scaffold(
          body: Center(
            child: CircularProgressIndicator(),
          ),
        ),
      );
    }

    if (authProvider.isAuthenticated) {
      return const MainScreen();
    } else {
      return const LoginScreen();
    }
  }
}

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'error_logger.dart';

/// В debug-режиме показывает кнопку с ошибкой. Нажатие — диалог с копированием.
class DebugErrorOverlay extends StatefulWidget {
  final Widget child;
  final GlobalKey<NavigatorState>? navigatorKey;

  const DebugErrorOverlay({super.key, required this.child, this.navigatorKey});

  @override
  State<DebugErrorOverlay> createState() => _DebugErrorOverlayState();
}

class _DebugErrorOverlayState extends State<DebugErrorOverlay> {
  @override
  void initState() {
    super.initState();
    if (kDebugMode) {
      ErrorLogger.instance.addListener(_onErrorChanged);
    }
  }

  @override
  void dispose() {
    if (kDebugMode) {
      ErrorLogger.instance.removeListener(_onErrorChanged);
    }
    super.dispose();
  }

  void _onErrorChanged() {
    if (mounted) setState(() {});
  }

  void _showErrorDialog() {
    if (!ErrorLogger.instance.hasError) return;

    final navContext = widget.navigatorKey?.currentContext ?? context;
    showDialog(
      context: navContext,
      builder: (context) => AlertDialog(
        title: const Row(
          children: [
            Icon(Icons.error_outline, color: Colors.red),
            SizedBox(width: 8),
            Text('Последняя ошибка'),
          ],
        ),
        content: SingleChildScrollView(
          child: SelectionArea(
            child: Text(
              ErrorLogger.instance.fullText,
              style: const TextStyle(fontFamily: 'monospace', fontSize: 11),
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () {
              ErrorLogger.instance.clear();
              Navigator.pop(context);
              setState(() {});
            },
            child: const Text('Очистить'),
          ),
          FilledButton.icon(
            onPressed: () {
              Clipboard.setData(
                ClipboardData(text: ErrorLogger.instance.fullText),
              );
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Скопировано в буфер обмена')),
              );
            },
            icon: const Icon(Icons.copy),
            label: const Text('Копировать'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!kDebugMode) return widget.child;

    return Stack(
      textDirection: TextDirection.ltr,
      children: [
        widget.child,
        if (ErrorLogger.instance.hasError)
          Positioned(
            top: MediaQuery.of(context).padding.top + 8,
            right: 8,
            child: Material(
              color: Colors.red.shade700,
              borderRadius: BorderRadius.circular(8),
              elevation: 4,
              child: InkWell(
                onTap: _showErrorDialog,
                borderRadius: BorderRadius.circular(8),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  child: const Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.error, color: Colors.white, size: 20),
                      SizedBox(width: 8),
                      Text(
                        'Ошибка — нажмите',
                        style: TextStyle(
                          color: Colors.white,
                          fontWeight: FontWeight.bold,
                          fontSize: 12,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
      ],
    );
  }
}

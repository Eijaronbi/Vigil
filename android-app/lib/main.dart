import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'screens/home_screen.dart';
import 'services/notification_listener.dart';
import 'services/websocket_service.dart';
import 'services/tts_service.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const VigilApp());
}

class VigilApp extends StatefulWidget {
  const VigilApp({super.key});

  @override
  State<VigilApp> createState() => _VigilAppState();
}

class _VigilAppState extends State<VigilApp> {
  final NotificationListenerService _notifService = NotificationListenerService();
  final WebSocketService _wsService = WebSocketService();
  final TTSService _ttsService = TTSService();
  late MethodChannel _methodChannel;
  bool _isListening = false;
  int _alertCount = 0;

  @override
  void initState() {
    super.initState();
    _methodChannel = const MethodChannel('com.vigil.app/notifications');
    _methodChannel.setMethodCallHandler(_handleMethodCall);
    _initServices();
  }

  Future<dynamic> _handleMethodCall(MethodCall call) async {
    if (call.method == 'onNotification') {
      final args = call.arguments as Map<dynamic, dynamic>;
      final app = args['app'] as String? ?? '';
      final title = args['title'] as String?;
      final text = args['text'] as String?;
      _notifService.onNotificationReceived(app, title, text);
      setState(() => _alertCount++);
    }
    return null;
  }

  Future<void> _initServices() async {
    await _ttsService.init();

    _notifService.onNotification((app, title, text) {
      _wsService.sendMessage({
        'source': _mapAppSource(app),
        'group_name': title ?? app,
        'sender': title ?? 'Unknown',
        'text': text ?? '',
        'timestamp': DateTime.now().toIso8601String(),
      });
    });

    _wsService.onAlert((data) {
      final text = data['summary'] ?? data['text'] ?? '';
      if (text.isNotEmpty) {
        _ttsService.speak(text);
      }
    });

    setState(() => _isListening = true);
  }

  String _mapAppSource(String package) {
    if (package.contains('whatsapp')) return 'whatsapp';
    if (package.contains('telegram')) return 'telegram';
    if (package.contains('gm') || package.contains('gmail')) return 'gmail';
    if (package.contains('twitter') || package.contains('x')) return 'twitter';
    return package;
  }

  @override
  void dispose() {
    _wsService.disconnect();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Vigil',
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark().copyWith(
        scaffoldBackgroundColor: const Color(0xFF0A0A0A),
        colorScheme: ColorScheme.dark(
          primary: const Color(0xFF00FF41),
          secondary: const Color(0xFF707070),
          surface: const Color(0xFF111111),
        ),
        textTheme: const TextTheme(
          bodyMedium: TextStyle(fontFamily: 'monospace', color: Color(0xFFE0E0E0)),
        ),
      ),
      home: HomeScreen(
        isListening: _isListening,
        alertCount: _alertCount,
        ttsService: _ttsService,
        wsService: _wsService,
        notifService: _notifService,
      ),
    );
  }
}

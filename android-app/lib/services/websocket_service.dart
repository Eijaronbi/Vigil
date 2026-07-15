import 'dart:async';
import 'dart:convert';
import 'package:web_socket_channel/web_socket_channel.dart';

typedef AlertCallback = void Function(Map<String, dynamic> data);

class WebSocketService {
  WebSocketChannel? _channel;
  AlertCallback? _onAlert;
  Timer? _reconnectTimer;
  Timer? _pingTimer;
  String _url = 'ws://localhost:8002/ws';
  bool _disposed = false;

  void setUrl(String url) {
    _url = url;
  }

  void connect() {
    _disposed = false;
    _doConnect();
  }

  void _doConnect() {
    try {
      _channel?.sink.close();
    } catch (_) {}

    try {
      _channel = WebSocketChannel.connect(Uri.parse(_url));
      _channel!.stream.listen(
        (data) {
          try {
            final parsed = jsonDecode(data as String) as Map<String, dynamic>;
            if (parsed['type'] == 'alert' || parsed['type'] == 'priority_alert') {
              _onAlert?.call(parsed);
            }
          } catch (_) {}
        },
        onDone: () => _scheduleReconnect(),
        onError: (_) => _scheduleReconnect(),
      );
      _startPing();
    } catch (_) {
      _scheduleReconnect();
    }
  }

  void _startPing() {
    _pingTimer?.cancel();
    _pingTimer = Timer.periodic(const Duration(seconds: 25), (_) {
      try {
        _channel?.sink.add('{"type":"ping"}');
      } catch (_) {}
    });
  }

  void _scheduleReconnect() {
    if (_disposed) return;
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(const Duration(seconds: 5), _doConnect);
  }

  void sendMessage(Map<String, dynamic> msg) {
    try {
      _channel?.sink.add(jsonEncode(msg));
    } catch (_) {}
  }

  void onAlert(AlertCallback cb) {
    _onAlert = cb;
  }

  void disconnect() {
    _disposed = true;
    _reconnectTimer?.cancel();
    _pingTimer?.cancel();
    try {
      _channel?.sink.close();
    } catch (_) {}
  }
}

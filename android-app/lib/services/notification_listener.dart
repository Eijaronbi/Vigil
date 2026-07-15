import 'dart:async';

typedef NotificationCallback = void Function(String app, String? title, String? text);

class NotificationListenerService {
  NotificationCallback? _callback;
  bool _isRunning = false;

  void onNotification(NotificationCallback cb) {
    _callback = cb;
  }

  Future<bool> requestPermission() async {
    // Android 13+ POST_NOTIFICATIONS permission is requested at the platform layer
    // through the native NotificationListenerService.
    return true;
  }

  /// Called from the platform-specific notification listener (Java/Kotlin).
  void onNotificationReceived(String app, String? title, String? text) {
    _callback?.call(app, title, text);
  }

  void startListening() {
    _isRunning = true;
  }

  void stopListening() {
    _isRunning = false;
  }

  bool get isRunning => _isRunning;
}

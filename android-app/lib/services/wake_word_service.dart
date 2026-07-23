import 'package:flutter/services.dart';

class WakeWordService {
  static const _channel = MethodChannel('com.vigil.app/wake_word');
  bool _isEnabled = false;

  bool get isEnabled => _isEnabled;

  Future<bool> toggle() async {
    if (_isEnabled) {
      await _channel.invokeMethod('stopWakeWord');
      _isEnabled = false;
    } else {
      try {
        await _channel.invokeMethod('startWakeWord');
        _isEnabled = true;
      } catch (e) {
        _isEnabled = false;
        rethrow;
      }
    }
    return _isEnabled;
  }

  Future<bool> checkPermission() async {
    try {
      final result = await _channel.invokeMethod<bool>('checkAudioPermission');
      return result ?? false;
    } catch (_) {
      return false;
    }
  }
}

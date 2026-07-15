import 'package:flutter_tts/flutter_tts.dart';

class TTSService {
  final FlutterTts _tts = FlutterTts();
  bool _isSpeaking = false;
  bool _initialized = false;

  Future<void> init() async {
    if (_initialized) return;
    await _tts.setLanguage('en-US');
    await _tts.setPitch(1.0);
    await _tts.setSpeechRate(0.5);
    _tts.setCompletionHandler(() => _isSpeaking = false);
    _tts.setErrorHandler((_) => _isSpeaking = false);
    _initialized = true;
  }

  Future<void> speak(String text) async {
    if (_isSpeaking) {
      await _tts.stop();
    }
    _isSpeaking = true;
    await _tts.speak(text);
  }

  Future<void> stop() async {
    await _tts.stop();
    _isSpeaking = false;
  }

  bool get isSpeaking => _isSpeaking;

  void dispose() {
    _tts.stop();
  }
}

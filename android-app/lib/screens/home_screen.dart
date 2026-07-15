import 'package:flutter/material.dart';
import '../services/notification_listener.dart';
import '../services/websocket_service.dart';
import '../services/tts_service.dart';

class HomeScreen extends StatelessWidget {
  final bool isListening;
  final int alertCount;
  final TTSService ttsService;
  final WebSocketService wsService;
  final NotificationListenerService notifService;

  const HomeScreen({
    super.key,
    required this.isListening,
    required this.alertCount,
    required this.ttsService,
    required this.wsService,
    required this.notifService,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Header
              Row(
                children: [
                  Container(
                    width: 12,
                    height: 12,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: isListening
                          ? const Color(0xFF00FF41)
                          : const Color(0xFF707070),
                      boxShadow: isListening
                          ? [
                              BoxShadow(
                                color: const Color(0xFF00FF41).withValues(alpha: 0.5),
                                blurRadius: 8,
                              ),
                            ]
                          : [],
                    ),
                  ),
                  const SizedBox(width: 12),
                  Text(
                    'VIGIL',
                    style: TextStyle(
                      fontFamily: 'monospace',
                      fontSize: 28,
                      fontWeight: FontWeight.bold,
                      color: isListening
                          ? const Color(0xFF00FF41)
                          : const Color(0xFF707070),
                    ),
                  ),
                  const Spacer(),
                  Text(
                    'v1.0',
                    style: TextStyle(
                      fontFamily: 'monospace',
                      color: const Color(0xFF707070).withValues(alpha: 0.5),
                      fontSize: 12,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                'never miss what matters',
                style: TextStyle(
                  fontFamily: 'monospace',
                  fontSize: 12,
                  color: const Color(0xFF707070),
                ),
              ),
              const SizedBox(height: 32),

              // Status card
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: const Color(0xFF111111),
                  border: Border.all(color: const Color(0xFF00FF41).withValues(alpha: 0.3)),
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _statusRow('Status', isListening ? 'Listening' : 'Idle'),
                    const SizedBox(height: 8),
                    _statusRow('Alerts Today', alertCount.toString()),
                    const SizedBox(height: 8),
                    _statusRow('Server', 'ws://localhost:8002/ws'),
                  ],
                ),
              ),
              const SizedBox(height: 24),

              // Controls
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: const Color(0xFF111111),
                  border: Border.all(color: const Color(0xFF707070).withValues(alpha: 0.2)),
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '\$ controls',
                      style: TextStyle(
                        fontFamily: 'monospace',
                        fontSize: 12,
                        color: const Color(0xFF707070),
                      ),
                    ),
                    const SizedBox(height: 12),
                    _controlButton(context, 'Test TTS', () async {
                      await ttsService.speak('Vigil online. Never miss what matters.');
                    }),
                    const SizedBox(height: 8),
                    _controlButton(context, 'Reconnect WS', () {
                      wsService.disconnect();
                      wsService.connect();
                    }),
                  ],
                ),
              ),
              const SizedBox(height: 24),

              // Log
              Expanded(
                child: Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: const Color(0xFF111111),
                    border: Border.all(color: const Color(0xFF707070).withValues(alpha: 0.2)),
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        '\$ log',
                        style: TextStyle(
                          fontFamily: 'monospace',
                          fontSize: 12,
                          color: const Color(0xFF707070),
                        ),
                      ),
                      const SizedBox(height: 8),
                      Expanded(
                        child: Center(
                          child: Text(
                            'Waiting for notifications...',
                            style: TextStyle(
                              fontFamily: 'monospace',
                              fontSize: 13,
                              color: const Color(0xFF707070).withValues(alpha: 0.5),
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _statusRow(String label, String value) {
    return Row(
      children: [
        Text(
          '\$$label ',
          style: TextStyle(
            fontFamily: 'monospace',
            fontSize: 13,
            color: const Color(0xFF00FF41),
          ),
        ),
        Text(
          value,
          style: const TextStyle(
            fontFamily: 'monospace',
            fontSize: 13,
            color: Color(0xFFE0E0E0),
          ),
        ),
      ],
    );
  }

  Widget _controlButton(BuildContext context, String label, VoidCallback onPressed) {
    return SizedBox(
      width: double.infinity,
      child: OutlinedButton(
        onPressed: onPressed,
        style: OutlinedButton.styleFrom(
          foregroundColor: const Color(0xFF00FF41),
          side: BorderSide(color: const Color(0xFF00FF41).withValues(alpha: 0.5)),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
          padding: const EdgeInsets.symmetric(vertical: 12),
        ),
        child: Text(
          '\$ $label',
          style: const TextStyle(fontFamily: 'monospace', fontSize: 13),
        ),
      ),
    );
  }
}

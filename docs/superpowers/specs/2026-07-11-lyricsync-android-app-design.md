# LyricSync — Android Auto-Lyrics App Design

## Overview

An Android app that automatically detects what music is playing (even with screen locked), fetches or transcribes the lyrics, and displays them on the lockscreen via notification + optional floating overlay.

## Tech Stack

| Decision | Choice |
|---|---|
| Language | Kotlin |
| UI | Jetpack Compose |
| Min SDK | 29 (Android 10) |
| Target SDK | 34 (Android 14) |
| Architecture | Clean MVVM with modular Gradle modules |
| DI | Hilt |
| Networking | Retrofit + OkHttp + Kotlinx Serialization |
| Local DB | Room |
| Async | Kotlin Coroutines + Flow |
| Fingerprinting | ACRCloud SDK |
| Transcription | Whisper.cpp via JNI (on-device) |
| YouTube captions | Data API v3 (search) + timedtext API (captions) |

## Module Structure

```
LyricSync/
├── app/                          # Application, DI, Navigation, Settings
├── core/                         # Shared models, DB, utils
└── feature/
    ├── song-detection/           # NotificationListener + fingerprinting
    ├── lyrics/                   # YouTube captions + transcription + repository
    └── display/                  # Notification + overlay UI
```

## Data Flow

```
Media notification → NotificationListenerService → extract (title, artist)
    ↓ (no metadata)
AudioRecord (10s) → ACRCloud fingerprint → song identification
    ↓
Room DB cache lookup → hit? → serve lyrics immediately
    ↓ miss
YouTube Data API v3 search → get videoId → youtube.com/api/timedtext → parse captions
    ↓ no captions
ForegroundService → AudioRecord stream → Whisper.cpp (JNI) → transcribed text + timestamps
    ↓
Store lyrics + timestamps in Room → display via notification + overlay
```

## Components

### song-detection module

- **MediaNotificationListener** (`NotificationListenerService`): Listens for `EXTRA_MEDIA_SESSION` notifications. Extracts `METADATA_KEY_TITLE`, `METADATA_KEY_ARTIST`, `METADATA_KEY_ALBUM`, `METADATA_KEY_ART`. Publishes `SongDetectedEvent` to the repository.
- **AudioFingerprinter**: Uses `AudioRecord` to capture 10s of audio. Sends to ACRCloud SDK for fingerprint matching. Returns identified `SongInfo`.
- **SongDetector**: Facade that first tries notification metadata. If unavailable within 5s, starts fingerprinting.

### lyrics module

- **YouTubeCaptionFetcher**: 
  - Search: `GET https://www.googleapis.com/youtube/v3/search?q={title}+{artist}&part=snippet&type=video`
  - Captions: `GET https://www.youtube.com/api/timedtext?v={videoId}&fmt=json3`
  - Parses JSON3 format into `List<LyricLine>` with timestamps
  - Filters: prefers English captions, auto-generated OK
- **TranscriptionEngine**:
  - Captures audio via `AudioRecord` in 30s chunks
  - Passes PCM data to Whisper.cpp native library via JNI
  - Returns transcribed text with word-level timestamps
  - Runs on a background coroutine (Dispatchers.IO)
- **LyricsRepository**:
  - `getLyrics(title, artist): Flow<LyricsResult>`
  - Strategy: cache → YouTube → transcription
  - Saves results to Room DB after fetch
  - Emits progress states (Loading, Cached, YouTube, Transcribing, Error)

### display module

- **LyricNotificationBuilder**:
  - Builds `NotificationCompat.Builder` with `MediaStyle`
  - Expanded layout uses `RemoteViews` showing 5 lyric lines
  - Lines highlight based on elapsed time (synced via playback position from media session)
  - Collapsed: shows title, artist, album art
- **LyricOverlayComposable**:
  - Rendered via `Dialog` with `TYPE_APPLICATION_OVERLAY`
  - Semi-transparent dark background (60% opacity)
  - Full lyrics as scrollable text, auto-scrolls to current line
  - Tap anywhere → dismiss overlay; double-tap → toggle pause/resume
- **LyricSyncService**:
  - `ForegroundService` with persistent notification
  - Manages detection lifecycle
  - Coordinates between song-detection, lyrics, and display

### core module

- **Room Database**:
  - `songs(id TEXT PK, title, artist, source TEXT, duration_ms, created_at, updated_at)`
  - `lyric_lines(id INTEGER PK AUTOINCREMENT, song_id FK, sequence INT, text, start_ms, end_ms)`
  - Index: `(title, artist)` composite
- **Models**: `SongInfo`, `LyricLine`, `LyricsResult(sealed class)`, `DetectionResult`
- **DI Modules**: Hilt modules for Retrofit, Room, ACRCloud, Whisper
- **Extensions**: Date/Time utils, Flow utils, Context extensions

## Permissions

| Permission | Type | Purpose |
|---|---|---|
| `BIND_NOTIFICATION_LISTENER_SERVICE` | System setting | Read media notifications |
| `RECORD_AUDIO` | Runtime | Microphone for transcription + fingerprinting |
| `SYSTEM_ALERT_WINDOW` | Runtime | Overlay mode |
| `POST_NOTIFICATIONS` | Runtime (13+) | Show notifications |
| `FOREGROUND_SERVICE` | Manifest | Background service |
| `INTERNET` | Manifest | API calls |

## UI Screens

1. **Main Activity**: Settings hub
   - Enable/disable detection toggle
   - Recent songs list (from cache)
   - Tap song → view full lyrics
   - Permission status indicators
2. **Lockscreen notification**: Auto-shown when song detected
   - Collapsed: album art + title + artist
   - Expanded: 5 synced lyric lines
3. **Overlay**: Optional floating lyrics
   - Full lyrics, auto-scrolling
   - Accessed via notification action button

## Error Handling

| Scenario | Behavior |
|---|---|
| No notification permission | Prompt to enable in settings, show guide |
| No notification metadata | Auto-start fingerprinting |
| Fingerprinting fails | Show "Could not identify song" in notification |
| YouTube fetch fails (no network) | Skip to transcription if recording; else show cached if any |
| YouTube no captions | Auto-start transcription |
| Transcription fails (noisy audio) | Log failure, show "Lyrics unavailable" |
| Overlay permission denied | Disable overlay toggle, prompt once |
| No internet + no cache | Show "No lyrics available" with retry button |

## Success Criteria

- Song detected within 5s of playback start
- YouTube captions fetched within 3s
- Transcription delivers first lines within 10s
- Lyrics appear on lockscreen without user interaction
- Cached songs serve instantly offline
- App battery usage stays under 5% per hour of music playback

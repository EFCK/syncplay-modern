"""Fork-local translations for syncplay-modern UI strings.

Upstream `syncplay/messages*.py` covers protocol notifications, server
errors, and the console UI. The PySide6 modern UI introduces its own
labels (menus, sidebar tabs, settings rows, onboarding fields) that
don't exist upstream. Holding those translations here — instead of
appending keys to `messages_en.py` / `messages_tr.py` / etc. — keeps
the upstream files untouched, so future upstream merges don't
conflict, and a missing modern translation quietly falls back to
English without breaking upstream code paths.

The active language code is the same one upstream tracks
(``messages.messages["CURRENT"]``). Calling
``syncplay.messages.setLanguage(code)`` switches both upstream
notifications and modern-UI labels in lockstep.

Priming happens once at import time: if the upstream tracker has no
language set yet (the user hasn't been through ConfigurationGetter or
hasn't picked an explicit language), we set it to the OS-detected
language so the very first `tr()` call already returns the right
string. After that, `tr()` is a pure read — no global mutation per
lookup.
"""

from __future__ import annotations

from syncplay import messages as _upstream


_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        # Window / dialog titles
        "window-title": "syncplay-modern",
        "settings-window-title": "Settings",
        "playback-window-title": "Playback",
        "connect-window-title": "Connect to a Syncplay room",

        # Menu bar
        "menu-file": "&File",
        "menu-open-file": "&Open File…",
        "menu-open-url": "Open &URL…",
        "menu-quit": "&Quit",
        "menu-playback": "&Playback",
        "menu-audio-subs": "&Audio && Subtitles…",
        "menu-settings": "&Settings",
        "menu-preferences": "&Preferences…",

        # Sidebar tabs
        "tab-room": "Room",
        "tab-chat": "Chat",
        "tab-queue": "Queue",
        "tab-errors": "Errors",

        # Chat / room panels
        "chat-placeholder": "Send a message…",
        "room-label": "Room: {room}",
        "room-none": "(no room)",
        "ready-join": "Ready (join sync)",
        "ready-leave": "Not Ready (watch alone)",
        "room-col-user": "User",
        "room-col-file": "File",
        "room-activity": "Activity",
        "ready-needs-file": "Open a video file before marking yourself ready",

        # Onboarding dialog
        "onb-nickname": "Nickname",
        "onb-nickname-ph": "Your nickname",
        "onb-server": "Server",
        "onb-port": "Port",
        "onb-room": "Room",
        "onb-room-ph": "Room name (any string)",
        "onb-password": "Server password",
        "onb-password-ph": "Optional",
        "onb-vlc-path": "VLC location",
        "onb-vlc-path-ph": "auto-detect",
        "onb-browse": "Browse…",
        "onb-vlc-hint-default": "Only set this if VLC isn't installed in the default location.",
        "onb-vlc-hint-missing": "Folder doesn't exist.",
        "onb-vlc-hint-ok": "Looks like a VLC install.",
        "onb-vlc-hint-unknown": "Couldn't find libvlc here — saving anyway; loader will surface the real error.",
        "onb-run": "Run",
        "onb-run-tip": "Use these values for this session only; don't change the saved config.",
        "onb-save-run": "Update Config and Run",
        "onb-save-run-tip": "Save these values to the config and use them for this session.",
        "onb-missing-title": "Missing fields",
        "onb-missing-body": "Nickname, server, and room are all required.",
        "onb-bad-port-title": "Invalid port",
        "onb-bad-port-body": "Port must be a number between 1 and 65535.",

        # Queue panel
        "queue-empty-hint":
            "Drag a video file here or click “Add file…” to "
            "start a shared queue. Items are visible to everyone in the room.",
        "queue-add-btn": "Add file…",
        "queue-add-dialog-title": "Add files to playlist",
        "queue-play-this": "Play this",
        "queue-remove": "Remove from queue",

        # Errors panel
        "errors-clear": "Clear",

        # File-open dialogs
        "open-media-title": "Open Media",
        "open-media-filter":
            "Media files (*.mkv *.mp4 *.avi *.mov *.webm *.m4v *.flv *.wmv *.mpg *.mpeg *.ts);;All files (*)",
        "open-url-title": "Open URL",
        "open-url-prompt": "Stream URL:",

        # Chat toggle button
        "chat-show": "Show chat",
        "chat-hide": "Hide chat",

        # Ready-gating toast
        "waiting-ready-one": "Waiting for 1 user to ready up",
        "waiting-ready-many": "Waiting for {n} users to ready up",

        # Brief-status toasts triggered by keyboard shortcuts
        "toast-seek": "Seek {sign}{seconds}s",
        "toast-volume": "Volume {percent}%",
        "toast-muted": "Muted",
        "toast-unmuted": "Unmuted",
        "toast-audio-delay": "Audio delay {ms:+d} ms",
        "toast-subtitle-delay": "Subtitle delay {ms:+d} ms",
        "toast-audio-track": "Audio: {label}",
        "toast-subtitle-track": "Subtitle: {label}",
        "toast-audio-change-fail": "Audio change failed: {error}",
        "toast-audio-rejected": "Audio change rejected by libvlc (id={track_id})",
        "toast-subtitle-change-fail": "Subtitle change failed: {error}",
        "toast-subtitle-rejected": "Subtitle change rejected by libvlc (id={track_id})",
        "toast-speed": "Speed {rate:.2f}x",
        "toast-speed-reset": "Speed 1.00x",

        # Video controls
        "vc-play-pause": "Play / Pause",
        "vc-mute": "Mute",
        "vc-fullscreen": "Fullscreen",

        # Settings dialog — tabs
        "settings-tab-connection": "Connection",
        "settings-tab-sync": "Sync",
        "settings-tab-behavior": "Behavior",
        "settings-tab-privacy": "Privacy",
        "settings-tab-notifications": "Notifications",
        "settings-tab-language": "Language",

        # Settings dialog — Connection tab
        "settings-server": "Server",
        "settings-nickname": "Nickname",
        "settings-default-room": "Default room",
        "settings-connection-note":
            "These four values are set on the connect screen. Changing them "
            "requires reconnecting — relaunch the app to pick up a new value.",

        # Settings dialog — Sync tab
        "settings-sync-intro":
            "When peers drift apart in playback position, Syncplay nudges "
            "your speed/position to bring you back in line. Tune that here.",
        "settings-row-slow-down": "Slow down",
        "settings-row-rewind": "Rewind",
        "settings-row-fastforward": "Fast-forward",
        "settings-row-drift-weighting": "Drift weighting",
        "settings-row-slowdown-kickin": "Slowdown kick-in",
        "settings-row-rewind-threshold": "Rewind threshold",
        "settings-row-ff-threshold": "Fast-forward threshold",
        "settings-bool-slow-on-desync": "Slow down when ahead of others",
        "settings-bool-rewind-on-desync": "Rewind if I'm too far ahead",
        "settings-bool-fastfwd-on-desync": "Fast-forward if I'm too far behind",
        "settings-bool-dont-slow-down":
            "Don't slow down on my account (others ignore me when computing position)",

        # Settings dialog — Behavior tab
        "settings-row-readiness": "Readiness",
        "settings-row-on-leave": "On leave",
        "settings-row-when-play": "When I press play",
        "settings-row-min-users": "Min users for autoplay",
        "settings-row-autoplay-safety": "Autoplay safety",
        "settings-row-playlist": "Playlist",
        "settings-bool-ready-at-start": "Mark me ready at startup",
        "settings-bool-pause-on-leave": "Pause when someone leaves the room",
        "settings-info-unpause": "Playback starts when every user in the room is ready.",
        "settings-bool-autoplay-same-files":
            "Require everyone to have the same filename to autoplay",
        "settings-bool-shared-playlist": "Enable shared playlist (room-wide queue)",
        "settings-bool-loop-playlist": "Loop the playlist when the last item ends",
        "settings-bool-loop-single": "Loop the current file when it ends",

        # Settings dialog — Privacy tab
        "settings-privacy-intro":
            "Syncplay normally tells the room what file (name, size, duration) "
            "you have loaded so it can verify everyone watches the same thing. "
            "If you'd rather not share the raw values, switch to hashed (the "
            "room can only see whether files match) or disabled (no info at all).",
        "settings-row-filename-priv": "Filename privacy",
        "settings-row-filesize-priv": "File size privacy",
        "settings-row-trusted-domains": "Trusted domains",
        "settings-bool-only-trusted":
            "Only auto-switch to URLs on the trusted domains list below",
        "settings-trusted-domains-placeholder": "one domain per line",
        "settings-priv-raw": "Send actual value",
        "settings-priv-hashed": "Send hashed value",
        "settings-priv-disabled": "Don't send at all",

        # Settings dialog — Notifications tab
        "settings-notif-intro":
            "Toasts and on-screen-display warnings. The default fork "
            "behaviour is quiet — flip these on if you want more nagging.",
        "settings-row-osd-master": "OSD master",
        "settings-row-warnings": "Warnings",
        "settings-row-sync-events": "Sync events",
        "settings-row-same-room": "Same-room events",
        "settings-row-cross-room": "Cross-room events",
        "settings-row-non-controller": "Non-controller events",
        "settings-row-duration": "Duration mismatch",
        "settings-row-fullscreen-autohide": "Fullscreen chat auto-hide",
        "settings-bool-show-osd": "Show on-screen overlay messages at all",
        "settings-bool-show-warnings": "Show warning toasts",
        "settings-bool-show-slowdown": "Show slowdown / speedup events",
        "settings-bool-show-same-room": "Show events from users in my room",
        "settings-bool-show-diff-room": "Show events from other rooms",
        "settings-bool-show-non-controller": "Show events triggered by non-controllers",
        "settings-bool-duration-notif":
            "Notify me when file durations don't match across the room",

        # Settings dialog — Language tab
        "settings-language-intro":
            "Choose the language used for menus, settings, and Syncplay "
            "notifications. \"Auto-detect\" follows your operating system.",
        "settings-language-label": "Language",
        "settings-language-auto": "Auto-detect (system: {name})",
        "settings-language-restart-note":
            "Some labels update immediately; a few only refresh after the next launch.",

        # Playback dialog
        "playback-row-audio": "Audio track",
        "playback-row-subtitle": "Subtitle track",
        "playback-row-sub-delay": "Subtitle delay",
        "playback-row-chat-overlay": "Chat overlay",
        "playback-reset": "Reset",
        "playback-chat-on-video": "Show chat on video",
    },
    "tr": {
        # Window / dialog titles
        "window-title": "syncplay-modern",
        "settings-window-title": "Ayarlar",
        "playback-window-title": "Oynatma",
        "connect-window-title": "Bir Syncplay odasına bağlan",

        # Menu bar
        "menu-file": "&Dosya",
        "menu-open-file": "Dosya &Aç…",
        "menu-open-url": "&URL Aç…",
        "menu-quit": "&Çıkış",
        "menu-playback": "&Oynatma",
        "menu-audio-subs": "&Ses && Altyazı…",
        "menu-settings": "&Ayarlar",
        "menu-preferences": "&Tercihler…",

        # Sidebar tabs
        "tab-room": "Oda",
        "tab-chat": "Sohbet",
        "tab-queue": "Sıra",
        "tab-errors": "Hatalar",

        # Chat / room panels
        "chat-placeholder": "Bir mesaj gönder…",
        "room-label": "Oda: {room}",
        "room-none": "(oda yok)",
        "ready-join": "Hazır (senkrona katıl)",
        "ready-leave": "Hazır değil (tek başına izle)",
        "room-col-user": "Kullanıcı",
        "room-col-file": "Dosya",
        "room-activity": "Etkinlik",
        "ready-needs-file": "Hazır olarak işaretlemeden önce bir video dosyası aç",

        # Onboarding dialog
        "onb-nickname": "Takma ad",
        "onb-nickname-ph": "Takma adınız",
        "onb-server": "Sunucu",
        "onb-port": "Bağlantı noktası",
        "onb-room": "Oda",
        "onb-room-ph": "Oda adı (herhangi bir metin)",
        "onb-password": "Sunucu parolası",
        "onb-password-ph": "İsteğe bağlı",
        "onb-vlc-path": "VLC konumu",
        "onb-vlc-path-ph": "otomatik algıla",
        "onb-browse": "Gözat…",
        "onb-vlc-hint-default": "Yalnızca VLC varsayılan konumda kurulu değilse ayarlayın.",
        "onb-vlc-hint-missing": "Klasör bulunamadı.",
        "onb-vlc-hint-ok": "Bir VLC kurulumuna benziyor.",
        "onb-vlc-hint-unknown": "Burada libvlc bulunamadı — yine de kaydediliyor; gerçek hatayı yükleyici gösterecek.",
        "onb-run": "Çalıştır",
        "onb-run-tip": "Bu değerleri yalnızca bu oturum için kullan; kayıtlı yapılandırmayı değiştirme.",
        "onb-save-run": "Yapılandırmayı Güncelle ve Çalıştır",
        "onb-save-run-tip": "Bu değerleri yapılandırmaya kaydet ve bu oturum için kullan.",
        "onb-missing-title": "Eksik alanlar",
        "onb-missing-body": "Takma ad, sunucu ve oda alanlarının tümü zorunludur.",
        "onb-bad-port-title": "Geçersiz bağlantı noktası",
        "onb-bad-port-body": "Bağlantı noktası 1 ile 65535 arasında bir sayı olmalıdır.",

        # Queue panel
        "queue-empty-hint":
            "Buraya bir video dosyası sürükleyin veya “Dosya ekle…” düğmesine tıklayarak "
            "ortak bir sıra başlatın. Öğeler odadaki herkese görünür.",
        "queue-add-btn": "Dosya ekle…",
        "queue-add-dialog-title": "Çalma listesine dosya ekle",
        "queue-play-this": "Bunu oynat",
        "queue-remove": "Sıradan kaldır",

        # Errors panel
        "errors-clear": "Temizle",

        # File-open dialogs
        "open-media-title": "Ortam Aç",
        "open-media-filter":
            "Ortam dosyaları (*.mkv *.mp4 *.avi *.mov *.webm *.m4v *.flv *.wmv *.mpg *.mpeg *.ts);;Tüm dosyalar (*)",
        "open-url-title": "URL Aç",
        "open-url-prompt": "Akış URL'si:",

        # Chat toggle button
        "chat-show": "Sohbeti göster",
        "chat-hide": "Sohbeti gizle",

        # Ready-gating toast
        "waiting-ready-one": "1 kullanıcının hazır olması bekleniyor",
        "waiting-ready-many": "{n} kullanıcının hazır olması bekleniyor",

        # Brief-status toasts triggered by keyboard shortcuts
        "toast-seek": "Atla {sign}{seconds}s",
        "toast-volume": "Ses %{percent}",
        "toast-muted": "Sessiz",
        "toast-unmuted": "Ses açık",
        "toast-audio-delay": "Ses gecikmesi {ms:+d} ms",
        "toast-subtitle-delay": "Altyazı gecikmesi {ms:+d} ms",
        "toast-audio-track": "Ses: {label}",
        "toast-subtitle-track": "Altyazı: {label}",
        "toast-audio-change-fail": "Ses değişikliği başarısız: {error}",
        "toast-audio-rejected": "libvlc ses değişikliğini reddetti (id={track_id})",
        "toast-subtitle-change-fail": "Altyazı değişikliği başarısız: {error}",
        "toast-subtitle-rejected": "libvlc altyazı değişikliğini reddetti (id={track_id})",
        "toast-speed": "Hız {rate:.2f}x",
        "toast-speed-reset": "Hız 1.00x",

        # Video controls
        "vc-play-pause": "Oynat / Duraklat",
        "vc-mute": "Sessize al",
        "vc-fullscreen": "Tam ekran",

        # Settings dialog — tabs
        "settings-tab-connection": "Bağlantı",
        "settings-tab-sync": "Senkron",
        "settings-tab-behavior": "Davranış",
        "settings-tab-privacy": "Gizlilik",
        "settings-tab-notifications": "Bildirimler",
        "settings-tab-language": "Dil",

        # Settings dialog — Connection tab
        "settings-server": "Sunucu",
        "settings-nickname": "Takma ad",
        "settings-default-room": "Varsayılan oda",
        "settings-connection-note":
            "Bu dört değer bağlantı ekranında belirlenir. Değiştirmek için "
            "yeniden bağlanmak gerekir — yeni değeri uygulamak için uygulamayı yeniden başlatın.",

        # Settings dialog — Sync tab
        "settings-sync-intro":
            "Diğerleriyle oynatma konumun farklılaştığında Syncplay "
            "hızını/konumunu hizalamak için ayarlar. Buradan ince ayar yap.",
        "settings-row-slow-down": "Yavaşla",
        "settings-row-rewind": "Geri sar",
        "settings-row-fastforward": "İleri sar",
        "settings-row-drift-weighting": "Sapma ağırlığı",
        "settings-row-slowdown-kickin": "Yavaşlama eşiği",
        "settings-row-rewind-threshold": "Geri sarma eşiği",
        "settings-row-ff-threshold": "İleri sarma eşiği",
        "settings-bool-slow-on-desync": "Diğerlerinin önündeysem yavaşla",
        "settings-bool-rewind-on-desync": "Çok ileridesem geri sar",
        "settings-bool-fastfwd-on-desync": "Çok geridysem ileri sar",
        "settings-bool-dont-slow-down":
            "Benim yüzümden yavaşlama (diğerleri konumu hesaplarken beni yok sayar)",

        # Settings dialog — Behavior tab
        "settings-row-readiness": "Hazır olma",
        "settings-row-on-leave": "Ayrılma davranışı",
        "settings-row-when-play": "Oynat'a bastığımda",
        "settings-row-min-users": "Otomatik oynatma için min kullanıcı",
        "settings-row-autoplay-safety": "Otomatik oynatma güvenliği",
        "settings-row-playlist": "Çalma listesi",
        "settings-bool-ready-at-start": "Başlangıçta beni hazır olarak işaretle",
        "settings-bool-pause-on-leave": "Odadan biri ayrıldığında duraklat",
        "settings-info-unpause": "Oynatma, odadaki tüm kullanıcılar hazır olunca başlar.",
        "settings-bool-autoplay-same-files":
            "Otomatik oynatmak için herkesin aynı dosya adına sahip olması gereksin",
        "settings-bool-shared-playlist": "Ortak çalma listesini etkinleştir (oda genelinde sıra)",
        "settings-bool-loop-playlist": "Son öğe bitince çalma listesini başa sar",
        "settings-bool-loop-single": "Geçerli dosya bitince başa sar",

        # Settings dialog — Privacy tab
        "settings-privacy-intro":
            "Syncplay normalde odadaki herkese yüklediğin dosyanın adını, "
            "boyutunu ve süresini bildirir; böylece herkesin aynı şeyi izlediği "
            "doğrulanır. Ham değerleri paylaşmak istemiyorsan karma değere geç "
            "(oda yalnızca dosyaların eşleşip eşleşmediğini görür) ya da hiç "
            "paylaşma (hiçbir bilgi gönderilmez).",
        "settings-row-filename-priv": "Dosya adı gizliliği",
        "settings-row-filesize-priv": "Dosya boyutu gizliliği",
        "settings-row-trusted-domains": "Güvenilir alanlar",
        "settings-bool-only-trusted":
            "URL'lere yalnızca aşağıdaki güvenilir alanlar listesindekilere otomatik geç",
        "settings-trusted-domains-placeholder": "her satıra bir alan",
        "settings-priv-raw": "Gerçek değeri gönder",
        "settings-priv-hashed": "Karma değer gönder",
        "settings-priv-disabled": "Hiç gönderme",

        # Settings dialog — Notifications tab
        "settings-notif-intro":
            "Bildirim baloncukları ve ekran üstü uyarılar. Bu sürümün varsayılanı "
            "sessizdir — daha fazla bildirim istiyorsan açabilirsin.",
        "settings-row-osd-master": "OSD ana anahtarı",
        "settings-row-warnings": "Uyarılar",
        "settings-row-sync-events": "Senkron olayları",
        "settings-row-same-room": "Aynı oda olayları",
        "settings-row-cross-room": "Diğer oda olayları",
        "settings-row-non-controller": "Denetleyici olmayan olaylar",
        "settings-row-duration": "Süre uyumsuzluğu",
        "settings-row-fullscreen-autohide": "Tam ekran sohbet oto-gizle",
        "settings-bool-show-osd": "Ekran üstü mesajları hiç göster",
        "settings-bool-show-warnings": "Uyarı bildirimlerini göster",
        "settings-bool-show-slowdown": "Yavaşlama / hızlanma olaylarını göster",
        "settings-bool-show-same-room": "Odamdaki kullanıcıların olaylarını göster",
        "settings-bool-show-diff-room": "Diğer odalardaki olayları göster",
        "settings-bool-show-non-controller": "Denetleyici olmayanların tetiklediği olayları göster",
        "settings-bool-duration-notif":
            "Odadaki dosya süreleri eşleşmediğinde beni uyar",

        # Settings dialog — Language tab
        "settings-language-intro":
            "Menüler, ayarlar ve Syncplay bildirimleri için kullanılacak "
            "dili seçin. \"Otomatik algıla\" işletim sisteminizi takip eder.",
        "settings-language-label": "Dil",
        "settings-language-auto": "Otomatik algıla (sistem: {name})",
        "settings-language-restart-note":
            "Bazı etiketler hemen güncellenir; bir kısmı yalnızca bir sonraki açılışta yenilenir.",

        # Playback dialog
        "playback-row-audio": "Ses parçası",
        "playback-row-subtitle": "Altyazı parçası",
        "playback-row-sub-delay": "Altyazı gecikmesi",
        "playback-row-chat-overlay": "Sohbet bindirmesi",
        "playback-reset": "Sıfırla",
        "playback-chat-on-video": "Sohbeti videonun üzerinde göster",
    },
}


# True iff the user picked "Auto-detect" (or hasn't picked yet); flipped
# off by an explicit `set_language(code)` call. Kept so the settings tab
# can render the right initial combo selection without re-reading the
# INI, and so we don't lose the user's "follow the OS" intent when the
# detected code is mid-session pushed into upstream's tracker.
_auto_detect_active = True


def _prime_default_language() -> None:
    """Ensure upstream's tracker has *some* valid language at import time.

    Runs once at module import. If ConfigurationGetter has already
    primed the tracker with the user's saved choice, this is a no-op.
    Otherwise we auto-detect and stash the OS language so the first
    `tr()` call already returns localized strings.
    """
    current = _upstream.messages.get("CURRENT")
    if current and _upstream.isValidLanguage(current):
        return
    _upstream.setLanguage(_upstream.getInitialLanguage())


_prime_default_language()


def current_language() -> str:
    """Return the active language code (e.g. ``"en"``, ``"tr"``)."""
    lang = _upstream.messages.get("CURRENT")
    if lang and _upstream.isValidLanguage(lang):
        return lang
    return "en"


def tr(key: str, **fmt: object) -> str:
    """Translate ``key`` for the active language, falling back to English.

    Unknown keys are returned verbatim — surfacing the key in the UI
    makes a missing translation obvious during development without
    crashing the app. Format errors fall through to the raw template
    so a stray ``{`` in a localized string never crashes a render.
    """
    lang = current_language()
    bundle = _STRINGS.get(lang)
    text: str | None = None
    if bundle is not None:
        text = bundle.get(key)
    if text is None:
        text = _STRINGS["en"].get(key, key)
    if fmt:
        try:
            return text.format(**fmt)
        except (KeyError, IndexError, ValueError):
            return text
    return text


def available_languages() -> dict[str, str]:
    """Return ``{code: native-name}`` for every language upstream supports.

    Modern-UI strings for languages without an entry in ``_STRINGS``
    fall through to English; the language code is still selectable so
    upstream chat / notification strings can be localized.
    """
    out: dict[str, str] = {}
    for code, native in _upstream.getLanguages().items():
        out[code] = native
    return out


def system_language() -> str:
    """OS-detected language code (matches what auto-detect would pick)."""
    return _upstream.getInitialLanguage()


def set_language(code: str) -> None:
    """Update the active language for both upstream and modern strings.

    An empty / unknown ``code`` is treated as "follow the OS": we apply
    the auto-detected code to upstream's tracker right now (so the rest
    of the session is rendered correctly) and remember that the user's
    intent was auto-detect, so the settings combo can re-select the
    "Auto" entry without having to re-read the INI.
    """
    global _auto_detect_active
    if not code or not _upstream.isValidLanguage(code):
        _auto_detect_active = True
        code = _upstream.getInitialLanguage()
    else:
        _auto_detect_active = False
    _upstream.setLanguage(code)


def is_auto_detect_active() -> bool:
    """True iff the active language was selected by auto-detection."""
    return _auto_detect_active

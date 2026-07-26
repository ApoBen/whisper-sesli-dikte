import sys
import os
import subprocess
import selectors
import urllib.request
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QTextEdit, QComboBox, 
                             QLabel, QProgressBar, QCheckBox, QSystemTrayIcon, 
                             QMenu, QGraphicsDropShadowEffect)
from PySide6.QtCore import Qt, QThread, Signal, Slot, QTimer
from PySide6.QtGui import QIcon, QColor, QFont, QPalette

from recorder import AudioRecorder
from transcriber import TranscriberThread

# Global F9 Keyboard Listener Thread using evdev
class GlobalF9Listener(QThread):
    f9_pressed = Signal()

    def run(self):
        try:
            import evdev
        except ImportError:
            print("evdev module not found, global shortcut disabled.")
            return

        devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
        keyboards = []
        for dev in devices:
            try:
                capabilities = dev.capabilities()
                if evdev.ecodes.EV_KEY in capabilities:
                    if evdev.ecodes.KEY_F9 in capabilities[evdev.ecodes.EV_KEY]:
                        keyboards.append(dev)
            except Exception:
                pass
                
        if not keyboards:
            print("No F9 compatible keyboards found.")
            return
            
        while not self.isInterruptionRequested():
            for k in keyboards:
                try:
                    event = k.read_one()
                    while event:
                        if event.type == evdev.ecodes.EV_KEY:
                            key_event = evdev.categorize(event)
                            keycodes = key_event.keycode
                            if not isinstance(keycodes, list):
                                keycodes = [keycodes]
                            if 'KEY_F9' in keycodes and key_event.keystate == evdev.KeyEvent.key_down:
                                self.f9_pressed.emit()
                        event = k.read_one()
                except Exception:
                    pass
            self.msleep(50)

# Model Downloader Thread
class ModelDownloader(QThread):
    progress = Signal(int, int) # downloaded, total
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, model_name, dest_dir):
        super().__init__()
        self.model_name = model_name
        self.dest_dir = dest_dir

    def run(self):
        url = f"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{self.model_name}.bin"
        dest_path = os.path.join(self.dest_dir, f"ggml-{self.model_name}.bin")
        
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                total_size = int(response.info().get('Content-Length', 0))
                downloaded = 0
                block_size = 1024 * 64
                
                with open(dest_path, 'wb') as f:
                    while not self.isInterruptionRequested():
                        buffer = response.read(block_size)
                        if not buffer:
                            break
                        f.write(buffer)
                        downloaded += len(buffer)
                        self.progress.emit(downloaded, total_size)
            if not self.isInterruptionRequested():
                self.finished.emit(dest_path)
        except Exception as e:
            self.error.emit(str(e))

class WhisperDictationApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.scratch_dir = "/home/apobenol/.gemini/antigravity/scratch"
        self.wav_path = "/tmp/whisper_app_record.wav"
        self.history_file = os.path.join(os.path.expanduser("~"), ".local", "share", "whisper-dictation", "history.json")
        self.history_entries = []
        
        self.ensure_ydotoold()
        self.load_history()
        self.recorder = AudioRecorder(self.wav_path)
        self.transcriber_thread = None
        self.downloader_thread = None
        self.listener_thread = None
        self.recording_vol = 0.0
        
        self.init_ui()
        self.start_listener()
        self.check_models()

    def ensure_ydotoold(self):
        try:
            pgrep = subprocess.run(['pgrep', '-x', 'ydotoold'], stdout=subprocess.PIPE)
            if pgrep.returncode != 0:
                print("ydotoold is not running. Starting it...")
                subprocess.Popen(['ydotoold'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            print(f"Error starting ydotoold: {e}")

    def init_ui(self):
        self.setWindowTitle("Whisper Sesli Dikte")
        self.resize(540, 620)
        self.setMinimumSize(420, 500)
        
        # Dark modern premium theme stylesheet (QSS)
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #16171d, stop:1 #0c0d10);
            }
            QWidget {
                color: #e1e1e6;
                font-family: 'Inter', 'Segoe UI', 'Roboto', sans-serif;
            }
            QLabel {
                font-size: 13px;
                color: #a8a8b3;
                font-weight: 500;
            }
            #navContainer {
                background-color: #1a1b22;
                border: 1px solid #2d303f;
                border-radius: 12px;
            }
            QPushButton.navButton {
                background-color: transparent;
                border: none;
                border-radius: 8px;
                color: #a8a8b3;
                font-weight: bold;
                padding: 6px 12px;
                font-size: 11px;
                min-height: 28px;
            }
            QPushButton.navButton:checked {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00adb5, stop:1 #00f5ff);
                color: #121214;
            }
            QPushButton.navButton:hover:!checked {
                background-color: #252838;
                color: #e1e1e6;
            }
            QComboBox {
                background-color: #1e2029;
                border: 1px solid #2d303f;
                border-radius: 8px;
                padding: 8px 16px;
                color: #e1e1e6;
                font-weight: 500;
            }
            QComboBox:hover {
                border-color: #00adb5;
                background-color: #232635;
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            QComboBox QAbstractItemView {
                background-color: #1e2029;
                border: 1px solid #2d303f;
                selection-background-color: #00adb5;
                selection-color: #121214;
                color: #e1e1e6;
            }
            QTextEdit {
                background-color: #121318;
                border: 1px solid #232635;
                border-radius: 12px;
                padding: 16px;
                color: #e8e8ef;
                font-size: 14px;
                line-height: 150%;
            }
            QTextEdit:focus {
                border-color: #00adb5;
            }
            QCheckBox {
                spacing: 8px;
                font-weight: 500;
                color: #a8a8b3;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 5px;
                border: 2px solid #2d303f;
                background-color: #1e2029;
            }
            QCheckBox::indicator:hover {
                border-color: #00adb5;
            }
            QCheckBox::indicator:checked {
                background-color: #00adb5;
                border-color: #00adb5;
            }
            QProgressBar {
                border: none;
                border-radius: 6px;
                text-align: center;
                background-color: #1e2029;
                height: 10px;
                color: transparent;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00adb5, stop:1 #00f5ff);
                border-radius: 6px;
            }
            QPushButton {
                background-color: #1e2029;
                border: 1px solid #2d303f;
                border-radius: 8px;
                padding: 10px 20px;
                font-weight: bold;
                color: #e1e1e6;
            }
            QPushButton:hover {
                background-color: #252838;
                border-color: #383d54;
            }
            QPushButton:pressed {
                background-color: #121318;
            }
            #recordButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #00adb5, stop:1 #00878d);
                color: #ffffff;
                border: none;
                border-radius: 40px;
                min-width: 80px;
                min-height: 80px;
                max-width: 80px;
                max-height: 80px;
                font-size: 15px;
                font-weight: bold;
                letter-spacing: 1px;
            }
            #recordButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #00c2cb, stop:1 #00adb5);
            }
            #recordButton:checked {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ff4b5c, stop:1 #dc2f43);
            }
            #copyButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00adb5, stop:1 #00f5ff);
                color: #121214;
                border: none;
                border-radius: 8px;
                font-weight: bold;
                padding: 11px;
            }
            #copyButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00c2cb, stop:1 #33f8ff);
            }
            #clearButton {
                background-color: #1e2029;
                border: 1px solid #2d303f;
                border-radius: 8px;
                font-weight: bold;
                padding: 11px;
                color: #a8a8b3;
            }
            #clearButton:hover {
                color: #ff4b5c;
                border-color: #ff4b5c;
                background-color: #231f24;
            }
        """)
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Root horizontal layout: main panel + history drawer
        root_layout = QHBoxLayout(central_widget)
        root_layout.setSpacing(0)
        root_layout.setContentsMargins(0, 0, 0, 0)
        
        main_panel = QWidget()
        main_layout = QVBoxLayout(main_panel)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.addWidget(main_panel, 1)
        
        # History Drawer (hidden by default)
        from PySide6.QtWidgets import QListWidget, QListWidgetItem, QScrollArea
        self.history_drawer = QWidget()
        self.history_drawer.setVisible(False)
        self.history_drawer.setMinimumWidth(200)
        self.history_drawer.setMaximumWidth(220)
        self.history_drawer.setStyleSheet("""
            background-color: #12131a;
            border-left: 1px solid #2d303f;
        """)
        drawer_layout = QVBoxLayout(self.history_drawer)
        drawer_layout.setContentsMargins(8, 12, 8, 12)
        drawer_layout.setSpacing(6)
        
        drawer_title_row = QHBoxLayout()
        drawer_title = QLabel("📋 Geçmiş")
        drawer_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #00adb5;")
        drawer_title_row.addWidget(drawer_title)
        
        clear_hist_btn = QPushButton("🗑")
        clear_hist_btn.setStyleSheet("""
            QPushButton { border:none; background:transparent; font-size:14px; color:#ff4b5c; padding:0 4px; }
            QPushButton:hover { color:#ff1a2e; }
        """)
        clear_hist_btn.setToolTip("Geçmişi Temizle")
        clear_hist_btn.clicked.connect(self.clear_history)
        drawer_title_row.addWidget(clear_hist_btn, 0, Qt.AlignRight)
        drawer_layout.addLayout(drawer_title_row)
        
        self.history_list = QListWidget()
        self.history_list.setStyleSheet("""
            QListWidget {
                background-color: #12131a;
                border: none;
                color: #c8c8d2;
                font-size: 11px;
            }
            QListWidget::item {
                border-bottom: 1px solid #1e2029;
                padding: 6px 4px;
                border-radius: 4px;
            }
            QListWidget::item:selected {
                background-color: #1e2029;
                color: #ffffff;
            }
            QListWidget::item:hover {
                background-color: #1a1b22;
            }
        """)
        self.history_list.itemDoubleClicked.connect(self.copy_history_item)
        drawer_layout.addWidget(self.history_list)
        
        hist_copy_btn = QPushButton("Seçiliyi Kopyala")
        hist_copy_btn.setObjectName("copyButton")
        hist_copy_btn.clicked.connect(lambda: self.copy_history_item(self.history_list.currentItem()))
        drawer_layout.addWidget(hist_copy_btn)
        
        root_layout.addWidget(self.history_drawer)

        # Tabbed interface for modes & languages (At the very top, Chrome-like with add/close support)
        from PySide6.QtWidgets import QTabWidget
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        
        # Add tab button (+)
        self.add_tab_btn = QPushButton("+")
        self.add_tab_btn.setStyleSheet("""
            QPushButton {
                font-weight: bold;
                font-size: 16px;
                color: #00adb5;
                border: none;
                background-color: transparent;
                padding: 2px 10px;
            }
            QPushButton:hover {
                background-color: #252838;
                border-radius: 4px;
            }
        """)
        self.add_tab_btn.clicked.connect(self.add_new_tab)
        self.tabs.setCornerWidget(self.add_tab_btn, Qt.TopRightCorner)
        
        main_layout.addWidget(self.tabs)
        self.tabs.currentChanged.connect(self.check_models)



        # Header / Status
        self.status_label = QLabel("Başlatılmaya hazır")
        self.status_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #e1e1e6;")
        self.status_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.status_label)

        # Recording Section
        rec_layout = QHBoxLayout()
        rec_layout.setAlignment(Qt.AlignCenter)
        self.record_button = QPushButton("Dikte")
        self.record_button.setObjectName("recordButton")
        self.record_button.setCheckable(True)
        self.record_button.clicked.connect(self.toggle_recording)
        
        # Shadow effect
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 173, 181, 100))
        shadow.setOffset(0, 4)
        self.record_button.setGraphicsEffect(shadow)
        
        rec_layout.addWidget(self.record_button)
        main_layout.addLayout(rec_layout)

        # Level bar
        self.level_bar = QProgressBar()
        self.level_bar.setRange(0, 100)
        self.level_bar.setValue(0)
        self.level_bar.setFormat("Mikrofon Düzeyi")
        main_layout.addWidget(self.level_bar)

        # Model Selection (simple HBox)
        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("Whisper Modeli:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(["tiny", "tiny.en", "base", "base.en", "small", "small.en", "medium", "medium.en", "large-v3"])
        self.model_combo.setCurrentText("large-v3")
        self.model_combo.currentTextChanged.connect(self.check_models)
        model_layout.addWidget(self.model_combo)
        main_layout.addLayout(model_layout)

        # Downloader Progress Bar
        self.download_bar = QProgressBar()
        self.download_bar.setVisible(False)
        main_layout.addWidget(self.download_bar)
        
        self.download_button = QPushButton("Seçili Modeli İndir")
        self.download_button.clicked.connect(self.download_model)
        self.download_button.setVisible(False)
        main_layout.addWidget(self.download_button)

        # Options
        options_layout = QHBoxLayout()
        self.autotype_cb = QCheckBox("Metni İmlece Yapıştır (Auto-Type)")
        self.autotype_cb.setChecked(True)
        self.notify_cb = QCheckBox("Ekran Bildirimleri (Notification)")
        self.notify_cb.setChecked(True)
        options_layout.addWidget(self.autotype_cb)
        options_layout.addWidget(self.notify_cb)
        main_layout.addLayout(options_layout)

        # Text Output
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("Konuşulan metin burada görünecektir...")
        main_layout.addWidget(self.text_edit)

        # Bottom Buttons
        button_layout = QHBoxLayout()
        self.copy_button = QPushButton("Metni Kopyala")
        self.copy_button.setObjectName("copyButton")
        self.copy_button.clicked.connect(self.copy_text)
        self.clear_button = QPushButton("Temizle")
        self.clear_button.setObjectName("clearButton")
        self.clear_button.clicked.connect(self.text_edit.clear)
        
        self.history_toggle_btn = QPushButton("📋 Geçmiş")
        self.history_toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e2029;
                border: 1px solid #2d303f;
                border-radius: 8px;
                padding: 10px 14px;
                font-weight: bold;
                color: #a8a8b3;
            }
            QPushButton:hover {
                border-color: #00adb5;
                color: #00adb5;
            }
            QPushButton:checked {
                background-color: #0f2a2c;
                border-color: #00adb5;
                color: #00adb5;
            }
        """)
        self.history_toggle_btn.setCheckable(True)
        self.history_toggle_btn.toggled.connect(self.toggle_history_drawer)
        
        button_layout.addWidget(self.copy_button)
        button_layout.addWidget(self.clear_button)
        button_layout.addWidget(self.history_toggle_btn)
        main_layout.addLayout(button_layout)

        # Create default tabs (moved to end to prevent initialization errors)
        self.create_tab("Türkçe Dikte", "tr", False)
        self.create_tab("İngilizce Dikte", "en", False)
        self.create_tab("Çeviri", "tr", False)

        # System Tray
        self.setup_tray()

    def setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        # Fallback to system mic icon or default icon
        self.tray_icon.setIcon(QIcon.fromTheme("audio-input-microphone", QIcon()))
        
        tray_menu = QMenu()
        show_action = tray_menu.addAction("Göster")
        show_action.triggered.connect(self.showNormal)
        exit_action = tray_menu.addAction("Çıkış")
        exit_action.triggered.connect(QApplication.instance().quit)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_activated)
        self.tray_icon.show()

    def tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.showNormal()
                self.activateWindow()

    def closeEvent(self, event):
        # Pencere kapatıldığında çıkmak yerine sistem tepsisine gizle
        self.hide()
        event.ignore()
        self.send_notification("Arka Planda Çalışıyor", "F9 tuşu ile istediğiniz zaman dikte başlatabilirsiniz.")

    def start_listener(self):
        self.listener_thread = GlobalF9Listener()
        self.listener_thread.f9_pressed.connect(self.f9_triggered)
        self.listener_thread.start()

    @Slot()
    def f9_triggered(self):
        if self.record_button.isEnabled():
            self.record_button.click()
        else:
            self.send_notification("Model Eksik", "Seçili model yüklü değil. Lütfen önce indirin veya hazır bir model seçin.")

    def get_active_model(self):
        return self.model_combo.currentText()

    def create_tab(self, name, lang="tr", translate=False):
        from PySide6.QtWidgets import QLineEdit, QGridLayout
        tab_widget = QWidget()
        tab_layout = QGridLayout(tab_widget)
        tab_layout.setContentsMargins(10, 8, 10, 8)
        tab_layout.setSpacing(8)
        
        # Row 0 Left: Name Edit
        name_edit = QLineEdit(name)
        name_edit.setMaxLength(15)
        name_edit.setPlaceholderText("Sekme Adı")
        name_edit.setStyleSheet("background-color: #121318; border: 1px solid #2d303f; border-radius: 6px; padding: 4px 8px; font-weight: bold; color: #e1e1e6;")
        name_edit.setMinimumWidth(110)
        tab_layout.addWidget(name_edit, 0, 0)
        
        # Row 0 Right: Source Lang
        lang_widget = QWidget()
        lang_layout = QHBoxLayout(lang_widget)
        lang_layout.setContentsMargins(0, 0, 0, 0)
        lang_layout.setSpacing(6)
        
        lang_label = QLabel("Dil:")
        lang_layout.addWidget(lang_label)
        
        lang_combo = QComboBox()
        lang_combo.addItem("Türkçe", "tr")
        lang_combo.addItem("İngilizce", "en")
        lang_combo.addItem("Almanca", "de")
        lang_combo.addItem("Fransızca", "fr")
        lang_combo.addItem("İspanyolca", "es")
        lang_combo.setCurrentIndex(lang_combo.findData(lang))
        lang_combo.currentIndexChanged.connect(self.check_models)
        lang_layout.addWidget(lang_combo)
        
        tab_layout.addWidget(lang_widget, 0, 1)
        
        # Row 1 Left: Translate Checkbox
        trans_cb = QCheckBox("Çevir")
        trans_cb.setChecked(translate)
        tab_layout.addWidget(trans_cb, 1, 0)
        
        # Row 1 Right: Target Lang
        target_widget = QWidget()
        target_layout = QHBoxLayout(target_widget)
        target_layout.setContentsMargins(0, 0, 0, 0)
        target_layout.setSpacing(6)
        
        target_label = QLabel("Hedef:")
        target_layout.addWidget(target_label)
        
        target_combo = QComboBox()
        target_combo.addItem("İngilizce", "en")
        target_combo.addItem("Türkçe", "tr")
        target_combo.addItem("Almanca", "de")
        target_combo.addItem("Fransızca", "fr")
        target_combo.addItem("İspanyolca", "es")
        target_combo.addItem("İtalyanca", "it")
        target_combo.addItem("Rusça", "ru")
        target_combo.addItem("Arapça", "ar")
        target_combo.addItem("Japonca", "ja")
        target_combo.setCurrentIndex(0) # Default to English
        target_layout.addWidget(target_combo)
        
        tab_layout.addWidget(target_widget, 1, 1)
        
        # Set initial visibility based on translate flag
        target_label.setVisible(translate)
        target_combo.setVisible(translate)
        
        # Connect toggles to hide/show target widgets dynamically
        trans_cb.toggled.connect(target_label.setVisible)
        trans_cb.toggled.connect(target_combo.setVisible)
        
        # Store refs
        tab_widget.lang_combo = lang_combo
        tab_widget.trans_cb = trans_cb
        tab_widget.target_combo = target_combo
        tab_widget.name_edit = name_edit
        
        # Add to tabs
        idx = self.tabs.addTab(tab_widget, name)
        
        # Signal connection to update title dynamically
        name_edit.textChanged.connect(lambda text, w=tab_widget: self.update_tab_title(w, text))
        
        self.tabs.setCurrentIndex(idx)
        self.check_models()

    def update_tab_title(self, widget, text):
        idx = self.tabs.indexOf(widget)
        if idx != -1:
            self.tabs.setTabText(idx, text if text.strip() else "Dikte")

    def close_tab(self, index):
        if self.tabs.count() > 1:
            self.tabs.removeTab(index)
            self.check_models()

    def add_new_tab(self):
        self.create_tab(f"Dikte {self.tabs.count() + 1}")


    def check_models(self):
        model_name = self.get_active_model()
        model_path = os.path.join(self.scratch_dir, f"ggml-{model_name}.bin")
        if os.path.exists(model_path):
            self.status_label.setText(f"Model Hazır: {model_name}")
            self.download_button.setVisible(False)
            self.record_button.setEnabled(True)
        else:
            self.status_label.setText(f"Model Eksik: {model_name}")
            self.download_button.setText(f"{model_name} Modelini İndir")
            self.download_button.setVisible(True)
            self.record_button.setEnabled(False)

    def download_model(self):
        model_name = self.get_active_model()
        self.download_bar.setVisible(True)
        self.download_button.setEnabled(False)
        self.status_label.setText("Model indiriliyor...")
        
        self.downloader_thread = ModelDownloader(model_name, self.scratch_dir)
        self.downloader_thread.progress.connect(self.update_download_progress)
        self.downloader_thread.finished.connect(self.download_finished)
        self.downloader_thread.error.connect(self.download_error)
        self.downloader_thread.start()

    def update_download_progress(self, downloaded, total):
        if total > 0:
            val = int((downloaded / total) * 100)
            self.download_bar.setValue(val)

    def download_finished(self, path):
        self.download_bar.setVisible(False)
        self.download_button.setEnabled(True)
        self.check_models()
        self.send_notification("İndirme Tamamlandı", f"Model başarıyla kuruldu.")

    def download_error(self, err):
        self.download_bar.setVisible(False)
        self.download_button.setEnabled(True)
        self.status_label.setText(f"Hata: {err}")
        self.send_notification("Hata", f"Model indirilemedi: {err}")

    def update_volume(self, vol):
        # Update progress bar smoothly in main thread
        self.level_bar.setValue(int(vol * 100))

    def toggle_recording(self):
        if self.record_button.isChecked():
            # Start Recording
            self.record_button.setText("Dur")
            self.record_button.setStyleSheet("background-color: #e23e57; color: white;")
            self.status_label.setText("Ses Kaydediliyor...")
            self.send_notification("Dikte Başladı", "Konuşun... (Bitirmek için F9 veya Dur butonuna basın)")
            self.recorder.start(volume_callback=self.update_volume)
        else:
            # Stop Recording
            self.record_button.setText("Dikte")
            self.record_button.setStyleSheet("")
            self.recorder.stop()
            self.level_bar.setValue(0)
            self.status_label.setText("Metin oluşturuluyor...")
            self.send_notification("Kayıt Durduruldu", "Ses çözümleniyor...")
            
            # Start Transcription
            model_name = self.get_active_model()
            model_path = os.path.join(self.scratch_dir, f"ggml-{model_name}.bin")
            
            # Determine lang and translate dynamically from the active tab widget
            active_tab = self.tabs.currentWidget()
            if active_tab:
                lang = active_tab.lang_combo.currentData()
                translate = active_tab.trans_cb.isChecked()
                target_lang = active_tab.target_combo.currentData()
            else:
                lang = "tr"
                translate = False
                target_lang = "en"
                
            self.transcriber_thread = TranscriberThread(model_path, self.wav_path, lang, translate, target_lang)
            self.transcriber_thread.finished.connect(self.transcription_finished)
            self.transcriber_thread.error.connect(self.transcription_error)
            self.transcriber_thread.start()

    def transcription_finished(self, text):
        self.status_label.setText("Hazır")
        if text:
            self.text_edit.append(text)
            self.add_to_history(text)
            if self.autotype_cb.isChecked():
                self.paste_text_via_uinput(text)
            else:
                self.send_notification("Deşifre Tamamlandı", text)
        else:
            self.send_notification("Whisper", "Konuşma algılanamadı.")

    def load_history(self):
        try:
            os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    import json
                    self.history_entries = json.load(f)
        except Exception:
            self.history_entries = []

    def save_history(self):
        try:
            import json
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history_entries[-200:], f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def add_to_history(self, text):
        from datetime import datetime
        from PySide6.QtWidgets import QListWidgetItem
        timestamp = datetime.now().strftime("%d.%m %H:%M")
        entry = {"text": text, "time": timestamp}
        self.history_entries.append(entry)
        self.save_history()
        
        # Add to list widget at the top
        display = f"[{timestamp}]\n{text[:80]}{'...' if len(text) > 80 else ''}"
        item = QListWidgetItem(display)
        item.setData(0x0100, text)  # Store full text in UserRole
        self.history_list.insertItem(0, item)

    def refresh_history_list(self):
        from PySide6.QtWidgets import QListWidgetItem
        self.history_list.clear()
        for entry in reversed(self.history_entries[-200:]):
            display = f"[{entry['time']}]\n{entry['text'][:80]}{'...' if len(entry['text']) > 80 else ''}"
            item = QListWidgetItem(display)
            item.setData(0x0100, entry['text'])
            self.history_list.addItem(item)

    def toggle_history_drawer(self, checked):
        self.history_drawer.setVisible(checked)
        if checked:
            self.refresh_history_list()
            self.resize(self.width() + 210, self.height())
        else:
            self.resize(self.width() - 210, self.height())

    def copy_history_item(self, item):
        if item is None:
            return
        full_text = item.data(0x0100)
        if full_text:
            clipboard = QApplication.clipboard()
            clipboard.setText(full_text)
            self.send_notification("Kopyalandı", "Geçmiş öğesi panoya kopyalandı.")

    def clear_history(self):
        self.history_entries = []
        self.history_list.clear()
        self.save_history()

    def transcription_error(self, err):
        self.status_label.setText("Hata oluştu")
        self.send_notification("Transkripsiyon Hatası", err)

    def paste_text_via_uinput(self, text):
        try:
            # Pano yedeği al
            old_clip = subprocess.check_output(['wl-paste', '-n'], stderr=subprocess.DEVNULL).decode('utf-8', errors='ignore')
        except Exception:
            old_clip = ""

        try:
            # Metni panoya kopyala
            p = subprocess.Popen(['wl-copy'], stdin=subprocess.PIPE)
            p.communicate(input=text.encode('utf-8'))
            
            # Ctrl+V yapıştır
            subprocess.run(['ydotool', 'key', '29:1', '47:1', '47:0', '29:0'])
            
            # Panoyu eski haline getir
            def restore():
                p_res = subprocess.Popen(['wl-copy'], stdin=subprocess.PIPE)
                p_res.communicate(input=old_clip.encode('utf-8'))
            
            QTimer.singleShot(500, restore)
        except Exception as e:
            print(f"Pasting failed: {e}")

    def copy_text(self):
        text = self.text_edit.toPlainText()
        if text:
            try:
                p = subprocess.Popen(['wl-copy'], stdin=subprocess.PIPE)
                p.communicate(input=text.encode('utf-8'))
                self.status_label.setText("Panoya kopyalandı!")
                QTimer.singleShot(2000, lambda: self.status_label.setText("Hazır"))
            except Exception as e:
                print(f"Copy failed: {e}")

    def send_notification(self, title, msg):
        if self.notify_cb.isChecked():
            subprocess.run(['notify-send', '-t', '1500', title, msg])

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # Modern Dark Theme Palette setup
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(18, 18, 20))
    palette.setColor(QPalette.WindowText, QColor(225, 225, 230))
    palette.setColor(QPalette.Base, QColor(32, 32, 36))
    palette.setColor(QPalette.AlternateBase, QColor(18, 18, 20))
    palette.setColor(QPalette.ToolTipBase, QColor(18, 18, 20))
    palette.setColor(QPalette.ToolTipText, QColor(225, 225, 230))
    palette.setColor(QPalette.Text, QColor(225, 225, 230))
    palette.setColor(QPalette.Button, QColor(32, 32, 36))
    palette.setColor(QPalette.ButtonText, QColor(225, 225, 230))
    palette.setColor(QPalette.BrightText, QColor(255, 255, 255))
    palette.setColor(QPalette.Highlight, QColor(0, 173, 181))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)
    
    window = WhisperDictationApp()
    window.show()
    sys.exit(app.exec())

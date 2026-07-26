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
        
        self.ensure_ydotoold()
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
        self.resize(450, 600)
        self.setMinimumSize(400, 500)
        
        # Dark modern theme palette
        self.setStyleSheet("""
            QMainWindow {
                background-color: #121214;
            }
            QWidget {
                color: #e1e1e6;
                font-family: 'Segoe UI', 'Roboto', sans-serif;
            }
            QLabel {
                font-size: 13px;
                color: #a8a8b3;
            }
            QComboBox {
                background-color: #202024;
                border: 1px solid #323238;
                border-radius: 6px;
                padding: 6px 12px;
                color: #e1e1e6;
            }
            QComboBox::drop-down {
                border: none;
            }
            QTextEdit {
                background-color: #202024;
                border: 1px solid #323238;
                border-radius: 8px;
                padding: 10px;
                color: #e1e1e6;
                font-size: 14px;
            }
            QCheckBox {
                spacing: 8px;
            }
            QProgressBar {
                border: 1px solid #323238;
                border-radius: 4px;
                text-align: center;
                background-color: #202024;
                height: 12px;
            }
            QProgressBar::chunk {
                background-color: #00adb5;
                border-radius: 3px;
            }
            QPushButton {
                background-color: #202024;
                border: 1px solid #323238;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                color: #e1e1e6;
            }
            QPushButton:hover {
                background-color: #29292e;
            }
            QPushButton:pressed {
                background-color: #121214;
            }
            #recordButton {
                background-color: #00adb5;
                color: #ffffff;
                border: none;
                border-radius: 40px;
                min-width: 80px;
                min-height: 80px;
                max-width: 80px;
                max-height: 80px;
                font-size: 16px;
            }
            #recordButton:hover {
                background-color: #00c2cb;
            }
            #recordButton:checked {
                background-color: #e23e57;
            }
        """)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(16)
        main_layout.setContentsMargins(20, 20, 20, 20)

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

        # Config Panel
        config_layout = QHBoxLayout()
        
        # Model selector
        model_vbox = QVBoxLayout()
        model_vbox.addWidget(QLabel("Whisper Modeli:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(["tiny", "base", "small", "medium", "large-v3"])
        self.model_combo.setCurrentText("large-v3")
        self.model_combo.currentTextChanged.connect(self.check_models)
        model_vbox.addWidget(self.model_combo)
        config_layout.addLayout(model_vbox)

        # Language selector
        lang_vbox = QVBoxLayout()
        lang_vbox.addWidget(QLabel("Dikte Dili:"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("Türkçe", "tr")
        self.lang_combo.addItem("İngilizce", "en")
        self.lang_combo.addItem("Otomatik Algıla", "auto")
        lang_vbox.addWidget(self.lang_combo)
        config_layout.addLayout(lang_vbox)

        main_layout.addLayout(config_layout)

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
        self.advanced_cb = QCheckBox("Gelişmiş Ayarlar")
        self.advanced_cb.setChecked(False)
        self.advanced_cb.toggled.connect(self.toggle_advanced)
        options_layout.addWidget(self.autotype_cb)
        options_layout.addWidget(self.notify_cb)
        options_layout.addWidget(self.advanced_cb)
        main_layout.addLayout(options_layout)

        # Advanced Settings Widget
        self.advanced_widget = QWidget()
        self.advanced_widget.setVisible(False)
        self.advanced_widget.setStyleSheet("background-color: #1a1a1e; border-radius: 6px; border: 1px solid #2d2d31;")
        adv_layout = QVBoxLayout(self.advanced_widget)
        adv_layout.setContentsMargins(12, 12, 12, 12)
        
        adv_title = QLabel("Gelişmiş Çeviri & İngilizce Modelleri")
        adv_title.setStyleSheet("font-weight: bold; color: #00adb5; border: none;")
        adv_layout.addWidget(adv_title)
        
        trans_layout = QHBoxLayout()
        self.translate_cb = QCheckBox("İngilizceye Çevir (-tr)")
        self.translate_cb.setChecked(False)
        trans_layout.addWidget(self.translate_cb)
        
        self.use_en_model_cb = QCheckBox("İngilizce Odaklı Model (.en)")
        self.use_en_model_cb.setChecked(False)
        self.use_en_model_cb.toggled.connect(self.toggle_en_model_cb)
        trans_layout.addWidget(self.use_en_model_cb)
        adv_layout.addLayout(trans_layout)
        
        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("İngilizce Modeli:"))
        self.en_model_combo = QComboBox()
        self.en_model_combo.addItems(["tiny.en", "base.en", "small.en", "medium.en"])
        self.en_model_combo.setCurrentText("small.en")
        self.en_model_combo.setEnabled(False)
        self.en_model_combo.currentTextChanged.connect(self.check_models)
        model_layout.addWidget(self.en_model_combo)
        adv_layout.addLayout(model_layout)
        
        main_layout.addWidget(self.advanced_widget)

        # Text Output
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("Konuşulan metin burada görünecektir...")
        main_layout.addWidget(self.text_edit)

        # Bottom Buttons
        button_layout = QHBoxLayout()
        self.copy_button = QPushButton("Metni Kopyala")
        self.copy_button.clicked.connect(self.copy_text)
        self.clear_button = QPushButton("Temizle")
        self.clear_button.clicked.connect(self.text_edit.clear)
        button_layout.addWidget(self.copy_button)
        button_layout.addWidget(self.clear_button)
        main_layout.addLayout(button_layout)

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
        if self.advanced_cb.isChecked() and self.use_en_model_cb.isChecked():
            return self.en_model_combo.currentText()
        return self.model_combo.currentText()

    def toggle_advanced(self, checked):
        self.advanced_widget.setVisible(checked)
        self.check_models()

    def toggle_en_model_cb(self, checked):
        self.en_model_combo.setEnabled(checked)
        self.check_models()

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
            lang = self.lang_combo.currentData()
            
            translate = False
            if self.advanced_cb.isChecked() and self.translate_cb.isChecked():
                translate = True
                
            self.transcriber_thread = TranscriberThread(model_path, self.wav_path, lang, translate)
            self.transcriber_thread.finished.connect(self.transcription_finished)
            self.transcriber_thread.error.connect(self.transcription_error)
            self.transcriber_thread.start()

    def transcription_finished(self, text):
        self.status_label.setText("Hazır")
        if text:
            self.text_edit.append(text)
            if self.autotype_cb.isChecked():
                self.paste_text_via_uinput(text)
            else:
                self.send_notification("Deşifre Tamamlandı", text)
        else:
            self.send_notification("Whisper", "Konuşma algılanamadı.")

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

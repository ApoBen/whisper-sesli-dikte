import subprocess
import os
from PySide6.QtCore import QThread, Signal

class TranscriberThread(QThread):
    started = Signal()
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, model_path, wav_path, language="tr", translate=False):
        super().__init__()
        self.model_path = model_path
        self.wav_path = wav_path
        self.language = language
        self.translate = translate
        self.output_base = "/tmp/whisper_transcription"
        self.output_txt = f"{self.output_base}.txt"

    def run(self):
        self.started.emit()
        
        if os.path.exists(self.output_txt):
            try:
                os.remove(self.output_txt)
            except Exception:
                pass
            
        cmd = [
            'whisper-cli',
            '-m', self.model_path,
            '-l', self.language,
            '-f', self.wav_path,
            '-otxt',
            '-of', self.output_base,
            '-np'
        ]
        if self.translate:
            cmd.append('-tr')
        
        try:
            process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # Vulkan çıkış hatasını (cleanup crash) bypass etmek için önce çıktı dosyasını kontrol et
            if os.path.exists(self.output_txt):
                with open(self.output_txt, 'r', encoding='utf-8') as f:
                    text = f.read().strip()
                
                # Single line cleaning
                text = text.replace('\n', ' ').strip()
                self.finished.emit(text)
                try:
                    os.remove(self.output_txt)
                except Exception:
                    pass
            elif process.returncode != 0:
                err_msg = process.stderr.decode('utf-8', errors='ignore')
                self.error.emit(f"whisper-cli error: {err_msg}")
            else:
                self.error.emit("Transcription completed but output file not found.")
        except Exception as e:
            self.error.emit(str(e))

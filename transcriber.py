import subprocess
import os
from PySide6.QtCore import QThread, Signal

class TranscriberThread(QThread):
    started = Signal()
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, model_path, wav_path, language="tr", translate=False, target_language="en"):
        super().__init__()
        self.model_path = model_path
        self.wav_path = wav_path
        self.language = language
        self.translate = translate
        self.target_language = target_language
        self.output_base = "/tmp/whisper_transcription"
        self.output_txt = f"{self.output_base}.txt"

    def google_translate(self, text, source_lang='auto', target_lang='en'):
        import urllib.request
        import urllib.parse
        import json
        try:
            sl = source_lang
            if sl == 'auto':
                sl = 'auto'
            url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=" + sl + "&tl=" + target_lang + "&dt=t&q=" + urllib.parse.quote(text)
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))
                result = "".join([sentence[0] for sentence in data[0] if sentence[0]])
                return result
        except Exception as e:
            return f"(Çeviri Hatası: {e}) {text}"

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
        
        try:
            print(f"Executing: {' '.join(cmd)}")
            process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # Vulkan çıkış hatasını (cleanup crash) bypass etmek için önce çıktı dosyasını kontrol et
            if os.path.exists(self.output_txt):
                with open(self.output_txt, 'r', encoding='utf-8') as f:
                    text = f.read().strip()
                
                # Single line cleaning
                text = text.replace('\n', ' ').strip()
                
                if self.translate and text:
                    text = self.google_translate(text, self.language, self.target_language)
                    
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

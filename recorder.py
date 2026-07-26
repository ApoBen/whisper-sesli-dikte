import wave
import subprocess
import struct
import math
import threading

class AudioRecorder:
    def __init__(self, filename, sample_rate=16000):
        self.filename = filename
        self.sample_rate = sample_rate
        self.process = None
        self.recording = False
        self.volume_callback = None
        self.thread = None

    def start(self, volume_callback=None):
        self.recording = True
        self.volume_callback = volume_callback
        self.thread = threading.Thread(target=self._record_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.recording = False
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                self.process.kill()
        if self.thread:
            self.thread.join(timeout=1.0)

    def _record_loop(self):
        cmd = ['arecord', '-q', '-r', str(self.sample_rate), '-f', 'S16_LE', '-c', '1', '-t', 'raw']
        try:
            self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except Exception as e:
            print(f"Failed to start arecord: {e}")
            return
        
        try:
            wf = wave.open(self.filename, 'wb')
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
        except Exception as e:
            print(f"Failed to open wav file for writing: {e}")
            if self.process:
                self.process.kill()
            return
        
        chunk_size = 1024
        bytes_to_read = chunk_size * 2
        
        while self.recording:
            try:
                data = self.process.stdout.read(bytes_to_read)
                if not data:
                    break
                    
                wf.writeframes(data)
                
                if self.volume_callback and len(data) > 0:
                    count = len(data) // 2
                    shorts = struct.unpack(f"{count}h", data)
                    
                    sum_squares = sum(s * s for s in shorts)
                    rms = math.sqrt(sum_squares / count) if count > 0 else 0
                    
                    normalized_vol = min(rms / 12000.0, 1.0)
                    self.volume_callback(normalized_vol)
            except Exception as e:
                print(f"Error during recording loop: {e}")
                break
                
        wf.close()

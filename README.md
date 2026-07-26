# Whisper Sesli Dikte (Whisper Dictation App)

Bu uygulama, Linux (özellikle Arch Linux ve KDE Plasma/Wayland) sistemlerinde global bir kısayol (**F9**) aracılığıyla sesinizi kaydedip, yerel olarak çalışan **Whisper (large-v3)** modeli vasıtasıyla deşifre eden ve imlecin bulunduğu yere anında yapıştıran modern bir masaüstü (GUI) uygulamasıdır.

Çözümleme işlemini tamamen bilgisayarınızda yerel (local) olarak ve **Intel Arc (veya diğer Vulkan destekli) GPU**'nuz üzerinden çok hızlı bir şekilde gerçekleştirir.

## Özellikler
- **Vulkan GPU Hızlandırması:** GPU desteği sayesinde sesler saniyeler içinde çözümlenir.
- **Kusursuz Türkçe Karakter Desteği:** Tuş simülasyonu yerine pano (clipboard) kopyala-yapıştır yöntemi kullanıldığından Türkçe karakterler (ş, ç, ğ, ı, ö, ü) eksiksiz yazdırılır.
- **Model Yöneticisi:** Arayüzden `tiny`, `base`, `small`, `medium` ve `large-v3` modellerini seçebilir, eksik olan modelleri tek tıkla arayüzden indirebilirsiniz.
- **Ses Düzeyi Takibi:** Kayıt esnasında ses yüksekliğini gösteren mikrofon düzeyi barı.
- **Sistem Tepsisi (Tray) Modu:** Pencereyi kapattığınızda uygulama sistem tepsisine küçülür ve arka planda çalışmaya devam eder.
- **KDE Otomatik Başlatma:** Sistem başlangıcında arka planda otomatik olarak başlar.

## Gereksinimler
- Python 3
- PySide6
- python-evdev
- wl-clipboard (Wayland için pano kontrolü)
- ydotool (Sanal klavye simülasyonu için)
- whisper-cpp (ggerganov/whisper.cpp portu)
- alsa-utils (Kayıt için `arecord`)

## Kurulum

Uygulamayı ve tüm bağımlılıklarını kurmak için `install.sh` betiğini çalıştırabilirsiniz:

```bash
chmod +x install.sh
./install.sh
```

## Manuel Kurulum

1. **Bağımlılıkları Yükleyin (Arch Linux):**
   ```bash
   sudo pacman -S --needed python-pyside6 python-evdev wl-clipboard ydotool whisper-cpp alsa-utils
   ```

2. **Grup ve Yetki Ayarları:**
   Kısayolların ve sanal klavyenin çalışabilmesi için kullanıcınızın `input` grubuna dahil olması ve udev kurallarının ayarlanması gerekir:
   ```bash
   sudo usermod -aG input $USER
   sudo bash -c 'echo "KERNEL==\"uinput\", SUBSYSTEM==\"misc\", OPTIONS+=\"static_node=uinput\", TAG+=\"uaccess\"" > /etc/udev/rules.d/85-sunshine-input.rules'
   sudo udevadm control --reload-rules && sudo udevadm trigger
   sudo modprobe uinput
   ```

3. **Ydotool ve Kısayol Dinleyici Servislerini Etkinleştirin:**
   ```bash
   systemctl --user enable --now ydotool.service
   ```

4. **Uygulamayı Çalıştırın:**
   ```bash
   python dictation_app.py
   ```

## Lisans
MIT

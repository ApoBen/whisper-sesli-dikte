#!/bin/bash

# Renk tanımları
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}[*] Whisper Sesli Dikte Kurulumu Başlatılıyor...${NC}"

# Arch Linux kontrolü
if [ -f /etc/arch-release ]; then
    echo -e "${GREEN}[*] Bağımlılıklar pacman ile yükleniyor...${NC}"
    sudo pacman -S --needed --noconfirm python-pyside6 python-evdev wl-clipboard ydotool whisper-cpp alsa-utils
else
    echo -e "${RED}[!] Arch Linux tespit edilemedi. Lütfen bağımlılıkları manuel olarak yükleyin:${NC}"
    echo "pyside6, python-evdev, wl-clipboard, ydotool, whisper-cpp, alsa-utils"
fi

# Kullanıcıyı input grubuna ekle
echo -e "${GREEN}[*] Kullanıcı yetkilendirmeleri yapılıyor...${NC}"
sudo usermod -aG input $USER

# uinput udev kurallarını ayarla
sudo bash -c 'echo "KERNEL==\"uinput\", SUBSYSTEM==\"misc\", OPTIONS+=\"static_node=uinput\", TAG+=\"uaccess\"" > /etc/udev/rules.d/85-sunshine-input.rules'
sudo udevadm control --reload-rules && sudo udevadm trigger
sudo modprobe uinput

# ydotool servisini etkinleştir
echo -e "${GREEN}[*] ydotool servisi aktif ediliyor...${NC}"
systemctl --user enable --now ydotool.service

# Otomatik başlatma dosyasını oluştur
echo -e "${GREEN}[*] KDE Otomatik Başlatma kısayolu oluşturuluyor...${NC}"
mkdir -p ~/.config/autostart
APP_DIR=$(pwd)

cat << AUTOSTART > ~/.config/autostart/whisper-dictation.desktop
[Desktop Entry]
Exec=/usr/bin/python ${APP_DIR}/dictation_app.py
Name=Whisper Dictation
Type=Application
X-KDE-Autostart-after=panel
AUTOSTART

echo -e "${GREEN}[✓] Kurulum tamamlandı! Değişikliklerin tam olarak geçerli olması için lütfen bilgisayarınızı yeniden başlatın veya oturumu kapatıp açın.${NC}"
echo -e "${GREEN}[*] Uygulamayı hemen başlatmak için: python dictation_app.py${NC}"

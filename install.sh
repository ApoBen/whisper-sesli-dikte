#!/bin/bash

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}[*] Evrensel Whisper Sesli Dikte Kurulumu Başlatılıyor...${NC}"

# Eğer script doğrudan curl ile uzaktan çalıştırıldıysa, depoyu klonla ve içine gir
if [ ! -f "dictation_app.py" ]; then
    echo -e "${GREEN}[*] Proje dosyaları indirilip kuruluyor...${NC}"
    INSTALL_DIR="$HOME/.local/share/whisper-dictation"
    rm -rf "$INSTALL_DIR"
    git clone https://github.com/ApoBen/whisper-sesli-dikte.git "$INSTALL_DIR"
    cd "$INSTALL_DIR" || exit 1
fi

# 1. Dağıtım tespiti ve Bağımlılıkların Kurulumu
if command -v pacman &> /dev/null; then
    echo -e "${GREEN}[*] Arch Linux tespit edildi. Paketler pacman ile kuruluyor...${NC}"
    sudo pacman -S --needed --noconfirm base-devel git python-pip python-pyside6 python-evdev wl-clipboard ydotool whisper-cpp alsa-utils
elif command -v apt-get &> /dev/null; then
    echo -e "${GREEN}[*] Debian/Ubuntu/Mint tespit edildi. Paketler apt ile kuruluyor...${NC}"
    sudo apt-get update
    sudo apt-get install -y build-essential git python3-pip wl-clipboard ydotool alsa-utils libevdev-dev python3-dev python3-pyside6 || \
    sudo apt-get install -y build-essential git python3-pip wl-clipboard ydotool alsa-utils libevdev-dev python3-dev
    
    # Python paketlerini kur
    pip3 install --upgrade --break-system-packages pyside6 evdev 2>/dev/null || pip3 install --upgrade pyside6 evdev
elif command -v dnf &> /dev/null; then
    echo -e "${GREEN}[*] Fedora tespit edildi. Paketler dnf ile kuruluyor...${NC}"
    sudo dnf groupinstall -y "Development Tools"
    sudo dnf install -y git python3-pip wl-clipboard ydotool alsa-utils libevdev-devel python3-devel python3-pyside6 || \
    sudo dnf install -y git python3-pip wl-clipboard ydotool alsa-utils libevdev-devel python3-devel
    
    pip3 install --upgrade --break-system-packages pyside6 evdev 2>/dev/null || pip3 install --upgrade pyside6 evdev
else
    echo -e "${YELLOW}[!] Desteklenmeyen dağıtım. Lütfen derleme araçlarını, python3-pyside6, python3-evdev, wl-clipboard, ydotool ve alsa-utils paketlerini manuel kurun.${NC}"
fi

# 2. Whisper.cpp Derleme (Eğer sistemde whisper-cli yoksa)
if ! command -v whisper-cli &> /dev/null; then
    echo -e "${YELLOW}[*] Sistemde whisper-cli bulunamadı. Whisper.cpp kaynaktan derleniyor (Vulkan GPU destekli)...${NC}"
    
    BUILD_DIR="/tmp/whisper_cpp_build"
    rm -rf "$BUILD_DIR"
    git clone https://github.com/ggerganov/whisper.cpp.git "$BUILD_DIR"
    
    cd "$BUILD_DIR"
    # Vulkan desteğiyle derle (Intel Arc ve diğer modern GPU'lar için)
    GGML_VULKAN=1 make -j$(nproc)
    
    if [ -f "./build/bin/whisper-cli" ]; then
        sudo cp ./build/bin/whisper-cli /usr/local/bin/whisper-cli
        echo -e "${GREEN}[✓] whisper-cli başarıyla derlendi ve /usr/local/bin/whisper-cli konumuna yüklendi.${NC}"
    elif [ -f "./main" ]; then
        sudo cp ./main /usr/local/bin/whisper-cli
        echo -e "${GREEN}[✓] whisper-cli başarıyla derlendi ve /usr/local/bin/whisper-cli konumuna yüklendi.${NC}"
    else
        echo -e "${RED}[!] Derleme başarısız oldu.${NC}"
        exit 1
    fi
    cd - &>/dev/null
    rm -rf "$BUILD_DIR"
fi

# 3. Kullanıcı Yetkilendirmeleri (evdev ve ydotool için)
echo -e "${GREEN}[*] Kullanıcı yetkilendirmeleri yapılıyor...${NC}"
sudo usermod -aG input $USER

# uinput udev kurallarını ayarla
sudo bash -c 'echo "KERNEL==\"uinput\", SUBSYSTEM==\"misc\", OPTIONS+=\"static_node=uinput\", TAG+=\"uaccess\"" > /etc/udev/rules.d/85-sunshine-input.rules'
sudo udevadm control --reload-rules && sudo udevadm trigger
sudo modprobe uinput

# ydotool servisini etkinleştir (varsa)
if systemctl --user list-unit-files | grep -q ydotool; then
    echo -e "${GREEN}[*] ydotool servisi aktif ediliyor...${NC}"
    systemctl --user enable --now ydotool.service
fi

# 4. Masaüstü Kısayolu ve Otomatik Başlatma
echo -e "${GREEN}[*] Masaüstü uygulama kısayolları oluşturuluyor...${NC}"
APP_DIR=$(pwd)

# Uygulama menüsü kısayolu (Launcher)
mkdir -p ~/.local/share/applications
cat << LAUNCHER > ~/.local/share/applications/whisper-dictation.desktop
[Desktop Entry]
Name=Whisper Sesli Dikte
Comment=Yapay zeka destekli sesli dikte ve çeviri aracı
Exec=/usr/bin/python ${APP_DIR}/dictation_app.py
Icon=audio-input-microphone
Terminal=false
Type=Application
Categories=Utility;AudioVideo;
StartupNotify=true
LAUNCHER

# Otomatik başlatma kısayolu (Autostart)
mkdir -p ~/.config/autostart
cat << AUTOSTART > ~/.config/autostart/whisper-dictation.desktop
[Desktop Entry]
Name=Whisper Sesli Dikte
Exec=/usr/bin/python ${APP_DIR}/dictation_app.py
Type=Application
X-KDE-Autostart-after=panel
AUTOSTART

# Desktop veritabanını güncelle
update-desktop-database ~/.local/share/applications &>/dev/null

echo -e "${GREEN}[✓] Kurulum tamamlandı!${NC}"
echo -e "${YELLOW}[!] Değişikliklerin (grup yetkileri vb.) tam geçerli olması için oturumu kapatıp açmanız veya sistemi yeniden başlatmanız önerilir.${NC}"
echo -e "${GREEN}[*] Çalıştırmak için: python dictation_app.py${NC}"

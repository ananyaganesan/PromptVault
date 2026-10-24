#!/bin/zsh

set -euo pipefail

SCRIPT_DIR="${0:A:h}"
PROJECT_ROOT="${SCRIPT_DIR:h:h}"
SOURCE_APPLESCRIPT="${SCRIPT_DIR}/PromptVault.applescript"
LAUNCHER_SCRIPT="${SCRIPT_DIR}/promptvault-launcher.sh"
ICON_SOURCE="${SCRIPT_DIR}/PromptVaultIcon.svg"
OUTPUT_DIR="${1:-${HOME}/Applications}"
APP_PATH="${OUTPUT_DIR}/PromptVault.app"
TEMP_DIR="$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/promptvault-app.XXXXXX")"

cleanup() {
  /bin/rm -rf "${TEMP_DIR}"
}
trap cleanup EXIT

mkdir -p "${OUTPUT_DIR}"
chmod +x "${LAUNCHER_SCRIPT}"

escaped_launcher="${LAUNCHER_SCRIPT//\/\\}"
escaped_launcher="${escaped_launcher//\//\/}"
/usr/bin/sed "s/__LAUNCHER_PATH__/${escaped_launcher}/g" "${SOURCE_APPLESCRIPT}" > "${TEMP_DIR}/PromptVault.applescript"

/usr/bin/osacompile -o "${TEMP_DIR}/PromptVault.app" "${TEMP_DIR}/PromptVault.applescript"

# `sips` advertises SVG support on recent macOS releases but cannot reliably
# rasterize SVG files. Quick Look renders the source consistently using only
# tools included with macOS.
/usr/bin/qlmanage -t -s 1024 -o "${TEMP_DIR}" "${ICON_SOURCE}" >/dev/null
/bin/mv "${TEMP_DIR}/PromptVaultIcon.svg.png" "${TEMP_DIR}/icon-master.png"
iconset="${TEMP_DIR}/PromptVault.iconset"
mkdir -p "${iconset}"
for spec in "16:icon_16x16.png" "32:icon_16x16@2x.png" "32:icon_32x32.png" "64:icon_32x32@2x.png" "128:icon_128x128.png" "256:icon_128x128@2x.png" "256:icon_256x256.png" "512:icon_256x256@2x.png" "512:icon_512x512.png" "1024:icon_512x512@2x.png"; do
  size="${spec%%:*}"
  name="${spec#*:}"
  /usr/bin/sips -z "${size}" "${size}" "${TEMP_DIR}/icon-master.png" --out "${iconset}/${name}" >/dev/null
done
/usr/bin/iconutil -c icns "${iconset}" -o "${TEMP_DIR}/PromptVault.icns"

/bin/cp "${TEMP_DIR}/PromptVault.icns" "${TEMP_DIR}/PromptVault.app/Contents/Resources/applet.icns"
/usr/libexec/PlistBuddy -c "Set :CFBundleName PromptVault" "${TEMP_DIR}/PromptVault.app/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName PromptVault" "${TEMP_DIR}/PromptVault.app/Contents/Info.plist" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string PromptVault" "${TEMP_DIR}/PromptVault.app/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier com.promptvault.local-launcher" "${TEMP_DIR}/PromptVault.app/Contents/Info.plist" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string com.promptvault.local-launcher" "${TEMP_DIR}/PromptVault.app/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleIconFile applet" "${TEMP_DIR}/PromptVault.app/Contents/Info.plist"
for key in \
  LSRequiresCarbon \
  NSAppleEventsUsageDescription \
  NSAppleMusicUsageDescription \
  NSCalendarsUsageDescription \
  NSCameraUsageDescription \
  NSContactsUsageDescription \
  NSHomeKitUsageDescription \
  NSMicrophoneUsageDescription \
  NSPhotoLibraryUsageDescription \
  NSRemindersUsageDescription \
  NSSiriUsageDescription \
  NSSystemAdministrationUsageDescription
do
  /usr/libexec/PlistBuddy -c "Delete :${key}" "${TEMP_DIR}/PromptVault.app/Contents/Info.plist" 2>/dev/null || true
done
/usr/libexec/PlistBuddy -c "Add :LSUIElement bool true" "${TEMP_DIR}/PromptVault.app/Contents/Info.plist"
/usr/bin/codesign --force --deep --sign - "${TEMP_DIR}/PromptVault.app" >/dev/null

if [[ -e "${APP_PATH}" ]]; then
  /bin/mv "${APP_PATH}" "${TEMP_DIR}/previous-PromptVault.app"
fi
/bin/mv "${TEMP_DIR}/PromptVault.app" "${APP_PATH}"

print -r -- "Created ${APP_PATH}"
print -r -- "Project root: ${PROJECT_ROOT}"
print -r -- "Drag the app to the Dock if you want one-click access there."

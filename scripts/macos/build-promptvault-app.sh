#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
OUTPUT_DIR="${1:-${HOME}/Applications}"
TEMP_DIR="$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/promptvault-app.XXXXXX")"

# Keep the generated source and bundle together for inspection or recovery.
/usr/bin/sed "s|__LAUNCHER_PATH__|${SCRIPT_DIR}/promptvault-launcher.sh|g" \
  "${SCRIPT_DIR}/PromptVault.applescript" > "${TEMP_DIR}/PromptVault.applescript"
/usr/bin/osacompile -o "${TEMP_DIR}/PromptVault.app" "${TEMP_DIR}/PromptVault.applescript"

for existing in "${HOME}/Applications/PromptVault.app" "${HOME}/Desktop/PromptVault.app"; do
  if [[ -f "${existing}/Contents/Resources/applet.icns" ]]; then
    /bin/cp "${existing}/Contents/Resources/applet.icns" "${TEMP_DIR}/PromptVault.app/Contents/Resources/applet.icns"
    break
  fi
done

PLIST="${TEMP_DIR}/PromptVault.app/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleName PromptVault" "${PLIST}"
/usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string PromptVault" "${PLIST}"
/usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string com.promptvault.local-launcher" "${PLIST}"
/usr/libexec/PlistBuddy -c "Set :CFBundleIconFile applet" "${PLIST}"
/usr/libexec/PlistBuddy -c "Add :LSUIElement bool true" "${PLIST}"
# osacompile supplies permission descriptions unused by this launcher.
for key in LSRequiresCarbon NSAppleEventsUsageDescription NSAppleMusicUsageDescription \
  NSCalendarsUsageDescription NSCameraUsageDescription NSContactsUsageDescription \
  NSHomeKitUsageDescription NSMicrophoneUsageDescription NSPhotoLibraryUsageDescription \
  NSRemindersUsageDescription NSSiriUsageDescription NSSystemAdministrationUsageDescription; do
  /usr/libexec/PlistBuddy -c "Delete :${key}" "${PLIST}" 2>/dev/null || true
done
/usr/bin/codesign --force --deep --sign - "${TEMP_DIR}/PromptVault.app"
mkdir -p "${OUTPUT_DIR}"
/usr/bin/ditto "${TEMP_DIR}/PromptVault.app" "${OUTPUT_DIR}/PromptVault.app"
print -r -- "Created ${OUTPUT_DIR}/PromptVault.app"

#!/bin/bash
# 复制到项目 scripts/build-dmg.sh；适配区以下保留共同流程。
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

# --- 项目适配：名称、资源位置、签名身份和两个函数 ---
APP_NAME="ExampleApp"
PRODUCT_NAME="$APP_NAME"
INFO_PLIST="$PROJECT_ROOT/Resources/Info.plist"
OUTPUT_DIR="$PROJECT_ROOT/dist"
: "${SIGNING_IDENTITY:?Set SIGNING_IDENTITY to the configured Apple Development identity}"

build_app() {
    # 默认示例为 SwiftPM；Xcode 项目在这里构建 Release 并将 App 复制到 APP_PATH。
    swift build -c release --product "$PRODUCT_NAME"
    local bin_dir
    bin_dir="$(swift build -c release --show-bin-path)"
    mkdir -p "$APP_PATH/Contents/MacOS" "$APP_PATH/Contents/Resources"
    cp "$bin_dir/$PRODUCT_NAME" "$APP_PATH/Contents/MacOS/$PRODUCT_NAME"
    cp "$INFO_PLIST" "$APP_PATH/Contents/Info.plist"
    # 在此加入本项目图标、资源 bundle、动态库及 helper；全部在签名前完成。
}

sign_app() {
    # 有嵌套代码时，在主 App 前逐项签署；各组件使用自己的 entitlements。
    # 主 App 所需的 --entitlements、--options 等参数也在此沿用项目配置。
    codesign --force --sign "$SIGNING_IDENTITY" --timestamp=none "$APP_PATH"
}
# --- 共同流程 ---

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/macos-package.XXXXXX")"
STAGE="$WORK_DIR/volume"
APP_PATH="$STAGE/$APP_NAME.app"
DMG_TO_CLEAN=""

cleanup() {
    local status=$?
    trap - EXIT
    if [[ -n "$DMG_TO_CLEAN" ]]; then
        rm -f "$DMG_TO_CLEAN"
    fi
    rm -rf "$WORK_DIR"
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

mkdir -p "$STAGE" "$OUTPUT_DIR" "$WORK_DIR/tools"
# 工具产生的临时文件也归本次操作清理；项目编译缓存仍留在原位置。
export TMPDIR="$WORK_DIR/tools/"
printf '构建并组装 Release App\n'
build_app
VERSION="$(plutil -extract CFBundleShortVersionString raw "$APP_PATH/Contents/Info.plist")"
EXECUTABLE="$(plutil -extract CFBundleExecutable raw "$APP_PATH/Contents/Info.plist")"
ARCHITECTURES="$(lipo -archs "$APP_PATH/Contents/MacOS/$EXECUTABLE")"
printf '签署 App\n'
sign_app

# 名称只含产品、实际版本和实际架构；已有项目可在此沿用原固定命名。
DMG_PATH="$OUTPUT_DIR/$APP_NAME-$VERSION-${ARCHITECTURES// /-}.dmg"
if [[ -e "$DMG_PATH" ]] && lsof -t "$DMG_PATH" >/dev/null 2>&1; then
    printf '镜像仍在使用，请先卸载或关闭占用：%s\n' "$DMG_PATH" >&2
    exit 1
fi
rm -f "$DMG_PATH"
DMG_TO_CLEAN="$DMG_PATH"

ln -s /Applications "$STAGE/Applications"
printf '创建 DMG: %s\n' "$DMG_PATH"
hdiutil create -volname "$APP_NAME" -srcfolder "$STAGE" -format UDZO "$DMG_PATH"
DMG_TO_CLEAN=""
printf 'DMG: %s\n版本: %s\n配置: Release\n架构: %s\n签名: Apple Development（未公证）\n' \
    "$DMG_PATH" "$VERSION" "$ARCHITECTURES"

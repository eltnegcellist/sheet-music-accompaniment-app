# macOS 野良配布ガイド (Unsigned Distribution)

Apple Developer Program に加入せず、未署名 DMG として配布するための手順。

## トレードオフ

野良配布を選ぶと:

- **配布側**: Apple Developer Program 登録 ($99/年) と notarization の手間が一切不要。リリースまで全行程ローカル完結。
- **ユーザー側**: 初回起動時に Gatekeeper の警告（"開発元を確認できないため開けません"）が出る。手動で「とにかく開く」操作が必要。
- **将来リスク**: macOS は年々 Gatekeeper を厳格化している。現時点で「とにかく開く」は残っているが、将来のメジャーアップデートで未署名アプリの実行が完全にブロックされる可能性は否定できない。配布規模が大きくなる場合は Developer ID への移行を検討。

## ビルド前提

```sh
brew install tesseract poppler gradle git
```

加えて Xcode Command Line Tools, Rust, Node 18+, Python 3.11+。

## ビルドパイプライン

```sh
# 0. ランタイムツリー (JRE / Audiveris / Tesseract / Poppler) を生成。
#    Audiveris/JRE/Poppler のバージョン変更時のみ再実行。
scripts/fetch_runtime_macos.sh

# 1. PyInstaller サイドカーを --onefile モードでビルド。
scripts/build_sidecar.sh --onefile

# 2. .app をビルド。tauri.conf.json で targets=["app"] にしているので
#    Tauri 1.x の不安定な bundle_dmg.sh は走らない。
npm run tauri:build --prefix frontend

# 3. Adoptium の legal/ ツリーを .app 内に復元。
#    fetch_runtime_macos.sh が provenance 属性回避のため
#    resources/ の外に退避させているのを戻すステップ。
scripts/post_bundle_macos.sh

# 4. ad-hoc 署名 (codesign -s -)。Hardened Runtime と entitlements は
#    付けない (notarization 前提のため野良では不要)。
#    bundle_macho_macos.sh の install_name_tool 改変で無効になった
#    Poppler dylib の署名と、Tauri が未署名で残した .app 全体を
#    ad-hoc で署名し直す。
scripts/sign_adhoc_macos.sh

# 5. hdiutil で DMG にラップ。
scripts/build_dmg_macos.sh
# → dist/IMSLP-Accompanist-<version>.dmg
```

## エンドユーザー向け配布手順

DMG と一緒に下記の指示文を渡すか、README に記載すること。

### 初回起動

1. DMG をダウンロードしてダブルクリックしマウント。
2. `IMSLP Accompanist.app` を `/Applications` フォルダにドラッグ。
3. **Finder で `/Applications` を開き、`IMSLP Accompanist` を右クリック → 「開く」**。
   ダブルクリックで起動しようとすると "開発元を確認できないため開けません"
   のダイアログが出てしまい、macOS Sequoia 以降は右クリック→開くでも
   弾かれる場合がある。
4. それでも警告ダイアログが出る場合:
   - **macOS Ventura 以前**: ダイアログの「キャンセル」を押した後、
     **システム設定 → プライバシーとセキュリティ** を開き、画面下部の
     「"IMSLP Accompanist" は開発元を確認できないためブロックされました」
     の右にある **「このまま開く」** をクリック。次回起動時は警告なし。
   - **macOS Sonoma / Sequoia / Tahoe**: 上記と同じ場所に
     **「とにかく開く」** ボタンが出る。クリック後にもう一度起動。
5. それでもブロックされる場合、ターミナルで quarantine 属性を剥がす:
   ```sh
   xattr -dr com.apple.quarantine "/Applications/IMSLP Accompanist.app"
   ```
   その後、もう一度ダブルクリックで起動。

### 動作しない場合のデバッグ

- アプリがクラッシュ／無音終了する場合、`Console.app` で
  "IMSLP Accompanist" でフィルタしてエラーログを確認。
- ターミナルから直接起動するとサイドカー (Python バックエンド) の
  ログが見える:
  ```sh
  "/Applications/IMSLP Accompanist.app/Contents/MacOS/IMSLP Accompanist"
  ```

## ビルド側のトラブルシュート

### `codesign --verify` が `code object is not signed at all` で失敗

`sign_adhoc_macos.sh` を再実行。順序は厳守:
fetch_runtime → tauri:build → post_bundle → sign_adhoc → build_dmg。
post_bundle 後に何かファイルを書き換えたら sign_adhoc を再実行する必要がある。

### `pdf2image failed: Unable to get page count` が起動ログに出る

`runtime/poppler/bin` が `.app` 内に正しくバンドルされていない、または
`main.rs` の PATH 注入が効いていない可能性。`.app` 内を確認:

```sh
APP="frontend/src-tauri/target/release/bundle/macos/IMSLP Accompanist.app"
ls "$APP/Contents/Resources/resources/runtime/poppler/bin"
# pdftoppm pdfinfo pdfseparate pdfunite pdftocairo が並んでいるはず
```

### Tesseract が動かない（OCR が一切走らない）

`runtime/tesseract/{bin,lib}` が `.app` 内に正しくバンドル
されているか確認:

```sh
APP="frontend/src-tauri/target/release/bundle/macos/IMSLP Accompanist.app"
ls "$APP/Contents/Resources/resources/runtime/tesseract/bin"
# tesseract が見える
ls "$APP/Contents/Resources/resources/runtime/tesseract/lib"
# libtesseract.X.dylib, libleptonica.X.dylib, …
```

それでも動かない場合は `otool -L` でロード対象パスを確認:

```sh
otool -L "$APP/Contents/Resources/resources/runtime/tesseract/bin/tesseract"
# @loader_path/../lib/lib*.dylib に書き換わっていれば OK
# /opt/homebrew/... が残っていたら fetch_runtime_macos.sh を再実行
```

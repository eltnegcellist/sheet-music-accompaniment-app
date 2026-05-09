# Bundled resources

`tauri.conf.json` ships everything under this directory through Tauri's
`bundle.resources` glob. The two subdirectories that go under here at
build time are gitignored because they're large per-platform vendored
trees:

* `runtime/jre/`        — jlink-trimmed Temurin JRE
* `runtime/audiveris/`  — Audiveris install (built via `gradlew installDist` on
                          macOS/Windows, extracted from the .deb on Linux)
* `runtime/tessdata/`   — Tesseract language packs
* `tesseract/`          — Tesseract binary (system or Homebrew copy)

Run the matching `scripts/fetch_runtime_<os>.{sh,ps1}` to populate these
before `npm run tauri:build`. See the migration plan
(`docs/tauri_migration_plan.md`) for the assembly details.

This README is committed so that `tauri-build`'s `bundle.resources`
glob has at least one file to match during `cargo check`, before the
real runtime tree is staged.

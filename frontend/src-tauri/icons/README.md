# Icons

Tauri's bundle step (`npm run tauri:build`) needs the icon files listed
in `tauri.conf.json` (`tauri.bundle.icon`). They are not committed to
the repository because they are derived assets.

Generate them once from a 1024x1024 PNG source:

```bash
npx @tauri-apps/cli icon path/to/source-1024.png -o frontend/src-tauri/icons
```

Until the icons are generated, `tauri:dev` will still work but
`tauri:build` will fail with a "couldn't read icon" error. CI is
expected to run the `tauri icon` step before `tauri build`.

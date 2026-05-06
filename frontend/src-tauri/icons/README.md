# Icons

Tauri's bundle step (`npm run tauri:build`) and even `cargo check`
(via `tauri-build` in `build.rs`) need the icon files listed in
`tauri.conf.json` (`tauri.bundle.icon`) to actually exist on disk.

The PNG / ICO / ICNS files committed here are **placeholders** — a
solid-colour disc generated programmatically so CI builds stay
green without a real logo. Replace them when a designed icon set
lands.

To regenerate from a 1024x1024 PNG source:

```bash
npx @tauri-apps/cli icon path/to/source-1024.png -o frontend/src-tauri/icons
```

That command also emits Windows Store-specific assets
(`Square*Logo.png`, `StoreLogo.png`) which are not referenced from
`tauri.conf.json`; delete them after generation to keep the directory
minimal unless you intend to ship a UWP build.

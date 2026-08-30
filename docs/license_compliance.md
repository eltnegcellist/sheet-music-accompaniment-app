# License compliance for releases

IMSLP Accompanist is distributed under `AGPL-3.0-or-later`. The app also
bundles Audiveris 5.10.2, which is AGPL-licensed. This checklist is part of the
release process; it is not legal advice.

## Release checklist

1. Keep `LICENSE`, `THIRD_PARTY_NOTICES.md`, copyright notices, and dependency
   license files intact in source and binary distributions.
2. Publish the complete corresponding source for the exact binary, including
   build and packaging scripts. Create tag `vX.Y.Z` from the shipped commit.
3. Make the source offer easy to find in the application and on the release
   page. The in-app link for 0.1.1 points to tag `v0.1.1`, so create that tag
   before publishing the binary.
4. Run `scripts/validate_bundle.sh` after staging runtimes and the sidecar.
5. Run `scripts/post_bundle_macos.sh` after Tauri packaging. It adds the app,
   Audiveris, and runtime license files to the `.app`.
6. Build the DMG with `scripts/build_dmg_macos.sh`; verify its
   `Open Source Licenses` folder before uploading.
7. Do not impose additional restrictions that conflict with the AGPL, and
   provide installation information required for modified consumer-device
   versions when AGPL section 6 applies.
8. If users interact with a modified version over a network, preserve the
   prominent source-code offer required by AGPL section 13.

The existing 0.1.0 binary predates this compliance work. Replace it with a
0.1.1 build made from the matching tagged source rather than presenting 0.1.0
as the compliant release.

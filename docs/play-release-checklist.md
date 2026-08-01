# Google Play — release checklist (account, signing, rollout)

The repo side is done: CI builds a release-signed AAB and can auto-upload it
to Play. This checklist covers the parts that require your Google account and
a few permanent decisions. Work top to bottom.

---

## 1. Permanent decisions (cannot change after first publish)

| Decision | Current value | Notes |
| --- | --- | --- |
| **Application ID** | `app.mdown.mdown` | From `[tool.flet] org="app.mdown", project="mdown"`. Confirm this is final — it is the package name forever. To change it, edit `pyproject.toml` **before** the first upload. |
| **App name** | `MDown: Document to Markdown` | Editable later in the listing, but pick something you like. |
| **Account type** | *your choice* | **Personal** vs **Organization** — this sets your timeline (see §3). |

---

## 2. Developer account (Cluster D)

- [ ] Create a Google Play Developer account ($25 one-time) at
      https://play.google.com/console
- [ ] Complete identity/address verification (can take a few days — start now)
- [ ] Create the app → set default language, app name, "App" type, Free
- [ ] Reserve the application ID `app.mdown.mdown` on first upload

## 3. The timeline fork (personal accounts only)

New **personal** developer accounts must run **closed testing with at least
12 testers for 14 continuous days** before they can request production
access. **Organization** accounts skip this.

- [ ] If personal: recruit 12+ testers early (emails or a Google Group);
      you will add them to the closed-testing track in §6.
- [ ] The 14-day clock starts when testing begins — front-load it.

## 4. Signing (Cluster B — one-time setup)

- [ ] Generate the upload keystore (keep it forever):
      ```
      keytool -genkey -v -keystore upload-keystore.jks \
        -keyalg RSA -keysize 2048 -validity 10000 -alias upload
      ```
- [ ] Add repo secrets (Settings → Secrets and variables → Actions):
      `ANDROID_KEYSTORE_B64` (= `base64 -w0 upload-keystore.jks`),
      `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_PASSWORD`,
      `ANDROID_KEY_ALIAS` (`upload`)
- [ ] In Play Console, enrol the app in **Play App Signing** (default) — you
      upload with the upload key; Google manages the app signing key.

## 5. CI auto-upload (Cluster F — optional but recommended)

The `android` job uploads the AAB to the **internal** track on any `v*` tag,
when signed and given a service account. To enable:

- [ ] Play Console → Setup → API access → create/link a Google Cloud service
      account; grant it the "Release to testing tracks" permission.
- [ ] Download the service-account JSON key.
- [ ] Add it as the repo secret **`PLAY_SERVICE_ACCOUNT_JSON`** (paste the
      full JSON).
- [ ] Confirm `packageName` in `.github/workflows/build.yml` matches the
      generated `applicationId` (`app.mdown.mdown` unless you changed it).
- [ ] First upload to a track must be done **manually** in the Console (Play
      requires the initial release by hand); CI automation works for
      subsequent uploads.

Without `PLAY_SERVICE_ACCOUNT_JSON` the upload step logs a warning and skips
— the build still succeeds and the AAB is available as the `mdown-android-aab`
artifact to upload by hand.

## 6. Store listing & compliance (Cluster E)

From `docs/play-store-listing.md`:

- [ ] Main store listing: name, short + full description
- [ ] Upload `assets/play/icon-512.png` and
      `assets/play/feature-graphic-1024x500.png`
- [ ] Capture and upload 2–8 phone screenshots
- [ ] Privacy policy: fill placeholders in `docs/privacy-policy.html`, enable
      GitHub Pages (Settings → Pages → `main` / `/docs`), set the URL in Play
- [ ] Data safety form: "no data collected/shared"
- [ ] Content rating questionnaire → Everyone
- [ ] Target audience 13+, Ads = No

## 7. Release flow

- [ ] Cut a version: bump `version` in `pyproject.toml`, commit, tag `vX.Y.Z`,
      push the tag → CI builds a signed AAB (versionCode = run number)
- [ ] **Internal testing** → install on your own device, sanity check
- [ ] **Closed testing** → run the 14-day period if on a personal account
- [ ] **Production** → submit for review (first review can take days), then
      staged rollout (e.g. 20% → 100%)

---

### Status summary

| Cluster | State |
| --- | --- |
| A — Build system (AAB) | ✅ done in CI |
| B — Signing wiring | ✅ done; needs your keystore + 4 secrets |
| C — Icon / manifest audit | ✅ done |
| D — Developer account | ⬜ your action (§2) |
| E — Listing + legal | ✅ drafted (`play-store-listing.md`, `privacy-policy.html`); needs your details + screenshots |
| F — Release automation | ✅ done; needs `PLAY_SERVICE_ACCOUNT_JSON` + first manual release |

# Release guide

How to cut a release and get it in front of testers. Prerequisites (signing
secrets, Play account, `PLAY_SERVICE_ACCOUNT_JSON`) are in
[play-release-checklist.md](play-release-checklist.md).

## Cut a release in one command

```bash
python scripts/release.py patch      # 0.1.0 -> 0.1.1  (bug fixes)
python scripts/release.py minor      # 0.1.0 -> 0.2.0  (new features)
python scripts/release.py major      # 0.1.0 -> 1.0.0  (breaking)
python scripts/release.py 0.4.2      # explicit version
```

This bumps `version` in `pyproject.toml`, commits `Release vX.Y.Z`, and
creates an annotated `vX.Y.Z` tag locally. Preview first with `--dry-run`; it
refuses to run on a dirty tree or a tag that already exists.

Add `--push` to publish immediately:

```bash
python scripts/release.py patch --push
```

or push by hand afterwards:

```bash
git push origin <branch> && git push origin vX.Y.Z
```

## What happens after the tag lands

1. CI builds a **signed AAB** (versionName from `pyproject`, **versionCode =
   CI run number** — always increasing) plus an APK for sideloading.
2. If `PLAY_SERVICE_ACCOUNT_JSON` is set, CI uploads the AAB to Play's
   **internal** track automatically. Otherwise grab the `mdown-android-aab`
   artifact and upload it by hand.
3. In Play Console, promote the release: internal → closed → production.

> The **first** upload for a brand-new app must be done manually in the
> Console; CI automation covers every release after that.

## Tag cheat-sheet

```bash
git tag                     # list tags
git tag -d v0.1.1           # delete a local tag (before pushing)
git push origin :v0.1.1     # delete a pushed tag (stops/rebuilds a release)
git describe --tags         # what version is HEAD near
```

Never reuse a version number: Play rejects a duplicate versionCode/versionName.
Bump and tag again instead.

---

## Tester-recruitment email

New **personal** Play accounts must run closed testing with **12+ testers for
14 continuous days** before production. Recruit early. Template:

> **Subject:** Help me test MDown (Android) — 2 minutes to opt in
>
> Hi [NAME],
>
> I'm releasing a small Android app, **MDown** — it converts documents (Word,
> PDF, Excel, PowerPoint, and more) into Markdown, entirely on your phone. No
> ads, no accounts, nothing leaves your device.
>
> I need a handful of testers to opt in so Google will let me publish. It
> takes about two minutes and you can uninstall anytime:
>
> 1. Reply with the **Google account email** you use on your Android phone.
> 2. I'll add you as a tester and send back an opt-in link.
> 3. Tap the link, then "Download it on Google Play," and install.
>
> That's it — you don't have to actively do anything after installing; just
> keeping it for two weeks helps. Feedback welcome but optional.
>
> Thanks so much,
> [YOUR NAME]

**Logistics tips**
- Collect tester emails into a **Google Group** and add the group to the
  closed-testing track — easier than managing addresses individually.
- You can be one of your own testers, but you still need 12 total.
- The 14-day clock is continuous; testers leaving mid-window can reset it, so
  over-recruit (aim for ~15).

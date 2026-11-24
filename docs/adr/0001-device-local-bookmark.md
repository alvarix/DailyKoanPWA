# 0001 — Device-local bookmark and device-rendered push

Status: Accepted. Supersedes the shared selection and content-bearing push decisions in `data-model.md` and `push-pipeline.md`; delivery timing and subscription retention remain unchanged.

## Context

A public progression endpoint changed the reading position for every visitor. A push cannot know a private browser bookmark without restoring shared state or adding identity.

## Decision

Store Hold/Daily and the bookmark in browser storage. Flask serves today's UTC date-hash koan and explicit deep links. Settings migration v3 removes shared selection settings and retains the old index as a read-only seed until a future cleanup after device verification. Push sends the same trigger and public daily text to every subscription. The worker reads a device-local CacheStorage snapshot to display the held text with an empty title. The snapshot is not part of the versioned shell cache. Tapping opens `/`.

Held navigations carry a transient marker so a stale index can return usable daily HTML with a 404, reset the bookmark, and show a toast. Direct invalid links still return their normal 404.

## Consequences

No bookmark sync across devices; clearing local storage loses progress. Held home loads use an extra navigation. Back up SQLite before deploy. Highest risks are iOS notification-tap behavior and first-run seeding; retest on the installed app and restore the backup if rolling back to shared progression, since v3 removes rows older code needs.

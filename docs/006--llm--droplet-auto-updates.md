# DailyKoanPWA droplet: automatic updates and email reports

## Goal

Recreate the useful parts of the WMW setup without depending on Laravel Forge: daily Ubuntu security updates, automatic nginx and PHP updates from their verified package sources **if this droplet uses them**, and a Brevo email summarizing each update run. Keep whole-droplet reboots manual. Leave regular Ubuntu `-updates` off unless we explicitly decide to include it.

Do not assume this droplet uses WMW’s Ubuntu release, nginx repository, PHP versions, or mail setup. Start with discovery. Work one change at a time and ask before making production changes.

## Work in three chunks

### 1. Inventory the droplet and verify email

- Identify the Ubuntu version, web server, app runtime, installed packages, and APT origins. Check `apt-cache policy`, `apt-config dump`, and `systemctl list-timers --all apt-daily.timer apt-daily-upgrade.timer`. If the app uses containers or packages installed outside APT, identify their separate update path.
- Verify the latest completed DigitalOcean backup, console access, and the restore procedure. Record a public HTTPS check and an app-specific smoke test to repeat after changes. A private clone is an optional precaution, not a prerequisite; without one, live package behavior and restore time remain untested.
- If the droplet already has working system mail, test it before adding anything. Otherwise, reuse WMW’s `docs/scripts/brevo-update-mail.py` as a starting point. Adapt the hostname, site URL, and service names in its reboot instructions. Use a dedicated Brevo transactional API key, an approved sender, and a monitored recipient. Store the key as a root-only systemd credential; don’t put it in Git, command arguments, or logs.
- If using the adapter, scope the Sendmail override to `apt-daily-upgrade.service` rather than replacing system Sendmail. Don’t start or flush an old mail queue as part of this work. Send one synthetic report without running APT, then verify that a real scheduled report arrives under the existing update policy. The email should show result, package changes, and reboot instructions when flagged; keep raw logs on the droplet. Use `MailReport "always"` initially; consider `"on-change"` once delivery works.

### 2. Patch and verify the installed software

- Check which updates are pending. If nginx or PHP needs a package-source or major-version switch, do it manually in a separate window. Simulate first and inspect removals, config ownership, modules, and service changes. WMW’s initial nginx vendor switch left nginx stopped despite a passing config test; don’t assume the package will restart it here.
- After each update, verify the installed version, that the running service is using it, and that public HTTPS and the app smoke test pass. If the update fails, stop before changing anything else. Diagnose from the service and APT logs or use the agreed recovery path.

### 3. Enable routine unattended updates

- Keep the existing daily systemd timer; no new cron job is needed. Add exact origin rules only for verified repositories you want to trust. A third-party origin can supply routine updates and shared dependencies, not just security patches or the named runtime.
- Run `sudo unattended-upgrade --dry-run --debug` and review the allowed origins and proposed changes before leaving it unattended. An empty preview confirms there is nothing eligible now, not that the next vendor update will work. Verify the first real vendor update using the email, service state, running version, and public smoke test.
- Keep automatic reboots off. When a report flags a reboot, choose a quiet window, confirm no APT/dpkg operation is active, reboot manually, then check the running kernel, services, and public site. Use an external uptime alert as well as email; a successful update report is not proof the site is healthy.

## Reference and review

WMW reference: `docs/004.1--llm--ubuntu-auto-updates.md` and
`docs/scripts/brevo-update-mail.py`.

Peer review emphasized verifying package provenance and recovery access, testing
actual inbox delivery, and assigning someone to act on reboot alerts. This
brief includes those checks; it does not assume a clone, automatic rollback,
or an application migration.
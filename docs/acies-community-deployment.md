# ACIES community beta

Community mode runs the original Android 1v1 simulation with an authenticated HTTP API and TCP gateway. Players register or sign in with a username and password from the game's existing title-screen account picker. The gateway forwards the same frame-numbered inputs to each player. The Android simulation advances at 40 Hz and the gateway sends updates at 20 Hz.

The initial release supports unranked 1v1 on Windmill Boot Camp. Accounts, decks, clan membership, and completed match results persist in one SQLite database. The gateway keeps active matches and reconnect history in memory. A restart ends active matches. Rankings, TV replays, other PvP modes, and independent result verification are future work. In-game chat is off by default. Open registration is opt-in and has no self-service password recovery.

## Run a small VPS beta

These instructions use a dedicated Ubuntu or Debian VPS with an IPv4 DNS record for the release hostname. If you publish an IPv6 DNS record, verify that the VPS accepts HTTPS and gateway connections over IPv6 too. Allow TCP ports 80, 443, and 9443 through the VPS firewall. Keep the Python HTTP and gateway ports bound to loopback.

1. Install `python3`, `openssl`, `nginx`, `libnginx-mod-stream`, and `certbot`. Place the repository's small source files at `/opt/acies` and create a system user and group named `acies`. The Python server needs the `openssl` CLI for legacy client payloads. Community account passwords use salted PBKDF2-HMAC-SHA256 with 600,000 iterations. [OWASP password storage guidance](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html#pbkdf2)
2. Obtain a certificate for the new hostname. On a fresh VPS, `certbot certonly --standalone -d <hostname>` can obtain the first certificate while port 80 is free. After bringing up Nginx, configure Certbot renewal with webroot `/var/www/acme` and reload Nginx after successful renewal. The same certificate covers HTTPS on 443 and gateway TLS on 9443.
3. Copy the HTTPS fragment to `/etc/nginx/conf.d/acies.conf` and the stream fragment to `/etc/nginx/acies-stream.conf`. Replace `acies.example.com` and verify the certificate paths in both fragments. Add `stream { include /etc/nginx/acies-stream.conf; }` at the top level of `/etc/nginx/nginx.conf`, or include the fragment from the existing `stream` block. Run `nginx -t` before reloading.
4. Copy `deploy/community.env.example` to `/etc/acies/community.env` and set `ACIES_ORIGIN` to the exact HTTPS origin embedded in the APK. Copy the three `deploy/acies-community*` systemd units to `/etc/systemd/system/`. Then run:

   ```sh
   sudo systemctl daemon-reload
   sudo systemctl enable --now acies-community.service acies-community-backup.timer
   curl -fsS https://acies.example.com/community/health
   curl -fsS http://127.0.0.1:8080/community/metrics
   ```

   The metrics route is available through the VPS loopback. Nginx blocks it on the public endpoint. The backup timer keeps roughly two weeks of database snapshots under `/var/lib/acies/backups`. Copy backups to separate storage, protect them like account credentials, and verify a restore before depending on them. Restore with the community service stopped and the backup as the sole `community.sqlite3` database, without stale WAL files from the previous database.

5. Generate one code per tester. The operator sees each plaintext code once. Default validity is 48 hours.

   ```sh
   cd /opt/acies
   sudo -u acies python3 tools/acies_accounts.py /var/lib/acies/community.sqlite3 invite
   ```

Invite-only registration is the default. Set `ACIES_FLAGS=--open-registration` and restart the service when opening registration. Keep a separate test database and use a separate hostname for release candidates. The beta accepts complementary client results for match history. Leave competitive ranking disabled until a server-side verifier can independently confirm outcomes.

## Build and distribute the Android client

The community APK uses package ID `com.creagames.clashoflegions.community`, supports ARM64 devices running Android 7.0 or later, and builds from the original 2.5.1 APK. It can coexist with the original or the `.local` lab build. Install `apktool`, a JDK, and the Android SDK with an NDK, platform `android-35`, and build tools `36.0.0`.

```sh
python3 tools/build_acies_community.py acies.apk work/acies-community-unsigned.apk \
  --origin https://acies.example.com --sdk "$ANDROID_HOME"
"$ANDROID_HOME/build-tools/36.0.0/zipalign" -P 16 -f 4 \
  work/acies-community-unsigned.apk work/acies-community-aligned.apk
"$ANDROID_HOME/build-tools/36.0.0/apksigner" sign --ks /secure/path/acies-release.jks \
  --out work/acies-community.apk work/acies-community-aligned.apk
"$ANDROID_HOME/build-tools/36.0.0/apksigner" verify --verbose work/acies-community.apk
```

Keep release signing keys private and reuse the same release key for updates. Use a trusted public certificate for the release server. `--ca-cert` embeds a private certificate authority for a local test build. After verification, place the signed release APK and its SHA-256 checksum under `/srv/acies/downloads/` to serve them over HTTPS. The APK is about 680 MiB, so make sure the hosting quota covers downloads.

After the title screen's first-run terms, select **Create account**, enter the username, password, and invitation code, and submit the form. Returning players can select **Continue as …** to use the encrypted session on that device. **Sign in** accepts a username and password on any supported Android device, including when switching accounts. Google Play Games and the store connection are skipped during sign-in.

New accounts start the campaign tutorial. The server stores campaign results and lobby tutorial steps in SQLite for the signed-in account. Once that account finishes the campaign tutorial, sign-in restores Team Battle and the other feature unlocks without replaying their notices or restarting the old lobby walkthrough, which depends on the original shop. Existing community accounts that previously skipped onboarding keep access to the lobby. The Android client also stores unsent results and reconnect records under the signed-in player's ID. Records already saved on the server remain available after the APK update.

## Verify locally and before opening registration

```sh
python3 -m unittest discover -s tests -v
```

The integration tests put independent accounts behind the same source IP and cover credential isolation, persistence of tutorial progress across restarts, native gateway authentication, a missed order on reconnect, atomic match-result storage, and revocation. The OnePlus N100 and Pixel lab phones registered or signed in from the native title picker, entered the same 1v1, constructed barracks, summoned Hounds, and issued a movement order through the TLS gateway. A surrender produced complementary win and loss records in SQLite.

Use the lab phones or Fold7 for Android verification. For a local run, configure the Nginx HTTPS fragment on 8443 and the stream fragment on 9443. Use a test certificate with `IP:127.0.0.1` in its subject alternative names and protect its private key. Build the APK with `--origin https://127.0.0.1:8443 --gateway-port 9443 --ca-cert /path/to/test-ca.pem`, set the same admission URL on the Python server, and forward both ports for each device:

```sh
adb -s DEVICE_SERIAL reverse tcp:8443 tcp:8443
adb -s DEVICE_SERIAL reverse tcp:9443 tcp:9443
```

The API health endpoint should work through Nginx. The direct Python listeners remain on loopback. The standard production build uses the host's publicly trusted certificate and its real hostname.

For the first VPS test, put two phones on independent connections, such as Wi-Fi and mobile data. Create separate accounts, match in **Battle → 1v1**, and play through construction, movement, combat, and use of a deck card. Interrupt one connection, issue an order from the other device, and verify that reconnect applies it once. Finish a match by destroying the opposing base and confirm both players' saved results. Compare both clients at recorded simulation frames before treating cross-device determinism as verified. Repeat the run at the expected latency and concurrent load before opening registration.

# Dell Inspiron 3558 (Ubuntu Server) — always-on setup

Target: Ubuntu Server 26.04 LTS, fixed address 192.168.1.139 (router reservation), user `nomadadmin`, repository in `~/Kindle-Family-Dashboard`. **None of the files below has been run on the Dell yet** except `scripts/kfd setup` and `smoke` (passed). Do the steps in order and report each result.

Adjust the user, address and subnet if yours differ. Keep an SSH session open while changing the firewall.

## 1. Stop the manual server
```bash
cd ~/Kindle-Family-Dashboard && scripts/kfd stop
```

## 2. Keep the laptop awake with the lid closed
```bash
sudo mkdir -p /etc/systemd/logind.conf.d
printf '[Login]\nHandleLidSwitch=ignore\nHandleLidSwitchExternalPower=ignore\nHandleLidSwitchDocked=ignore\n' | sudo tee /etc/systemd/logind.conf.d/kfd.conf
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
sudo systemctl restart systemd-logind    # may end your SSH session; reconnect
```
Battery: keep the laptop on mains and in a ventilated spot. If the battery is removable, run without it. If it is swollen, hot or the case bulges, stop using it. Check for a charge limit with `ls /sys/class/power_supply/BAT0/` (a `charge_control_end_threshold` file means you can cap charging at 80).

## 3. Run the Family Hub as a service (starts on boot, restarts on failure)
```bash
cd ~/Kindle-Family-Dashboard
sed "s|@USER@|$USER|; s|@DIR@|$PWD|" deploy/kfd.service.in | sudo tee /etc/systemd/system/kfd.service >/dev/null
printf 'KFD_PORT=8765\nKFD_PUBLIC_ORIGIN=https://192.168.1.139:8443\n' > data/kfd.env
sudo systemctl daemon-reload && sudo systemctl enable --now kfd
systemctl status kfd --no-pager | head -12
scripts/kfd health
```
Once `KFD_PUBLIC_ORIGIN` is set, the app only accepts requests whose Host is `192.168.1.139:8443`, so the earlier SSH tunnel to `127.0.0.1:8765` stops working; use the HTTPS address from step 5 instead. `scripts/kfd health` still works (it uses loopback).

## 4. Install Caddy (TLS proxy)
```bash
sudo apt install -y caddy
caddy version
sudo cp deploy/Caddyfile.lan.example /etc/caddy/Caddyfile     # edit the address if it differs
sudo systemctl restart caddy && systemctl status caddy --no-pager | head -8
```
If `apt` has no `caddy` package or it is too old to run the file, use Caddy's own apt repository from caddyserver.com/docs/install and report back.

## 5. Firewall
```bash
sudo ufw allow from 192.168.1.0/24 to any port 22 proto tcp
sudo ufw allow from 192.168.1.0/24 to any port 8443 proto tcp
sudo ufw default deny incoming
sudo ufw enable
sudo ufw status verbose
```
No router port-forwarding. Docker is installed on this machine and can publish ports outside ufw's rules; do not run containers that publish ports on this host without checking.

## 6. Get the proxy CA certificate and run the checks
```bash
sudo cp /var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt ~/kfd-root.crt
sudo chown $USER ~/kfd-root.crt
cd ~/Kindle-Family-Dashboard && scripts/lan-check.sh https://192.168.1.139:8443 ~/kfd-root.crt
```
Expect every line `PASS`. If the `root.crt` path does not exist, run `sudo find /var/lib/caddy -name root.crt`.

## 7. Phone and Mac
Copy `kfd-root.crt` to the device (`scp nomadadmin@192.168.1.139:kfd-root.crt .` on the Mac, then AirDrop or share it), install it as a trusted certificate (iPhone: install the profile in Settings, then General → About → Certificate Trust Settings → enable it; Android: Settings → Security → install a CA certificate; Mac: Keychain Access → System → Always Trust), then open `https://192.168.1.139:8443`. The same CA decides whether the Kindle can ever trust this server; that is a Stage B test.

## Operations
`sudo systemctl status|restart|stop kfd`, `journalctl -u kfd -n 50` (the app logs no request data). Updates: `git pull && sudo systemctl restart kfd`. Back up with `python3 -m app.manage backup NEW_DIR` and keep `data/family.sqlite3.key` separately (`BACKUP_RESTORE.md`).

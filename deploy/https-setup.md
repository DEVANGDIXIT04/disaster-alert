# HTTPS / TLS setup (how the `https://` URL works)

The live app is served over HTTPS at **https://65-1-37-139.sslip.io** with a
valid, browser-trusted **Let's Encrypt** certificate — no warnings, and mobile
geolocation ("what's near me") works because the page is now secure.

## Why a `sslip.io` domain?

AWS will not let anyone install a real certificate on the default
`*.elasticbeanstalk.com` address (AWS owns that domain, so it can't be
validated). A certificate needs a domain name we can prove we control.

Rather than buy one, we use **sslip.io** — a free public DNS service that
resolves any `<ip>.sslip.io` name straight to that IP, no signup:

```
65-1-37-139.sslip.io  →  65.1.37.139   (our Elastic Beanstalk instance's Elastic IP)
```

Because the instance has a **static Elastic IP**, this name is stable, and
Let's Encrypt can validate it over HTTP-01 and issue a certificate.

## What was done (one-time)

1. Opened port **443** on the instance security group (80 stays open too).
2. Attached `AmazonSSMManagedInstanceCore` to the instance role so commands can
   be run on the box without SSH keys (via AWS Systems Manager).
3. Installed certbot and issued + wired up the certificate:

```bash
sudo dnf install -y certbot python3-certbot-nginx        # or: pip install certbot certbot-nginx
sudo certbot --nginx -d 65-1-37-139.sslip.io \
     --non-interactive --agree-tos -m 22803031@mail.jiit.ac.in --no-redirect
```

`--no-redirect` keeps plain HTTP working as well, so **both** URLs serve the app:

- `https://65-1-37-139.sslip.io`  (secure — share this one)
- `http://disaster-alert-env.eba-twpixdbf.ap-south-1.elasticbeanstalk.com`  (fallback)

The certificate **auto-renews** (certbot installs a systemd timer); it's valid
90 days at a time.

## Good to know

- HTTPS lives in the instance's nginx config. It survives **reboots**.
- It does **not** automatically survive an `eb deploy` (Beanstalk regenerates
  nginx) or an instance replacement. If you redeploy, just re-run the single
  `certbot --nginx …` command above to restore it — the certificate itself is
  already saved under `/etc/letsencrypt`, so it re-applies in seconds.
- To run that command without SSH, use AWS Systems Manager:
  `aws ssm send-command --instance-ids <id> --document-name AWS-RunShellScript --parameters commands='["sudo certbot --nginx -d 65-1-37-139.sslip.io --non-interactive --agree-tos -m <email> --no-redirect"]'`

## Teardown

Nothing extra to delete — the certificate and port rule disappear when the
Elastic Beanstalk environment is terminated (`eb terminate`).

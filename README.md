# Tempest E-paper Weather Display

Raspberry Pi weather display using Waveshare e-paper 7.5 inch display, Tempest Weather Station data, and Python.

![Screen Output](https://github.com/burke187/Tempest-7.5-E-Paper-Display/blob/master/pic/screen_output.png)

# Versions

## Version 1.1
- Added `setup.sh` to automate installation
- Refactored `weather.py` into fetch/parse/render stages
- Missing readings now display as `-`; a failed API pull shows a warning screen
  with the time of the last attempt

## Version 1.0
- Cleaned up images, debugged, new features, general tweaking of forked version 1.3

# Setup

`setup.sh` handles most of the installation: dependencies, SPI, the `.env` file
and the cron jobs. Three things it cannot do for you — wiring the HAT, and
fetching the two values that sit behind a tempestwx.com login.

## 1. Wire up the display

Follow the WaveShare instructions for the HAT itself:
https://www.waveshare.com/wiki/7.5inch_e-Paper_HAT_(B)_Manual#Working_With_Raspberry_Pi

*Note: see the comments in the code to change from 3 color to 2 color and vice
versa if desired.*

## 2. Collect your Tempest credentials

Do this in a browser **on your workstation**, before you start. Both values are
only visible while logged in to tempestwx.com, so there is no way for a script
to fetch them — and if you are working on a headless Pi over SSH, there is no
browser on the Pi at all.

| Value | Where |
| --- | --- |
| `STATION_ID` | Log in; it is the number in the URL: `https://tempestwx.com/station/XXXXXX` |
| `TEMPEST_TOKEN` | https://tempestwx.com/settings/tokens — create a token and copy it. Treat it as a password. |

The other two settings are handled during setup: `COUNTY_CODE` can be looked up
for you from latitude/longitude, and `TIMEZONE` defaults to `US/Eastern`.

## 3. Copy the repository to the Pi

```bash
scp -r Tempest-7.5-E-Paper-Display/ admin@your-raspberry-pi.local:/home/admin/
```

## 4. Run the setup script

```bash
ssh admin@your-raspberry-pi.local
cd /home/admin/Tempest-7.5-E-Paper-Display
./setup.sh
```

Run it as your normal user, not as root — it calls `sudo` itself where it needs
to. It prompts for the four settings, then writes them to `.env`.

It is safe to re-run: existing `.env` values are offered as defaults, and the
cron jobs are replaced rather than duplicated.

What it does:

| Step | Detail |
| --- | --- |
| Checks the environment | Confirms this is a Pi and that `lib/`, `pic/` and `font/` were all copied across |
| Installs packages | numpy and RPi.GPIO from `apt`; Pillow, requests, pytz, python-dotenv and spidev from `apt` too, falling back to `pip` if `apt` cannot supply them |
| Enables SPI | `raspi-config nonint do_spi 0`, skipped if already on |
| Writes `.env` | Created `chmod 600`, since it holds your API token |
| Looks up `COUNTY_CODE` | Optional: give it latitude/longitude and it queries the NWS for your zone |
| Tests your credentials | Calls the Tempest API so a bad token shows up now, not as a blank screen later |
| Installs cron jobs | Refresh every 5 minutes, plus the 4 AM reboot |

**If SPI was not already enabled, the Pi needs a reboot before the panel will
respond.** The script tells you, and offers to do it (only when run
interactively — it will never reboot on its own during an unattended run).

### Options

```
-y, --yes            Take defaults, never prompt
    --no-cron        Skip installing any cron jobs
    --no-reboot-cron Install the 5-minute refresh job but not the 4 AM reboot
    --skip-apt       Skip apt-get, only verify the Python imports
-h, --help           Show help
```

For an unattended install, pass the settings in the environment:

```bash
STATION_ID=12345 COUNTY_CODE=OHC035 TEMPEST_TOKEN=your-token \
    TIMEZONE=US/Eastern ./setup.sh -y
```

Note that this puts your token in your shell history.

### The cron jobs it installs

```bash
# Tempest e-paper display (managed by setup.sh)
*/5 * * * * /usr/bin/python3 /home/admin/Tempest-7.5-E-Paper-Display/weather.py > /dev/null 2>&1
0 4 * * * /sbin/reboot
```

The first redraws the screen every 5 minutes; output goes to `/dev/null` to save
memory. The second reboots the Pi at 4 AM daily, and can be skipped with
`--no-reboot-cron`.

## Manual setup

<details>
<summary>If you would rather do it by hand, or the script fails partway</summary>

Enable SPI (`sudo raspi-config` → Interface Options → SPI) and reboot, then
install the dependencies:

```bash
sudo apt-get update
sudo apt-get install -y python3-pil python3-numpy python3-requests \
    python3-tz python3-dotenv python3-spidev python3-rpi.gpio
```

Create a file named `.env` in the repository root, next to `weather.py`:

```bash
STATION_ID=12345
COUNTY_CODE=YOURCODE
TEMPEST_TOKEN=your-tempest-token
TIMEZONE=US/Eastern
```

```bash
chmod 600 .env   # it contains your API token
```

- `STATION_ID` is in the URL when you log in: `https://tempestwx.com/station/XXXXXX`
- `TEMPEST_TOKEN` is generated at https://tempestwx.com/settings/tokens
- `TIMEZONE` is a pytz name: https://mljar.com/blog/list-pytz-timezones/
- `COUNTY_CODE` is your NWS zone, which populates Watch/Warning data:
  1. Go to https://www.weather.gov and enter your ZIP code.
  2. After the location loads, click **"Get detailed info"**.
  3. Select your city if needed.
  4. Take the coordinates from the URL and open
     `https://api.weather.gov/points/LAT,LON` — the `"county"` field ends in
     your code, e.g. `OHC035`.

Then add the two cron jobs to the root crontab with `sudo crontab -e`, using the
block shown above.

Use `/usr/bin/python3`, not `python`: current Raspberry Pi OS releases ship no
`python` symlink, so a job calling `python` fails silently.

</details>

# Troubleshooting

Run the script by hand to see what it says — the cron job discards all output:

```bash
sudo /usr/bin/python3 /home/admin/Tempest-7.5-E-Paper-Display/weather.py
```

To keep a history instead, pipe the output through `logger` rather than into a
file of its own:

```bash
*/5 * * * * /usr/bin/python3 /home/admin/.../weather.py 2>&1 | logger -t weather
```

Then read it back with either of:

```bash
journalctl -t weather -n 50
grep weather /var/log/syslog
```

This goes to the system log, which is already size-capped and rotated, so it
cannot grow without bound. **Avoid `>> /var/log/weather.log`** — nothing rotates
a file you create yourself, so it grows forever. For scale, the script emits
roughly 41 KB/day (15 MB/year) at a 5-minute interval.

| Symptom | Likely cause |
| --- | --- |
| `Missing required environment variable` | No `.env`, or a key is missing from it. It must sit next to `weather.py`. |
| Screen stays blank, no errors | SPI not enabled, or the Pi was not rebooted after enabling it. |
| Screen stays blank on a Pi 5 | `RPi.GPIO` does not work there: `sudo apt-get remove -y python3-rpi.gpio && sudo apt-get install -y python3-rpi-lgpio` |
| `ModuleNotFoundError: No module named 'lib'` | The repository was copied incompletely — `lib/waveshare_epd/` is missing. |
| **API Unreachable** on screen | Expected behaviour when the Tempest API cannot be read. The line underneath gives the reason and the time of the last attempt; it clears on the next successful refresh. |
| `-` in place of a reading | The station did not report that value. A genuine zero displays as `0`. |

If only the NWS is unreachable, the display still draws normally — the alert
banner is simply omitted.

# Parts

https://www.waveshare.com/7.5inch-e-paper-hat-b.htm

- OR
https://www.waveshare.com/wiki/7.5inch_e-Paper_HAT

- Raspberry Pi ZeroW+

- SD card for the Pi (at least 8 GB)

- Power supply for the Pi



# Licensing

- Code licensed under the MIT License

- Documentation licensed under CC BY 3.0
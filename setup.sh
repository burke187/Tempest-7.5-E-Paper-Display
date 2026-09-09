#!/usr/bin/env bash
#
# Setup for the Tempest 7.5" e-paper display.
#
# First, in a browser on your workstation, log in to tempestwx.com and collect:
#   TEMPEST_TOKEN  https://tempestwx.com/settings/tokens
#   STATION_ID     https://tempestwx.com/station/XXXXXX  (the number in the URL)
# Both are behind a login, so no script can fetch them for you.
#
# Then run this ON the Raspberry Pi, from the directory it lives in, after
# copying the repo over from your workstation:
#
#   scp -r Tempest-7.5-E-Paper-Display/ admin@your-raspberry-pi.local:/home/admin/
#   ssh admin@your-raspberry-pi.local
#   cd /home/admin/Tempest-7.5-E-Paper-Display && ./setup.sh
#
# It installs dependencies, enables SPI, writes .env, and installs the cron
# jobs. Wiring the HAT to the GPIO header is the one step you still do by hand:
# https://www.waveshare.com/wiki/7.5inch_e-Paper_HAT_(B)_Manual#Working_With_Raspberry_Pi

set -euo pipefail

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$INSTALL_DIR/.env"
CRON_MARKER='# Tempest e-paper display (managed by setup.sh)'
PYTHON=/usr/bin/python3

ASSUME_YES=false
INSTALL_CRON=true
INSTALL_REBOOT_CRON=true
SKIP_APT=false

APT_PACKAGES=(
    python3 python3-pip python3-pil python3-numpy
    python3-requests python3-tz python3-dotenv
    python3-spidev python3-rpi.gpio
)
# "import name:pip name", for anything apt did not manage to provide
PIP_FALLBACK=(
    "PIL:Pillow"
    "requests:requests"
    "pytz:pytz"
    "dotenv:python-dotenv"
    "spidev:spidev"
)

usage() {
    cat <<EOF
Usage: ./setup.sh [options]

  -y, --yes            Take defaults, never prompt (see env vars below)
      --no-cron        Skip installing any cron jobs
      --no-reboot-cron Install the 5-minute refresh job but not the 4 AM reboot
      --skip-apt       Skip apt-get, only verify the Python imports
  -h, --help           Show this help

Non-interactive runs read these from the environment, falling back to any
values already in .env:

  STATION_ID  COUNTY_CODE  TEMPEST_TOKEN  TIMEZONE

STATION_ID and TEMPEST_TOKEN are only obtainable from tempestwx.com while
logged in, so fetch those two in a browser before you start.

  STATION_ID=12345 COUNTY_CODE=OHC035 TEMPEST_TOKEN=abc TIMEZONE=US/Eastern \\
      ./setup.sh -y
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -y|--yes)          ASSUME_YES=true ;;
        --no-cron)         INSTALL_CRON=false ;;
        --no-reboot-cron)  INSTALL_REBOOT_CRON=false ;;
        --skip-apt)        SKIP_APT=true ;;
        -h|--help)         usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
info() { printf '    %s\n' "$1"; }
warn() { printf '    \033[33mWARNING:\033[0m %s\n' "$1" >&2; }
die()  { printf '\n\033[31mERROR:\033[0m %s\n' "$1" >&2; exit 1; }

# Prompt for a value, defaulting to whatever we already know.
# ask VARNAME "Label" "current value"
ask() {
    local var=$1 label=$2 current=${3:-} answer
    if [[ -n "$current" ]] && $ASSUME_YES; then
        printf -v "$var" '%s' "$current"
        return
    fi
    if $ASSUME_YES || [[ ! -t 0 ]]; then
        [[ -n "$current" ]] || die "$label is required: set it in the environment or in .env, or run without -y"
        printf -v "$var" '%s' "$current"
        return
    fi
    while :; do
        if [[ -n "$current" ]]; then
            read -rp "    $label [$current]: " answer
            answer=${answer:-$current}
        else
            read -rp "    $label: " answer
        fi
        [[ -n "$answer" ]] && break
        echo "    A value is required."
    done
    printf -v "$var" '%s' "$answer"
}

confirm() {
    local prompt=$1 reply
    $ASSUME_YES && return 0
    [[ -t 0 ]] || return 0
    read -rp "    $prompt [Y/n] " reply
    [[ -z "$reply" || "$reply" =~ ^[Yy] ]]
}

# Show enough of a secret to recognise it, not enough to leak it
mask() {
    local value=$1
    if (( ${#value} <= 4 )); then printf '****'; else printf '****%s' "${value: -4}"; fi
}

# As ask(), but nothing is echoed and any existing value shows up masked, so
# the token never lands in scrollback or a terminal log.
# ask_secret VARNAME "Label" "current value"
ask_secret() {
    local var=$1 label=$2 current=${3:-} answer
    if $ASSUME_YES || [[ ! -t 0 ]]; then
        [[ -n "$current" ]] || die "$label is required: set it in the environment or in .env, or run without -y"
        printf -v "$var" '%s' "$current"
        return
    fi
    while :; do
        if [[ -n "$current" ]]; then
            read -rsp "    $label [Enter to keep $(mask "$current")]: " answer
            echo
            answer=${answer:-$current}
        else
            read -rsp "    $label (paste it; input is hidden): " answer
            echo
        fi
        [[ -n "$answer" ]] && break
        echo "    A value is required."
    done
    printf -v "$var" '%s' "$answer"
}

###########################################################
# Preflight
###########################################################

step "Checking the environment"

[[ $EUID -ne 0 ]] || warn "Running as root. Prefer running as your normal user; sudo is used where needed."
command -v sudo >/dev/null || die "sudo not found. This script needs it for apt, SPI and the root crontab."

if ! grep -qi raspberry /proc/device-tree/model 2>/dev/null; then
    warn "This does not look like a Raspberry Pi. Hardware steps will probably fail."
    confirm "Continue anyway?" || exit 1
else
    info "Model: $(tr -d '\0' < /proc/device-tree/model)"
fi

missing_assets=()
for asset in weather.py lib/waveshare_epd pic pic/icon font; do
    [[ -e "$INSTALL_DIR/$asset" ]] || missing_assets+=("$asset")
done
if [[ ${#missing_assets[@]} -gt 0 ]]; then
    die "Missing from $INSTALL_DIR: ${missing_assets[*]}
    Copy the whole repository across, not just weather.py."
fi
info "Install directory: $INSTALL_DIR"

###########################################################
# Values only you can fetch
###########################################################

# Seeded here rather than down in the config step so the browser-only
# prerequisites are raised before spending several minutes inside apt.
station=${STATION_ID:-}
county=${COUNTY_CODE:-}
token=${TEMPEST_TOKEN:-}
zone=${TIMEZONE:-}

if [[ -f "$ENV_FILE" ]]; then
    # The || guard picks up a final line with no trailing newline
    while IFS='=' read -r key value || [[ -n "$key" ]]; do
        value=${value%$'\r'}
        case "$key" in
            STATION_ID)    station=${station:-$value} ;;
            COUNTY_CODE)   county=${county:-$value} ;;
            TEMPEST_TOKEN) token=${token:-$value} ;;
            TIMEZONE)      zone=${zone:-$value} ;;
        esac
    done < "$ENV_FILE"
fi

if [[ -z "$token" || -z "$station" ]]; then
    step "Two values you have to fetch yourself"
    cat <<'EOF'
    Both of these live behind a login at tempestwx.com, so this script cannot
    retrieve them for you. Get them in a browser on your workstation, not on
    the Pi -- if you are here over SSH there is no browser on this machine:

      TEMPEST_TOKEN   https://tempestwx.com/settings/tokens
                      Log in, create a token, copy it. Treat it as a password.

      STATION_ID      https://tempestwx.com/station/XXXXXX
                      Log in; it is the number in the URL.

    Then paste them in below, or pass them in the environment to skip the
    prompts entirely:

      TEMPEST_TOKEN=... STATION_ID=... ./setup.sh
EOF
    echo
    if ! confirm "Do you have both to hand?"; then
        info "No problem: collect them, then run ./setup.sh again."
        info "Nothing has been changed on this system yet."
        exit 0
    fi
fi

###########################################################
# Dependencies and SPI
###########################################################

if $SKIP_APT; then
    step "Skipping apt (--skip-apt)"
else
    step "Installing system packages"
    sudo apt-get update -qq
    # Installed one at a time: package names drift between Pi OS releases and
    # one rename should not abort the whole run. Imports are verified below.
    for package in "${APT_PACKAGES[@]}"; do
        if sudo apt-get install -y -qq "$package" >/dev/null 2>&1; then
            info "ok       $package"
        else
            warn "could not install $package (trying pip later if needed)"
        fi
    done
fi

step "Verifying Python modules"
for entry in "${PIP_FALLBACK[@]}"; do
    import_name=${entry%%:*}
    pip_name=${entry##*:}
    if "$PYTHON" -c "import $import_name" >/dev/null 2>&1; then
        info "ok       $import_name"
        continue
    fi
    info "missing  $import_name, installing $pip_name with pip"
    # Pi OS Bookworm marks the system Python as externally managed (PEP 668),
    # so pip refuses to touch it without this flag.
    sudo "$PYTHON" -m pip install --quiet --break-system-packages "$pip_name" \
        || sudo "$PYTHON" -m pip install --quiet "$pip_name" \
        || warn "pip could not install $pip_name; weather.py will fail until it is present"
done

if [[ "$(tr -d '\0' < /proc/device-tree/model 2>/dev/null)" == *"Pi 5"* ]]; then
    warn "On the Pi 5, RPi.GPIO does not work. If the display stays blank, run:
        sudo apt-get remove -y python3-rpi.gpio && sudo apt-get install -y python3-rpi-lgpio"
fi

step "Enabling SPI"
if command -v raspi-config >/dev/null; then
    if sudo raspi-config nonint get_spi 2>/dev/null | grep -q '^0$'; then
        info "already enabled"
    else
        sudo raspi-config nonint do_spi 0
        info "enabled (a reboot is needed before the display will work)"
        NEEDS_REBOOT=true
    fi
else
    warn "raspi-config not found; enable SPI yourself with 'dtparam=spi=on' in /boot/firmware/config.txt"
fi

###########################################################
# Configuration
###########################################################

step "Configuring $ENV_FILE"

# station/county/token/zone were already seeded from the environment and any
# existing .env, up in the prerequisites section
[[ -f "$ENV_FILE" ]] && info ".env already exists; its values are offered as defaults"

echo
info "STATION_ID is in the URL when you log in: https://tempestwx.com/station/XXXXXX"
ask station "STATION_ID" "$station"

info "TEMPEST_TOKEN is the one you copied from https://tempestwx.com/settings/tokens"
ask_secret token "TEMPEST_TOKEN" "$token"

info "TIMEZONE is a pytz name, e.g. US/Eastern (https://mljar.com/blog/list-pytz-timezones/)"
ask zone "TIMEZONE" "${zone:-US/Eastern}"
if ! "$PYTHON" -c "import pytz,sys; pytz.timezone(sys.argv[1])" "$zone" >/dev/null 2>&1; then
    warn "'$zone' is not a timezone pytz recognises; weather.py will fail to start"
fi

# COUNTY_CODE is the NWS zone the alert feed is queried with. The NWS can look
# it up from coordinates, which saves walking the weather.gov UI by hand.
if [[ -z "$county" ]] && ! $ASSUME_YES && [[ -t 0 ]]; then
    info "COUNTY_CODE is your NWS zone, e.g. OHC035."
    if confirm "Look it up from latitude/longitude?"; then
        read -rp "    Latitude (e.g. 39.9612): " lat
        read -rp "    Longitude (e.g. -82.9988): " lon
        county=$("$PYTHON" - "$lat" "$lon" <<'PY' || true
import json, sys, urllib.request
lat, lon = sys.argv[1].strip(), sys.argv[2].strip()
url = f'https://api.weather.gov/points/{lat},{lon}'
try:
    request = urllib.request.Request(url, headers={'User-Agent': 'tempest-epaper-setup'})
    with urllib.request.urlopen(request, timeout=15) as response:
        county = json.load(response)['properties']['county']
    print(county.rstrip('/').rsplit('/', 1)[-1])
except Exception as exc:
    print(f'lookup failed: {exc}', file=sys.stderr)
PY
)
        [[ -n "$county" ]] && info "found $county" || warn "lookup failed, enter the code by hand"
    fi
    if [[ -z "$county" ]]; then
        info "Or: weather.gov -> your ZIP -> 'Get detailed info', then open"
        info "https://api.weather.gov/points/LAT,LON and read the 'county' field"
    fi
fi
ask county "COUNTY_CODE" "$county"

umask 077
cat > "$ENV_FILE" <<EOF
STATION_ID=$station
COUNTY_CODE=$county
TEMPEST_TOKEN=$token
TIMEZONE=$zone
EOF
chmod 600 "$ENV_FILE"
info "written, mode 600 (it holds your API token)"

step "Testing the Tempest API with those credentials"
# Passed through the environment, not argv: /proc/PID/cmdline is readable by
# any local user, /proc/PID/environ is not
if STATION_ID="$station" TEMPEST_TOKEN="$token" "$PYTHON" - <<'PY'
import json, os, sys, urllib.request
station, token = os.environ['STATION_ID'], os.environ['TEMPEST_TOKEN']
url = ('https://swd.weatherflow.com/swd/rest/better_forecast'
       f'?station_id={station}&units_temp=f&token={token}')
try:
    with urllib.request.urlopen(url, timeout=20) as response:
        data = json.load(response)
except Exception as exc:
    sys.exit(f'    request failed: {exc}')
if 'current_conditions' not in data:
    sys.exit(f"    no current_conditions in the reply: {str(data)[:200]}")
temp = data['current_conditions'].get('air_temperature')
print(f"    station reports {temp}F right now")
PY
then
    info "credentials look good"
else
    warn "could not read your station. Check STATION_ID and TEMPEST_TOKEN in $ENV_FILE."
fi

###########################################################
# Cron
###########################################################

if ! $INSTALL_CRON; then
    step "Skipping cron (--no-cron)"
else
    step "Installing cron jobs in the root crontab"
    refresh_job="*/5 * * * * $PYTHON $INSTALL_DIR/weather.py > /dev/null 2>&1"
    reboot_job='0 4 * * * /sbin/reboot'

    # Drop any previous block of ours plus older hand-written weather.py lines,
    # so re-running this script does not stack up duplicate jobs.
    current=$(sudo crontab -l 2>/dev/null || true)
    filtered=$(printf '%s\n' "$current" \
        | grep -vF "$CRON_MARKER" \
        | grep -v 'weather\.py' \
        | grep -v '^0 4 \* \* \* .*reboot' \
        || true)

    {
        printf '%s\n' "$filtered" | sed '/^$/d'
        printf '%s\n' "$CRON_MARKER"
        printf '%s\n' "$refresh_job"
        $INSTALL_REBOOT_CRON && printf '%s\n' "$reboot_job"
    } | sudo crontab -

    info "$refresh_job"
    $INSTALL_REBOOT_CRON && info "$reboot_job"
    info "output goes to /dev/null; to debug, point it at a file instead"
fi

###########################################################
# Done
###########################################################

step "Setup complete"
info "Still to do by hand:"
info "  - wire the HAT per the WaveShare wiki (link at the top of this script)"
info "  - the code targets the 3-colour panel; see the comments in weather.py"
info "    to switch to 2-colour"

interactive() { ! $ASSUME_YES && [[ -t 0 ]]; }

if [[ -n "${NEEDS_REBOOT:-}" ]]; then
    echo
    warn "SPI was just turned on, so the Pi needs a reboot before the panel responds."
    # Never reboot unattended, no matter what -y implies
    if interactive && confirm "Reboot now?"; then
        sudo reboot
    else
        info "Reboot when you are ready:  sudo reboot"
    fi
elif interactive && confirm "Draw a frame now to test the display?"; then
    sudo "$PYTHON" "$INSTALL_DIR/weather.py"
fi

exit 0

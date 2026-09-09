#!/usr/bin/env python3
"""E-paper weather display driven by a Tempest (WeatherFlow) station.

Heavily modified version of e_paper_weather_display: all observations come from
the TempestWX API, severe-weather headlines from the NWS.

One invocation draws a single frame and exits, so refresh scheduling belongs to
cron / systemd rather than this script.
"""

import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Any, Optional

import pytz
import requests
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = os.path.dirname(os.path.realpath(__file__))
PIC_DIR = os.path.join(BASE_DIR, 'pic')
ICON_DIR = os.path.join(PIC_DIR, 'icon')
FONT_FILE = os.path.join(BASE_DIR, 'font', 'Font.ttc')

# Search lib folder for display driver modules
sys.path.append('/home/admin/Tempest-7.5-E-Paper-Display-master/lib')

# Pick the correct 7.5" Waveshare screen - current build is for the 3 color
from lib.waveshare_epd import epd7in5_V2  # noqa: E402  (needs sys.path above)

BLACK = 'rgb(0,0,0)'
WHITE = 'rgb(255,255,255)'

MISSING = '-'            # displayed in place of any reading the API omits
TRACE_RAIN = 1000        # sentinel: it rained, but accumulation rounded to zero
HTTP_TIMEOUT = 30

# Error screen: keep RETRY_NOTICE honest if the cron interval changes
RETRY_NOTICE = 'Retrying in 5 min'
ERROR_ICON_TOP = 120

# Icons that look the same day or night; everything else has -day/-night pairs
TIME_AGNOSTIC_ICONS = ('cloudy', 'foggy', 'windy2', 'thundersnow')
TIME_AGNOSTIC_PREFIXES = ('possibly', 'clear', 'partly')
# Precipitation icons win over the wind override
WIND_OVERRIDE_EXCLUDED = ('thunderstorm', 'snow', 'sleet', 'rainy')
GUST_ICON_THRESHOLD = 10  # mph

# Explicit path: cron runs from a different working directory, so relying on
# dotenv's search would be a coin flip
load_dotenv(os.path.join(BASE_DIR, '.env'))


def require_env(name):
    """Fail loudly at startup rather than deep inside a request."""
    value = os.getenv(name)
    if not value:
        sys.exit(f'Missing required environment variable: {name}')
    return value


LOCAL_TZ = pytz.timezone(require_env('TIMEZONE'))
SUN_TZ = pytz.timezone('US/Eastern')  # zone the sunrise/sunset times print in

TEMPEST_URL = (
    'https://swd.weatherflow.com/swd/rest/better_forecast'
    f"?station_id={require_env('STATION_ID')}"
    '&units_temp=f&units_wind=mph&units_pressure=inhg'
    '&units_precip=in&units_distance=mi'
    f"&token={require_env('TEMPEST_TOKEN')}"
)
NWS_URL = f"https://api.weather.gov/alerts/active?zone={require_env('COUNTY_CODE')}"


@lru_cache(maxsize=None)
def font(size):
    """The display face at `size`, loaded once per size."""
    return ImageFont.truetype(FONT_FILE, size)


def text_width(draw, text, face):
    """Rendered width of `text`; replaces the removed ImageDraw.textsize()."""
    return draw.textbbox((0, 0), text, font=face)[2]


###########################################################
# Panel I/O
###########################################################

def write_to_screen(epd, image_path):
    """Push a saved PNG to the panel, then put the panel back to sleep."""
    print('Writing to screen.')
    frame = Image.new('1', (epd.width, epd.height), 255)
    frame.paste(Image.open(image_path), (0, 0))
    epd.init()
    epd.display(epd.getbuffer(frame))
    time.sleep(2)
    epd.sleep()


def display_error(epd, detail, attempted_at):
    """Fill the screen with an unreachable-API warning, then end the run.

    `detail` says which call failed and how; `attempted_at` is when the run
    started, so a frame left up by a long outage is obvious at a glance.
    """
    print(f'API unreachable: {detail}')
    image = Image.new('1', (epd.width, epd.height), 255)
    draw = ImageDraw.Draw(image)
    middle = epd.width // 2

    icon = Image.open(os.path.join(ICON_DIR, 'warning.png'))
    image.paste(icon, (middle - icon.width // 2, ERROR_ICON_TOP))

    draw.text((middle, 205), 'API Unreachable', font=font(60),
              fill=BLACK, anchor='mm')
    draw.text((middle, 265), detail, font=font(25), fill=BLACK, anchor='mm')
    draw.text((middle, 335), f"Last attempt: {attempted_at.strftime('%H:%M')}",
              font=font(35), fill=BLACK, anchor='mm')
    draw.text((middle, 395), RETRY_NOTICE, font=font(22), fill=BLACK, anchor='mm')

    path = os.path.join(PIC_DIR, 'error.png')
    image.save(path)
    image.close()
    write_to_screen(epd, path)
    sys.exit(0)


###########################################################
# Data
###########################################################

@dataclass
class Weather:
    """One frame's worth of readings, already in display units.

    Any value the API leaves out is MISSING, and every formatter renders that
    as '-' rather than guessing a number. Sunrise/sunset are None when the
    daily forecast is unavailable.
    """

    temp_current: Any
    feels_like: Any
    humidity: Any
    dew_point: Any
    wind: Any
    wind_cardinal: str
    uv_index: Any
    report: str
    icon_code: str
    temp_max: Any
    temp_min: Any
    sunrise: Optional[datetime]
    sunset: Optional[datetime]
    precip_percent: Any
    total_rain: float
    rain_time: int


class WeatherUnavailable(Exception):
    """The Tempest API could not be read; the message is shown on screen."""


def fetch_conditions():
    """Tempest forecast payload, or raise WeatherUnavailable."""
    print('Attempting to connect to Tempest WX.')
    try:
        response = requests.get(TEMPEST_URL, timeout=HTTP_TIMEOUT)
    except requests.Timeout as exc:
        raise WeatherUnavailable(
            f'Tempest WX timed out after {HTTP_TIMEOUT}s') from exc
    except requests.RequestException as exc:
        raise WeatherUnavailable('Could not reach Tempest WX') from exc

    if response.status_code != 200:
        raise WeatherUnavailable(
            f'Tempest WX returned HTTP {response.status_code}')

    try:
        payload = response.json()
    except ValueError as exc:
        raise WeatherUnavailable('Tempest WX sent an unreadable reply') from exc

    print('JSON pull from Tempest WX successful.')
    return payload


def fetch_alert_event():
    """Headline of the first active NWS alert for the zone, if there is one.

    Alerts are a bonus rather than a requirement: if the NWS is down the rest
    of the frame is still worth drawing, so failures are logged and skipped.
    """
    try:
        response = requests.get(NWS_URL, timeout=HTTP_TIMEOUT)
        features = response.json().get('features') or []
    except (requests.RequestException, ValueError) as exc:
        print(f'Skipping NWS alerts, could not reach the NWS: {exc}')
        return None

    if not features:
        print('No Severe Weather')
        return None
    return features[0].get('properties', {}).get('event')


def storm_icon(current):
    """Icon name, overridden to windy when it is gusty but not precipitating."""
    icon_code = reading(current, 'icon')
    gust = current.get('wind_gust') or 0
    if (not is_missing(icon_code)
            and gust >= GUST_ICON_THRESHOLD
            and icon_code not in WIND_OVERRIDE_EXCLUDED
            and not icon_code.startswith('clear')):
        return 'windy2'
    return icon_code


def reading(block, key):
    """A value from the API, or MISSING when it is absent or null."""
    value = block.get(key)
    return MISSING if value is None else value


def parse_weather(wxdata):
    current = wxdata['current_conditions']

    report = reading(current, 'conditions')
    if report == 'Thunderstorms Possible':
        report = 'T-Storms Possible'

    daily = wxdata['forecast']['daily'][0] if wxdata['forecast']['daily'] else {}
    sunrise_epoch = daily.get('sunrise')
    sunset_epoch = daily.get('sunset')

    total_rain = current.get('precip_accum_local_day') or 0
    rain_time = current.get('precip_minutes_local_day') or 0
    if rain_time > 0 and total_rain <= 0:
        total_rain = TRACE_RAIN

    return Weather(
        temp_current=reading(current, 'air_temperature'),
        feels_like=reading(current, 'feels_like'),
        humidity=reading(current, 'relative_humidity'),
        dew_point=reading(current, 'dew_point'),
        wind=reading(current, 'wind_avg'),
        wind_cardinal=reading(current, 'wind_direction_cardinal'),
        uv_index=reading(current, 'uv'),
        report=report,
        icon_code=storm_icon(current),
        temp_max=reading(daily, 'air_temp_high'),
        temp_min=reading(daily, 'air_temp_low'),
        sunrise=datetime.fromtimestamp(sunrise_epoch) if sunrise_epoch else None,
        sunset=datetime.fromtimestamp(sunset_epoch) if sunset_epoch else None,
        precip_percent=reading(daily, 'precip_probability'),
        total_rain=total_rain,
        rain_time=rain_time,
    )


###########################################################
# Formatting
###########################################################

def is_missing(value):
    """True for anything the API did not report, including NaN."""
    return value == MISSING or value is None or value != value


def fmt_number(value, decimals=0):
    """'-' for a missing reading, otherwise the value rounded for display."""
    return MISSING if is_missing(value) else f'{value:.{decimals}f}'


def fmt_temp(value):
    return f'{fmt_number(value)}\N{DEGREE SIGN}F'


def fmt_wind(speed, cardinal):
    return f'Wind: {fmt_number(speed, 1)} MPH {cardinal}'


def fmt_clock(moment):
    return MISSING if moment is None else moment.astimezone(SUN_TZ).strftime('%H:%M')


def fmt_rain(total_rain, rain_time):
    amount = 'Trace' if total_rain >= TRACE_RAIN else f'{total_rain:.2f} in'
    return f'Total: {amount} | Duration: {rain_time} min'


def fmt_date(moment):
    return moment.strftime('%a %B %d, %Y')


###########################################################
# Rendering
###########################################################

def icon_filename(icon_code, now, sunrise, sunset):
    if (icon_code.startswith(TIME_AGNOSTIC_PREFIXES)
            or icon_code in TIME_AGNOSTIC_ICONS):
        return f'{icon_code}.png'
    # Without sun times we cannot tell day from night, so assume night
    if sunrise and sunset and sunrise <= now < sunset:
        return f'{icon_code}-day.png'
    return f'{icon_code}-night.png'


def precip_icon(temp_current):
    """Snow below freezing, wintry mix just above it, rain otherwise."""
    if is_missing(temp_current):
        return 'precip.png'
    if temp_current <= 32:
        return 'snow.png'
    if temp_current <= 39:
        return 'mix.png'
    return 'precip.png'


def paste_icon(template, name, position):
    template.paste(Image.open(os.path.join(ICON_DIR, name)), position)


def draw_current_panel(template, draw, wx):
    """Top left: conditions icon, headline, UV index and precip chance."""
    if not is_missing(wx.icon_code):
        paste_icon(template, icon_filename(wx.icon_code, datetime.now(),
                                           wx.sunrise, wx.sunset), (40, 15))

    report = wx.report.title()
    if report == 'Wintry Mix Possible':
        # Too long for one line at font 22, so the label drops to a second line
        draw.text((15, 183), 'Now:', font=font(22), fill=BLACK)
        draw.text((70, 185), report, font=font(20), fill=BLACK)
    else:
        draw.text((15, 183), f'Now: {report}', font=font(22), fill=BLACK)

    # The barometer metric (sea_level_pressure plus a rising/steady/falling
    # arrow) used to occupy this slot - see weather.py.orig to swap it back in.
    paste_icon(template, 'uv.png', (15, 213))
    draw.text((65, 223), f'UV Index: {wx.uv_index}', font=font(22), fill=BLACK)

    paste_icon(template, precip_icon(wx.temp_current), (15, 255))
    draw.text((65, 263), f'Precip: {fmt_number(wx.precip_percent)}%',
              font=font(22), fill=BLACK)


def draw_feels_like(template, draw, wx):
    """Feels-like line, centred, flagged with a finger icon when it diverges."""
    text = f'Feels like: {fmt_temp(wx.feels_like)}'
    if is_missing(wx.feels_like) or is_missing(wx.temp_current):
        icon = None  # nothing to compare, so no hot/cold flag
    else:
        difference = int(wx.feels_like) - int(wx.temp_current)
        if difference >= 5:
            icon = 'finghot.png'
        elif difference <= -5:
            icon = 'fingcold.png'
        else:
            icon = None

    panel = Image.new('RGB', (520, 65), WHITE)
    panel_draw = ImageDraw.Draw(panel)
    # Shift left to leave room for the icon
    x = panel.width // 2 - (35 if icon else 0)
    panel_draw.text((x, panel.height // 2), text,
                    fill=BLACK, font=font(50), anchor='mm')
    if icon:
        width = text_width(draw, text, font(50))
        paste_icon(panel, icon, ((265 + width) // 2 + 100, 3))
    template.paste(panel, (265, 195))


def draw_temperature_panel(template, draw, wx):
    """Top right: date, the big current temperature, and feels-like."""
    draw.text((425, 30), fmt_date(datetime.now(LOCAL_TZ)),
              font=font(22), fill=BLACK)
    draw.text((365, 35), fmt_temp(wx.temp_current), font=font(160), fill=BLACK)
    draw_feels_like(template, draw, wx)


def draw_forecast_panel(template, draw, wx):
    """Bottom left: today's high and low, '-' when the forecast is unavailable."""
    draw.text((35, 330), f'High: {fmt_temp(wx.temp_max)}',
              font=font(50), fill=BLACK)
    draw.line((170, 390, 265, 390), fill=BLACK, width=4)
    draw.text((35, 395), f'Low:  {fmt_temp(wx.temp_min)}',
              font=font(50), fill=BLACK)


def draw_comfort_panel(template, draw, wx):
    """Bottom middle: humidity, dew point, wind."""
    rows = (
        ('rh.png', 320, f'Humidity: {fmt_number(wx.humidity)}%'),
        ('dp.png', 373, f'Dew Point: {fmt_temp(wx.dew_point)}'),
        ('wind.png', 425, fmt_wind(wx.wind, wx.wind_cardinal)),
    )
    for icon, y, text in rows:
        paste_icon(template, icon, (320, y))
        draw.text((370, y + 10), text, font=font(23), fill=BLACK)


def draw_sun_panel(template, draw, wx):
    """Bottom right: sunrise, sunset, and this refresh's timestamp."""
    rows = (
        ('sunrise.png', 320, f'Sunrise: {fmt_clock(wx.sunrise)}'),
        ('sunset.png', 370, f'Sunset: {fmt_clock(wx.sunset)}'),
        (None, 420, f"Updated: {datetime.now(LOCAL_TZ).strftime('%H:%M')}"),
    )
    for icon, y, text in rows:
        if icon:
            paste_icon(template, icon, (550, y))
        draw.text((615, y + 10), text, font=font(25), fill=BLACK)


def draw_banner(template, draw, text, icon):
    """Top centre strip, shared by the rain total and the forecast warning."""
    panel = Image.new('RGB', (520, 50), WHITE)
    panel_draw = ImageDraw.Draw(panel)
    # y is 22 rather than the panel's own centre: that is where the original
    # layout put this text, and the strip has been tuned around it.
    panel_draw.text((panel.width // 2 + 25, 22), text,
                    fill=BLACK, font=font(23), anchor='mm')
    width = text_width(draw, text, font(23))
    paste_icon(panel, icon, (width // 2 - 110, 0))
    template.paste(panel, (265, 15))


def draw_alert(template, draw, event):
    """Severe-weather headline, centred near the bottom of the screen."""
    panel = Image.new('RGB', (380, 40), WHITE)
    panel_draw = ImageDraw.Draw(panel)
    panel_draw.text((panel.width // 2 + 25, panel.height // 2), event,
                    fill=BLACK, font=font(23), anchor='mm')
    width = text_width(draw, event, font(23))
    paste_icon(panel, 'warning.png', ((380 - width) // 2 - 25, 0))
    template.paste(panel, (330, 255))


def render_frame(wx, event):
    """Compose the frame onto the template and return the saved PNG's path."""
    template = Image.open(os.path.join(PIC_DIR, 'template.png'))
    draw = ImageDraw.Draw(template)

    draw_current_panel(template, draw, wx)
    draw_temperature_panel(template, draw, wx)
    draw_forecast_panel(template, draw, wx)
    draw_comfort_panel(template, draw, wx)
    draw_sun_panel(template, draw, wx)

    # Both banners share one slot; rain wins when there is rain to report
    if is_missing(wx.temp_max):
        draw_banner(template, draw, 'Unable to pull forecast data!', 'warning.png')
    if wx.total_rain > 0:
        draw_banner(template, draw, fmt_rain(wx.total_rain, wx.rain_time),
                    'totalrain.png')
    if event:
        draw_alert(template, draw, event)

    path = os.path.join(PIC_DIR, 'screen_output.png')
    template.save(path)
    template.close()
    return path


def main():
    epd = epd7in5_V2.EPD()
    print('Initializing and clearing screen.')
    epd.init()
    epd.Clear()

    attempted_at = datetime.now(LOCAL_TZ)
    try:
        wx = parse_weather(fetch_conditions())
    except WeatherUnavailable as exc:
        display_error(epd, str(exc), attempted_at)
    except (KeyError, TypeError, ValueError) as exc:
        # HTTP 200 carrying an unexpected shape is still a failed pull
        print(f'Unexpected Tempest payload: {exc!r}')
        display_error(epd, 'Tempest WX sent unexpected data', attempted_at)

    write_to_screen(epd, render_frame(wx, fetch_alert_event()))


if __name__ == '__main__':
    main()

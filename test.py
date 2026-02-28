#-----------------------------------------------------------
# minimal variant of weather.py to test screen compatibility
# this just puts the template on the screen
#
# note: for the 2-color display this needs to use the older
#       v4.0 version of the waveshare libs but the 3-color
#       still uses the original upstream (later) library
#
# also: I renamed the hot/cold icons to be less iffy :-)
#-----------------------------------------------------------

# alphabetical order here so we can keep track
import csv
from   datetime import datetime
from   io import BytesIO
import json
import os
from   pathlib import Path
from   PIL import Image,ImageDraw,ImageFont
import requests
import sys
import time
import traceback
import urllib.request

#---------------------------------------------------------------

def write_to_screen(image, sleep_seconds):
    print('Writing to screen.')
    h_image = Image.new('1', (epd.width, epd.height), 255)
    screen_output_file = Image.open(os.path.join(picdir, image))
    h_image.paste(screen_output_file, (0, 0))
    epd.init()
    if config['twocolor_display']:
        epd.display(epd.getbuffer(h_image))
    else:
        h_red_image = Image.new('1', (epd.width, epd.height), 255)
        draw_red = ImageDraw.Draw(h_red_image)
        epd.display(epd.getbuffer(h_image), epd.getbuffer(h_red_image))
    time.sleep(2)
    epd.sleep()

    # TODO: should this be in the main program ?
    print('Sleeping for ' + str(sleep_seconds) +'.')
    time.sleep(sleep_seconds)

#---------------------------------------------------------------
# main() here
#---------------------------------------------------------------

picdir  = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'pic')
icondir = os.path.join(picdir, 'icon')
fontdir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'font')

# write scratch files herre
tmpdir  = "/tmp"

# search lib folder for display driver modules
sys.path.append('lib')

# initialize some hashes used below
conditions={}
config = {}

# we'd also read the config file here.....

###########################################################
# temporary items in lieu of reading the config file
###########################################################

config['twocolor_display'] = True

###########################################################
# test data in lieu of getting actual data at this time
###########################################################
conditions['baro']         = 30.23            # inHg
conditions['dewpt']        = 54               # degF
conditions['distance']     = "12 mi"          # NNN mi
conditions['event']        = "Storm Warning"  # or None
conditions['feels_like']   = 55               # degF
conditions['humidity']     = 98               # pct
conditions['precip_pct']   = 78               # pct
conditions['rain_time']    = 34               # min
conditions['strikes']      = 0                # (count) or None
conditions['temp_current'] = 68.3             # degF
conditions['temp_max']     = 72               # degF
conditions['temp_min']     = 54               # degF
conditions['total_rain']   = 2.2              # in
conditions['updated']      = "12:34"          # HH:MM
conditions['wind']         = 12.3             # mph
conditions['windcardinal'] = "NNW"            # direction
conditions['icon_code']    = "cloudy"         # see the icons dir for a list
conditions['description']  = "Rain Possible"  # TODO: placeholder here

###########################################################

# use the correct module for the specified type of display
if config['twocolor_display']:
    from waveshare_epd import epd7in5_V2
    epd = epd7in5_V2.EPD()
else:
    from waveshare_epd import epd7in5b_V2
    epd = epd7in5b_V2.EPD()

# Set the fonts
font22 = ImageFont.truetype(os.path.join(fontdir, 'Font.ttc'), 22)
font20 = ImageFont.truetype(os.path.join(fontdir, 'Font.ttc'), 20)
font22 = ImageFont.truetype(os.path.join(fontdir, 'Font.ttc'), 22)
font23 = ImageFont.truetype(os.path.join(fontdir, 'Font.ttc'), 23)
font25 = ImageFont.truetype(os.path.join(fontdir, 'Font.ttc'), 25)
font30 = ImageFont.truetype(os.path.join(fontdir, 'Font.ttc'), 30)
font35 = ImageFont.truetype(os.path.join(fontdir, 'Font.ttc'), 35)
font50 = ImageFont.truetype(os.path.join(fontdir, 'Font.ttc'), 50)
font60 = ImageFont.truetype(os.path.join(fontdir, 'Font.ttc'), 60)
font100 = ImageFont.truetype(os.path.join(fontdir, 'Font.ttc'), 100)
font160 = ImageFont.truetype(os.path.join(fontdir, 'Font.ttc'), 160)

# Set the colors
black = 'rgb(0,0,0)'
white = 'rgb(255,255,255)'
grey = 'rgb(235,235,235)'

#Comment/Remove if using a 2 color screen
#TODO - this doesn't seem to matter based on testing
red  = 'rgb(255,0,0)'

#---------------------------------------------------------------

# Initialize and clear screen
print('Initializing and clearing screen.')
epd.init()
epd.Clear()

#---------------------------------------------------------------

# This is wrapped in a try/except block so we can catch
# keyboard interrupts and cleanly init/clear/sleep the
# display to try to prevent burn-in.  It is not perfect
# but catches most of the ^C interrupts gracefully enough

try:
    while True:

        template = Image.open(os.path.join(picdir, 'template.png'))
        draw = ImageDraw.Draw(template)

        # generate some strings with units and/or rounding as applicable
        # TOODO: what if units are metric ?

        string_temp_max = 'High: ' + format(conditions['temp_max'], '.0f') +  u'\N{DEGREE SIGN}F'
        string_temp_min = 'Low:  ' + format(conditions['temp_min'], '.0f') +  u'\N{DEGREE SIGN}F'
        string_baro = str(conditions['baro']) +  ' in Hg'
        string_precip_percent = 'Precip: ' + str(format(conditions['precip_pct'], '.0f'))  + '%'
        string_feels_like = 'Feels like: ' + format(conditions['feels_like'], '.0f') +  u'\N{DEGREE SIGN}F'
        string_temp_current = format(conditions['temp_current'], '.0f') + u'\N{DEGREE SIGN}F'
        string_humidity = 'Humidity: ' + str(conditions['humidity']) + '%'
        string_dewpt = 'Dew Point: ' + format(conditions['dewpt'], '.0f') +  u'\N{DEGREE SIGN}F'
        string_wind = 'Wind: ' + format(conditions['wind'], '.1f') + ' MPH ' + conditions['windcardinal']
        string_description = 'Now: ' + conditions['description']  #TODO: placeholder here

        # TODO: refactor this mess.....
        if conditions['strikes'] is not None:
            if int(conditions['strikes']) > 0:
                string_strikes = str(conditions['strikes'])
                string_distance = conditions['distance']

        if conditions['event']:
            string_event = conditions['event']
        else:
            string_event = ""

        if conditions['total_rain'] < 1000:
            string_total_rain = 'Total: ' + str(format(conditions['total_rain'], '.2f')) + ' in | Duration: ' + str(conditions['rain_time']) + ' min'
        else:
            string_total_rain = 'Total: Trace | Duration: ' + str(conditions['rain_time']) + ' min'
            string_rain_time = str(conditions['rain_time']) + 'min'

        #------------------------------------------------------------------------
        #---------------- overlay data onto the image ---------------------------
        #----------------           start             ---------------------------
        #------------------------------------------------------------------------

        #--------  top left box ------- 

        #TODO: need nowcheck and sunrise/sunset code here for elif and else flow here
        icon_code = conditions['icon_code']
        if icon_code.startswith('possibly') or icon_code  == 'cloudy' or icon_code == 'foggy' or icon_code == 'windy' or icon_code.startswith('clear') or icon_code.startswith('partly'):
            icon_file = icon_code + '.png'
        elif nowcheck >= sunrise and nowcheck < sunset:
            icon_file = icon_code + '-day.png'
        else:
            icon_file = icon_code + '-night.png'
        icon_image = Image.open(os.path.join(icondir, icon_file))
        template.paste(icon_image, (40, 15))
        draw.text((15, 183), string_description, font=font22, fill=black)

        draw.text((65, 223),  string_baro                     , font=font22,  fill=black)  # baro
        draw.text((65, 263),  string_precip_percent           , font=font22,  fill=black)  # precip_pct

        #--------  bottom left box ------- 
        draw.text((35, 330),  string_temp_max                 , font=font50,  fill=black)  # temp_max
        draw.text((35, 395),  string_temp_min                 , font=font50,  fill=black)  # temp_min

        #--------  top right box ------- 
        draw.text((380, 22),  string_total_rain               , font=font23,  fill=black)  # total_rain
        draw.text((365, 35),  string_temp_current             , font=font160, fill=black)  # temp_current
        draw.text((360, 195), string_feels_like               , font=font50,  fill=black)  # feels_like

        # possible weather event text
        try:
             if conditions['event'] != None:
                alert_image = Image.open(os.path.join(icondir, "warning.png"))
                template.paste(alert_image, (335, 255))
                draw.text((385, 263), str(conditions['event']) , font=font23, fill=black)
        except NameError:
            print('No Severe Weather')

        # feels_like icon if it is hot or cold
        difference = int(conditions['feels_like']) - int(conditions['temp_current'])
        if difference >= 5:
            feels_file = 'wind.png'
            feels_image = Image.open(os.path.join(icondir, feels_file))
            template.paste(feels_image, (720, 196))
        if difference <= -5:
            feels_file = 'wind.png'
            feels_image = Image.open(os.path.join(icondir, feels_file))
            template.paste(feels_image, (720, 196))

        #--------  bottom middle box ------- 
        draw.text((370, 330), string_humidity                 , font=font23,  fill=black)  # humidity
        draw.text((370, 383), string_dewpt                    , font=font23,  fill=black)  # dewpt
        draw.text((370, 435), string_wind                     , font=font23,  fill=black)  # wind
        draw.text((385, 263), ""                              , font=font23,  fill=black)  # event

        rh_file = 'rh.png'
        rh_image = Image.open(os.path.join(icondir, rh_file))
        template.paste(rh_image, (320, 320))

        dp_file = 'dp.png'
        dp_image = Image.open(os.path.join(icondir, dp_file))
        template.paste(dp_image, (320, 373))

        wind_file = 'wind.png'
        wind_image = Image.open(os.path.join(icondir, wind_file))
        template.paste(wind_image, (320, 425))

        # total_rain only if we have rain
        if conditions['total_rain'] > 0 or conditions['total_rain'] == 1000:
            train_image = Image.open(os.path.join(icondir, "totalrain.png"))
            template.paste(train_image, (330, 15))
            draw.text((380, 22), string_total_rain, font=font23, fill=black)

        #--------  bottom right box ------- 

        # lightning info or by default the HH:MM last updated
        if conditions['strikes'] is not None and int(conditions['strikes']) > 0:
            draw.text((695, 330), 'Strikes', font=font22, fill=white)
            draw.text((685, 400), 'Distance', font=font22, fill=white)
            draw.text((683, 430), string_distance, font=font20, fill=white)  # distance
            draw.text((703, 360), string_strikes, font=font20, fill=white)  # strikes
            strike_image = Image.open(os.path.join(icondir, "strike.png"))
            template.paste(strike_image, (605, 305))
        else:
            draw.text((627, 330), 'UPDATED', font=font35, fill=white)
            draw.text((627, 375), conditions['updated'], font = font60, fill=white)  # HH:MM

        #------------------------------------------------------------------------
        #---------------- overlay data onto the image ---------------------------
        #----------------          done               ---------------------------
        #------------------------------------------------------------------------

        # save the aggregate image
        screen_output_file = os.path.join(tmpdir, 'screen_output.png')
        template.save(screen_output_file) # TODO: this should go to /tmp

        # Close the template file
        template.close()

        # write generated output file to screen
        write_to_screen(screen_output_file, 300)

except KeyboardInterrupt:
    print()
    print()
    print("#-----------------------------------")
    print("#       exiting on control-c        ")
    print("#    (this takes a few seconds)     ")
    epd.init()
    epd.Clear()
    epd.sleep()
    print("#          done                     ")
    print("#-----------------------------------")
    print()

# Tempest E-paper Weather Display

Raspberry Pi weather display using Waveshare e-paper 7.5 inch display, Tempest Weather Station data, and Python.

# Versions

## Version 1.3
- Cleaned up image sizing and removed loop.

# Setup

- Assuming you have a Pi of your choice loaded, you will need to setup the e-paper display per the instructions from WaveShare:  
  https://www.waveshare.com/wiki/7.5inch_e-Paper_HAT_(B)_Manual#Working_With_Raspberry_Pi  
  *Note: these instructions are for the 3 color screen which I am using. I have included comments in the code to change it back to the 2 color if desired.*

- Open `weather.py` and replace **Station ID here** with your station ID  
  (Log into tempestwx.com — after successful login your station ID will be listed at the end of the URL:  
  `https://tempestwx.com/station/XXXXXX`)  
  Replace **Token Here** with your API key (Create authorization at https://tempestwx.com/settings/tokens).

- Get your State/County ID from NWS to populate Watch/Warning data.  
  Steps:  
  1. Go to https://www.weather.gov and enter your ZIP code.  
  2. After the location loads, click **"Get detailed info"**.  
  3. Select your city if needed.  
  4. Extract the coordinates from the URL and open:  
     `https://api.weather.gov/points/[start,end]`  
     Look for `"county":` in the JSON — this is your county code.

- Create 2 cronjobs in the root crontab:

  ```bash
  sudo crontab -e
  ```
  ```bash
  */5 * * * * sudo python /path/to/weather.py > /dev/null 2>&1 &
  0 4 * * * sudo /sbin/reboot
  ```
This runs the Python script every 5 minutes and updates the screen.
Logs are sent to /dev/null to save memory.
The second cron job reboots the Raspberry Pi at 4 AM daily.

# Parts

https://www.waveshare.com/7.5inch-e-paper-hat-b.htm

- OR
https://www.waveshare.com/wiki/7.5inch_e-Paper_HAT

- Note: I have also ordered the grayscale model. The 2-color (grayscale) version refreshes in ~4 seconds vs ~24 seconds for the 3-color. The red pigment often does not activate, making the long refresh time not worth it.

- Raspberry Pi ZeroW+

- SD card for the Pi (at least 8 GB)

- Power supply for the Pi



# Licensing

- Code licensed under the MIT License

- Documentation licensed under CC BY 3.0
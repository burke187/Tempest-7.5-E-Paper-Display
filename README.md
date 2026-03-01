# Tempest E-paper Weather Display

Raspberry Pi weather display using Waveshare e-paper 7.5 inch display, Tempest Weather Station data, and Python.

![Screen Output](https://github.com/burke187/Tempest-7.5-E-Paper-Display/blob/master/pic/screen_output.png)

# Versions

## Version 1.0
- Cleaned up images, debugged, new features, general tweaking of forked version 1.3

# Setup

- Assuming you have a Pi of your choice loaded, you will need to setup the e-paper display per the instructions from WaveShare:  
  https://www.waveshare.com/wiki/7.5inch_e-Paper_HAT_(B)_Manual#Working_With_Raspberry_Pi  
  *Note: see included comments in the code to change from 3 color to 2 color and vice versa if desired.*
- Create a file named `.env` in the root directory. The content of the file should be as follows:
  ```bash
  STATION_ID=12345
  COUNTY_CODE=YOURCODE
  TEMPEST_TOKEN=your-tempest-token
  ```
- Your `STATION_ID` will be in the URL when you log in:
  `https://tempestwx.com/station/XXXXXX`  

- Your `TEMPEST_TOKEN` is the token you generated here: https://tempestwx.com/settings/tokens

- Get your `COUNTY_CODE` from NWS to populate Watch/Warning data.  
  Steps:  
  1. Go to https://www.weather.gov and enter your ZIP code.  
  2. After the location loads, click **"Get detailed info"**.  
  3. Select your city if needed.  
  4. Extract the coordinates from the URL and open:  
     `https://api.weather.gov/points/[start,end]`  
     Look for `"county":` in the JSON — this is your county code.

- Deploy repository to Raspberry Pi:
  ```bash
  scp -r Tempest-7.5-E-Paper-Display/ admin@your-raspberry-pi.local:/home/admin/
  ```

- SSH into your Raspberry Pi and create 2 cronjobs in the root crontab:

  ```bash
  sudo crontab -e
  ```
  ```bash
  */5 * * * * sudo python /home/admin/Tempest-7.5-E-Paper-Display/weather.py > /dev/null 2>&1 &
  0 4 * * * sudo /sbin/reboot
  ```
This runs the Python script every 5 minutes and updates the screen with new data.
Logs are sent to /dev/null to save memory.
The second cron job reboots the Raspberry Pi at 4 AM daily.

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
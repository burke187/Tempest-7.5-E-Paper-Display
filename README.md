<h1>Tempest E-paper Weather Display</h1>
<br>
  Raspberry Pi weather display using Waveshare e-paper 7.5 inch display, Tempest Weather Station data, and Python.
<h1>Versions</h1>
  <h2>Version 1.3</h2>
    <ul>
	    <li>Cleaned up image sizing and removed loop.</li>
    </ul>

<h1>Setup</h1>
  <ol type="1">
    <li>Assuming you have a Pi of your choice loaded, you will need to setup the e-paper display per the instructions from WaveShare: https://www.waveshare.com/wiki/7.5inch_e-Paper_HAT_(B)_Manual#Working_With_Raspberry_Pi.  *Note: these instructions are for the 3 color screen which I am using.  I have included comments in the code to change it back to the 2 color if desired.</li>
    <li>Open 'weather.py' and replace **Station ID here** with you station ID (Log into tempestwx.com - after successful login your station id will be listed at the end of the URL: https://tempestwx.com/station/XXXXXX) and **Token Here** with your API key (Create authorization at https://tempestwx.com/settings/tokens).</li>
    <li>Get your State/County ID from NSW to populate Watch/Warning data.  I have not found a great way to get this data other than using a multi-step process.  1. Go to https://www.weather.gov and enter your ZIP code on the left.  2. After the locaiton loads, click on "Get detailed info" 3. Select your city if needed 4. Get the coordinates out of the URL - these will be plugged into the API via browser of your choice: https://api.weather.gov/points/[start,end] - read through the data and look for "county": at the end of the JSON response.  This is your county code to plug into the Python code.  </li>
    <li>Create 2 cronjobs in the root crontab: 
      ```
      sudo crontab -e
      ```
      ```
      */5 * * * * sudo python /path/to/weather.py > /dev/null 2>&1 &`
      0 4 * * * sudo /sbin/reboot
      ```
      This runs the python script every 5 minutes and updates the screen. Logs are sent to /dev/null to save memory. The second cron reboots the Raspberry Pi every day at 4am.
    </li>
  </ol>
<br>  

# Parts
<ul>
  <li>https://www.waveshare.com/7.5inch-e-paper-hat-b.htm -OR- https://www.waveshare.com/wiki/7.5inch_e-Paper_HAT *Note: I have actually ordered the grayscale screen.  Having built one of each with the 3 color, the refresh time on the 2 color (grayscale) is so much faster I would not recommend the screen that includes red.  To date, I have not been able to get the red to work which means I just have a ridiculously long refresh time screen.  Not worth it.  The 2 color will refresh in 4 seconds vs ~24 for the 3 color.</li>
  <li>Raspberry Pi ZeroW+</li>
  <li>SD card for the Pi at least 8 GB.</li>
  <li>Power supply for the Pi.</li>
  <li>5 x 7 inch photo frame</li>
</ul>



<h1>Licensing</h1>
  <ul>
    <li>Code licensed under [MIT License](http://opensource.org/licenses/mit-license.html)</li>
    <li>Documentation licensed under [CC BY 3.0](http://creativecommons.org/licenses/by/3.0)</li>
  <ul>

![GitHub Release](https://img.shields.io/github/v/release/jackjpowell/hass-kub)
![GitHub Downloads (all assets, all releases)](https://img.shields.io/github/downloads/jackjpowell/hass-kub/total)
<a href="#"><img src="https://img.shields.io/maintenance/yes/2024.svg"></a>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://brands.home-assistant.io/kub/logo.png">
  <img alt="Knoxville Utilities Board Logo" src="https://brands.home-assistant.io/kub/logo.png">
</picture>

## Knoxville Utilities Board for Home Assistant

Home Assistant integration for the [Knoxville Utilities Board](https://www.kub.org/).

## Installation

There are two main ways to install this custom component within your Home Assistant instance:

1. Using HACS (see https://hacs.xyz/ for installation instructions if you do not already have it installed):

    [![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=JackJPowell&repository=hass-kub&category=Integration)

   Or
   
   1. From within Home Assistant, click on the link to **HACS**
   2. Click on **Integrations**
   3. Click on the vertical ellipsis in the top right and select **Custom repositories**
   4. Enter the URL for this repository in the section that says _Add custom repository URL_ and select **Integration** in the _Category_ dropdown list
   5. Click the **ADD** button
   6. Close the _Custom repositories_ window
   7. You should now be able to see the _KUB_ card on the HACS Integrations page. Click on **INSTALL** and proceed with the installation instructions.
   8. Restart your Home Assistant instance and then proceed to the _Configuration_ section below.

3. Manual Installation:
   1. Download or clone this repository
   2. Copy the contents of the folder **custom_components/kub** into the same file structure on your Home Assistant instance
   3. Restart your Home Assistant instance and then proceed to the _Configuration_ section below.

While the manual installation above seems like less steps, it's important to note that you will not be able to see updates to this custom component unless you are subscribed to the watch list. You will then have to repeat each step in the process. By using HACS, you'll be able to see that an update is available and easily update the custom component. Trust me, HACS is the worth the small upfront investment to get it setup.

## Configuration

There is a config flow for this integration. After installing the custom component and restarting:

1. Go to **Settings** -> **Devices & Services** -> **Integrations**
2. Click **+ ADD INTEGRATION** to setup a new integration
3. Search for **KUB** and select it
4. _You will now begin the configuration flow process_
5. Enter your KUB Username and Password into the prompt
6. Submit

## Usage

After the device is configured, the integration will expose 1 to 4 entities depending on the services available within your account:

- Sensors
  - Electricity
  - Gas
  - Water
  - Waste Water

KUB only updates their api data once a day so this integration is set to only poll once every 12 hours. However, once new data is retrieved, hourly statistics will also be back-loaded to be displayed on your energy dashboard.

## Options

Under the configure menu, you will find a single option to combine waste water usage and cost data into the water statistics. This is directed at those of us who only have a single point of water service and waste water is calculated via water consumption. This allows the statistics to better represent the total water cost for your residence. Even with this option enabled you will still have unique water and waste water summary sensors.

## Considerations

In an effort to improve startup times, you may notice upon restart that your KUB sensors are listed as _Unknown_. This is expected as usage/cost data retrieval has been delayed until after Home Assistant startup has completed. This delay significantly improves start times for the KUB integration.

## Your Support

As alluded to above, I only have a single line of water service and because of this I'm not able to determine what the api response looks like for those of you with multiple lines. This is most commonly seen when a residence has a pool or a large irrigation system. If this is you, could I ask a favor? On the KUB Devices screen there is a _visit_ link and to the right an overflow menu. If you select it, you will see an option to download diagnostics data. Select it and the browser will save a diagnostics json file. Next go to [my repo](https://github.com/JackJPowell/hass-kub) and create a new issue or discussion and provide that file to me. You can also email it my way as well. Thank you!

## Future Ideas

- [ ] Support multiple water lines

## Notes

- No Notes

## About This Project

I am not associated with KUB and provide this custom component purely for your own enjoyment and home automation needs.

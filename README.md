![GitHub Release](https://img.shields.io/github/v/release/jackjpowell/hass-kub)
![GitHub Downloads (all assets, all releases)](https://img.shields.io/github/downloads/jackjpowell/hass-kub/total)

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="">
  <img alt="Playstation Network logo" src="">
</picture>

## Knoxville Utility Board for Home Assistant

Home Assistant integration for the [Knoxville Utility Board](https://www.kub.org/).

## Installation

There are two main ways to install this custom component within your Home Assistant instance:

1. Using HACS (see https://hacs.xyz/ for installation instructions if you do not already have it installed):

   1. From within Home Assistant, click on the link to **HACS**
   2. Click on **Integrations**
   3. Click on the vertical ellipsis in the top right and select **Custom repositories**
   4. Enter the URL for this repository in the section that says _Add custom repository URL_ and select **Integration** in the _Category_ dropdown list
   5. Click the **ADD** button
   6. Close the _Custom repositories_ window
   7. You should now be able to see the _KUB_ card on the HACS Integrations page. Click on **INSTALL** and proceed with the installation instructions.
   8. Restart your Home Assistant instance and then proceed to the _Configuration_ section below.

2. Manual Installation:
   1. Download or clone this repository
   2. Copy the contents of the folder **custom_components/KUB** into the same file structure on your Home Assistant instance
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

After the device is configured, the integration will expose 1 to 4 entities:

- Sensors
  - Electricity
  - Gas
  - Water
  - Waste Water

## Future Ideas

- [ ] Future fun

## Notes

- No Notes

## About This Project

I am not associated with KUB and provide this custom component purely for your own enjoyment and home automation needs.

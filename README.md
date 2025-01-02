# Dominion Energy Scraper Home Assistant AppDaemon integration

This repo contains appdaemon scripts in order to scrape the excel energy usage stats from Dominion Energy, using Selenium. 
Note that this data appears delayed by 24H, so it is always backfilled. In order to do this, the Spooky integration is required from HACS
in order to expose a service call to load historical data.  

## Instructions

HA needs MQTT enabled and configured, as well as the Spooky integration from HACS to backfill data.

### Initial appdaemon install

Assuming use of appdaemon in container, update appdaemon.yaml to configure MQTT under mqtt
namespace, HASS under hass namespace. Append contents of apps.yaml to existing apps.yaml and update
accordingly. Also update both secrets.yaml. Copy the remaining files under config to appdaemon
config.

### Optional: Persist container updates
Start appdaemon container. Once at steady state and package updates applied, run `podman commit
[container_name]`, then get image list w/ `podman images -a` and tag the most recent hash w/ `podman
tag [hash] image_name:version` 


### Update HA entity names

Once AppDaemon starts, and the entities created in HA under MQTT, configure HA entities for dominion
w/ the following names: `sensor.dominion_energy_statistics_power`, `sensor.dominion_energy_statistics_energy`, 
`sensor.dominion_energy_statistics_monthly_cost`. 



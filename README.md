# Dominion Energy Scraper Home Assistant App daemon integration

## Instructions

HA needs MQTT enabled and configured. 

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



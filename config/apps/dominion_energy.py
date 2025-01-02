#! /usr/bin/env python3
import sys
import tempfile
import pathlib

import datetime
import time
import zoneinfo
import shutil
import itertools
import json

import pandas as pd

from typing import Any, Dict

import dominion_scrape

import mqttapi as mqtt
import hassapi as hass 
import adbase as ad

class DominionEnergy(ad.ADBase):
    def setup_devices(self):
        dominion_energy_device = {
            "dev": {
                "ids": "74d04845e2afd085",
                "name": "Dominion Energy Statistics",
                "mf": "Dominion Energy",
                "mdl": "N/A",
                "sw": "1.0",
                "sn": "N/A",
                "hw": "N/A",
                },
            "o": {
                "name":"AppDaemon MQTT",
                "sw": "1.0",
                "url": "https://jhnphm.github.com",
                },
            "cmps": {
                "dominion_energy_power": {
                    "p": "sensor",
                    "device_class":"power",
                    "unit_of_measurement":"kW",
                    "name": "Dominion Energy Power",
                    "value_template":"{{ value_json.power}}",
                    "unique_id":"power_145b",
                    'icon': 'mdi:home-lightning-bolt'
                },
                "dominion_energy_energy": {
                    "p": "sensor",
                    "device_class":"energy",
                    "name": "Dominion Energy Total Energy",
                    "unit_of_measurement":"kWh",
                    "value_template":"{{ value_json.energy}}",
                    "unique_id":"energy_9368",
                    'icon': 'mdi:home-lightning-bolt'
                },
                "dominion_energy_cost": {
                    "p": "sensor",
                    "unit_of_measurement":"USD",
                    "name": "Dominion Energy Monthly Cost",
                    "value_template":"{{ value_json.monthly_cost}}",
                    "unique_id":"energymonthlycost_4611",
                    'icon': 'mdi:cash'
                },
            },
            "state_topic":"dominion_energy/state",
            "qos": 0,
        }
        
        self.mqtt.mqtt_publish(topic="homeassistant/device/dominion_energy/config", payload=json.dumps(dominion_energy_device), namespace="mqtt")
    def initialize(self): 
        self.hass = self.get_plugin_api("HASS") # namespace name, see appdaemon.yaml
        self.adbase = self.get_ad_api()
        self.mqtt = self.get_plugin_api("MQTT")
        self.email = self.args["email"]
        self.password = self.args["password"]
        self.tariff_schedule = self.args['tariff_schedule']
        self.data_cache = self.args["data_cache"]
        self.tz = self.args["tz"]
        self.skip = self.args["skip"]

        self.setup_devices()


        # add random fuzz to run time
        self.adbase.run_every(self.load_data, "now", 60*60*12, random_start=0, random_end=3600/2)
        
        self.load_data()
        

    def run_scrape(self, **kwargs):
        self.adbase.log("Running scrape")
        with tempfile.TemporaryDirectory() as tmpdir:
            scraper = dominion_scrape.Scraper(email=self.email, password=self.password, format=dominion_scrape.ScrapeFormat.XLSX, download_dir=tmpdir)
            scraper.run()
            xlsx_path = list(pathlib.Path(tmpdir).glob('*.xlsx'))[0]
            shutil.copy(xlsx_path, self.data_cache)
        self.adbase.log("Scrape done")
    
    def load_df(self, **kwargs):
        self.setup_devices()
        self.data = pd.read_excel(self.data_cache, engine='openpyxl').fillna(0)
        df = self.data
        columns_list = list(df.columns)
        time_start = columns_list.index("Date")+1

        power = []
        energy = []
        monthly_costs = []

        last_stat = 0 # last power measurement at half-hour interval
        total = 0  # total energy from beginning
        monthly_energy = 0
        cur_start_of_month = datetime.datetime.now().astimezone().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        for i,row in df.iterrows():
            date = row["Date"]
            if sum(row[time_start:]) == 0:
                break
            for timestamp_col in df.columns[time_start:]:
                if ":30" in timestamp_col:
                    last_stat = row[timestamp_col]
                else:
                    timestamp_str = date + " " + timestamp_col.replace(" kWH", "")
                    date_time = datetime.datetime.fromtimestamp(time.mktime(time.strptime(timestamp_str, "%m/%d/%Y %I:%M %p")), tz = zoneinfo.ZoneInfo(self.tz))

                    stat = row[timestamp_col] + last_stat 
                    total += stat

                    if date_time == date_time.replace(day=1,hour=0,minute=0,second=0,microsecond=0): # first measurement of month
                        monthly_energy = 0
                        reset_monthly = True
                    else:
                        reset_monthly = False


                    date_str = date_time.strftime("%Y-%m-%d %H:%M:%S%z")
                    monthly_energy += stat

                    # cost calculations
                    monthly_cost = self.tariff_schedule['base_monthly_cost']
                    for i,(lower,upper) in enumerate(itertools.pairwise(self.tariff_schedule['thresholds'])):
                        if monthly_energy >= lower and monthly_energy < upper:
                            monthly_cost += self.tariff_schedule['rates'][date_time.month-1][i]*(monthly_energy-lower)
                        elif monthly_energy >= upper:
                            monthly_cost += self.tariff_schedule['rates'][date_time.month-1][i]*(upper-lower)

                    upper = self.tariff_schedule['thresholds'][-1]
                    if monthly_energy > upper:
                        monthly_cost += self.tariff_schedule['rates'][date_time.month-1][-1]*(monthly_energy-upper)


                    power.append({"start": date_str, "last_reset": date_str, "mean": stat, "max": stat, "min": stat})
                    energy.append({"start": date_str, "sum": total, "state": total})

                    if len(monthly_costs) == 0:
                        cost_sum = monthly_cost
                    else:
                        if reset_monthly:
                            cost_sum = monthly_costs[-1]['sum'] + monthly_cost
                        else:
                            cost_sum = monthly_cost - monthly_costs[-1]['state'] + monthly_costs[-1]['sum']
                    monthly_costs.append({"start": date_str, "sum": cost_sum, "state": monthly_cost})

                    


        # Load in currently monthly energy use to date as non-historical data (useful for computing cost per kWh
        #self.dominion_energy_monthly_cumulative_usage.set_state(state=monthly_energy, attributes=self.monthly_energy_entity_attributes)

        # Load in a week at a time
        batch_size = 24*7 # One week
        
        # Stolen from itertools for older py
        def batched(iterable, n, *, strict=False):
            # batched('ABCDEFG', 3) → ABC DEF G
            if n < 1:
                raise ValueError('n must be at least one')
            iterator = iter(iterable)
            while batch := tuple(itertools.islice(iterator, n)):
                if strict and len(batch) != n:
                    raise ValueError('batched(): incomplete batch')
                yield batch

        for batch in batched(power[self.skip:], batch_size):
            self.hass.call_service("recorder/import_statistics", statistic_id="sensor.dominion_energy_statistics_power", name="sensor.dominion_energy_statistics_power", source="recorder", has_sum=False, has_mean=True, unit_of_measurement='kW', stats=batch, namespace="hass")
        for batch in batched(energy[self.skip:], batch_size):
            self.hass.call_service("recorder/import_statistics", statistic_id="sensor.dominion_energy_statistics_energy", name="sensor.dominion_energy_statistics_energy", source="recorder", has_sum=True, has_mean=False, unit_of_measurement='kWh', stats=batch, namespace="hass")
        for batch in batched(monthly_costs[self.skip:], batch_size):
            self.hass.call_service("recorder/import_statistics", statistic_id="sensor.dominion_energy_statistics_monthly_cost", name="sensor.dominion_energy_statistics_monthly_cost", source="recorder", has_sum=True, has_mean=False, unit_of_measurement='USD', stats=batch, namespace="hass")
        
        self.skip = len(power)

        self.adbase.log("Pushed updated stats")


            
    def load_data(self, cb_args=None):
        try:
            self.run_scrape()
            self.load_df()

        except Exception as e:
            print(e)


        

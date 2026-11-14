"""Dry check of the final path without joining anything: preset parses, kit imports, server answers, map loads.
  PYTHONPATH=src python lab/build/dryrun.py [--preset c1] [--set k=v ...]"""
import argparse
import os
import sys

import spread

from spreadbot.config import Config
from spreadbot.geo import load_geo
from spreadbot.presets import PRESETS

ap = argparse.ArgumentParser()
ap.add_argument("--preset", default="")
ap.add_argument("--set", action="append", default=[])
a = ap.parse_args()
sets = (PRESETS[a.preset] if a.preset else []) + a.set
cfg = Config.parse(sets)
print("config ok:", a.preset or "defaults", len(sets), "overrides; hold", cfg.hold, "gov_tight", cfg.gov_tight, "theta", cfg.theta)
c = spread.Client()
geo = load_geo(c)
print("map ok:", len(geo.ids), "places")
print("worlds call ok:", len(c.worlds()), "worlds on the team key")
try:
    f = c.final()
    print("final endpoint answers: a final is set, world", f.get("worldId"), "now", f.get("now"))
except spread.SpreadError as e:
    print("final endpoint answers: no final now (status", e.status, ")")

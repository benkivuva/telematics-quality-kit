#!/bin/bash
echo "=== Testing Bug 1: clear command argument order ==="
uv run telematics shell --vehicles 20 << 'COMMANDS'
inject rural_blackout TRK-0001
clear TRK-0001 rural_blackout
exit
COMMANDS

echo -e "\n=== Testing Bug 2: Logger leakage on bad input ==="
uv run telematics shell --vehicles 20 << 'COMMANDS'
get FAKE-9999
exit
COMMANDS

echo -e "\n=== Testing Bug 3: clear all vs reset ==="
uv run telematics shell --vehicles 20 << 'COMMANDS'
inject gps_drift CAR-0002
advance 10m
clear all
fleet
reset
fleet
exit
COMMANDS

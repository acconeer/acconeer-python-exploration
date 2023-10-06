#!/bin/bash

# Optionally accepts a python version (e.g. "3.9")
# as the first argument. Defaults to "3.8"
python_version="${1:-3.8}"


short_hostname=$(hostname -s)
echo -e "Running on host: $short_hostname\n"

echo "Running A111 integration tests"
hatch run +py=$python_version test:integration-a111 --uart --spi
exit $?

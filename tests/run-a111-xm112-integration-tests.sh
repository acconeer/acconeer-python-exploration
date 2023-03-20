#!/bin/bash

# Optionally accepts a python version (e.g. "3.7")
# as the first argument. Defaults to "3.8"
python_version="${1:-3.8}"


short_hostname=$(hostname -s)
echo -e "Running on host: $short_hostname\n"

echo "Running A111 integration tests"
nox -s "test(python='$python_version')" -- --test-groups integration --integration-args a111 --uart --spi
exit $?

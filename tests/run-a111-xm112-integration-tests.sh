#!/bin/bash

short_hostname=$(hostname -s)
echo -e "Running on host: $short_hostname\n"

echo "Running A111 integration tests"
nox --no-error-on-missing-interpreters -s test -- --test-groups integration --integration-args a111 --uart --spi
exit $?

#!/bin/bash

# Optionally accepts a python version (e.g. "3.9")
# as the first argument. Defaults to "3.8"
python_version="${1:-3.8}"
# Optionally accepts a port (e.g. 1337) as the second argument.
# If not passed, the port flag will not be passed to the server or the tests
port="$2"

short_hostname=$(hostname -s)
echo -e "Running on host: $short_hostname\n"

echo "Running A111 integration tests"
if [ -n "$port" ]; then
  stash/out/customer/a111/internal_sanitizer_x86_64/out/acc_exploration_server_a111 --port "$port" > output_a111.txt &
else
  stash/out/customer/a111/internal_sanitizer_x86_64/out/acc_exploration_server_a111 > output_a111.txt &
fi
a111_pid=$!

if [ -n "$port" ]; then
  hatch run +py=$python_version test:integration-a111 --socket localhost 1 --port "$port"
else
  hatch run +py=$python_version test:integration-a111 --socket localhost 1
fi
a111_test_exit_code=$?

kill -s SIGINT $a111_pid
cat output_a111.txt

exit $a111_test_exit_code

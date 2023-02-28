#!/bin/bash

# Optionally accepts a python version (e.g. "3.7")
# as the first argument. Defaults to "3.8"
python_version="${1:-3.8}"
# Optionally accepts a port (e.g. 1337)
# as the second argument. Defaults to 6110
port="${2:-6110}"

short_hostname=$(hostname -s)
echo -e "Running on host: $short_hostname\n"

echo "Running A111 integration tests"
stash/out/customer/a111/internal_sanitizer_x86_64/out/acc_exploration_server_a111 --port "$port" > output_a111.txt &
a111_pid=$!
nox -s "test(python='$python_version')" -- --editable --test-groups integration --integration-args a111 --socket localhost 1 --port "$port"
a111_test_exit_code=$?

kill -s SIGINT $a111_pid
cat output_a111.txt

exit $a111_test_exit_code

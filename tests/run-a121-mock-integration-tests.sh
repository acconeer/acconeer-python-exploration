#!/bin/bash

# Optionally accepts a python version (e.g. "3.7")
# as the first argument. Defaults to "3.8"
python_version="${1:-3.8}"

short_hostname=$(hostname -s)
echo -e "Running on host: $short_hostname\n"

echo "Running A121 integration tests"
ACC_MOCK_TEST_PATTERN=1 stash/out/customer/a121/internal_sanitizer_x86_64/out/acc_exploration_server_a121 > output_a121.txt &
a121_pid=$!
nox -s "test(python='$python_version')" -- --test-groups integration --integration-args a121
a121_test_exit_code=$?

kill -s SIGINT $a121_pid
cat output_a121.txt

exit $a121_test_exit_code

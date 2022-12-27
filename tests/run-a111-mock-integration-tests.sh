#!/bin/bash

short_hostname=$(hostname -s)
echo -e "Running on host: $short_hostname\n"

echo "Running A111 integration tests"
stash/out/customer/a111/internal_sanitizer_x86_64/out/acc_exploration_server_a111 > output_a111.txt &
a111_pid=$!
nox --no-error-on-missing-interpreters -s test -- --test-groups integration --integration-args a111 --socket localhost 1
a111_test_exit_code=$?

kill -s SIGINT $a111_pid
cat output_a111.txt

exit $a111_test_exit_code

#!/bin/bash

short_hostname=$(hostname -s)
echo -e "Running on host: $short_hostname\n"

ACC_BOARD=emulation stash/out/customer/internal_sanitizer_x86_64/out/acc_exploration_server_a111 > output.txt &
pid=$!

pytest -v tests/integration --socket localhost 1

test_result=$?
kill -s SIGINT $pid

cat output.txt

exit $test_result

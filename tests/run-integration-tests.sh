#!/bin/bash

short_hostname=$(hostname -s)
echo -e "Running on host: $short_hostname\n"

echo "Running A111 integration tests"
stash/out/customer/a111/internal_sanitizer_x86_64/out/acc_exploration_server_a111 > output_a111.txt &
a111_pid=$!
nox -s test -- --test-groups integration --integration-args a111 --uart --spi --socket localhost 1
a111_test_exit_code=$?

kill -s SIGINT $a111_pid
cat output_a111.txt

[ $a111_test_exit_code -ne 0 ] && exit $a111_test_exit_code


echo "Running A121 integration tests"
stash/out/customer/a121/internal_sanitizer_x86_64/out/acc_exploration_server_a121 > output_a121.txt &
a121_pid=$!
nox -s test -- --test-groups integration --integration-args a121
a121_test_exit_code=$?

kill -s SIGINT $a121_pid
cat output_a121.txt

[ $a121_test_exit_code -ne 0 ] && exit $a121_test_exit_code

exit 0

#!/bin/bash
file --mime-type "$1" | sed 's/.*: //'

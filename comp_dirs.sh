#!/bin/bash
set -e

dira=$1
dirb=$2

diff <(cd ${dira} && find . | sort) <(cd ${dirb} && find . | sort) 

#!/bin/sh

token=218c38fc5e1c1523657c64dc54adea5642af7948
username=stefangstark
name=$1

curl -u "$username:$token" https://api.github.com/user/repos -d '{"name":"'$name'"}'

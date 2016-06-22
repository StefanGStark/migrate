#!/bin/sh

token=218c38fc5e1c1523657c64dc54adea5642af7948
username=stefangstark

github_name=$1
gitorious_url=$2


# create repo
curl -u "$username:$token" https://api.github.com/user/repos -d '{"name":"'$github_name'"}'


token=607ffa58e918fa572dbe933291477b692d7b4616
org=ratschlab
username=stefangstark
name=test
curl -u "$org:$token" https://api.github.com/user/repos -d '{"name":"'$name'"}'

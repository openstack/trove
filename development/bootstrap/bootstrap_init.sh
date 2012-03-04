### THINGS TO NOTE
# Make sure the host code is in /src
# Make sure the username is the same as the vm/host
# ** Assuming the username is reddwarf
# Make sure the host/vm bridge is at 10.0.0.1, which is the default devstack bridge
PATH_TO_HOST=/src/reddwarf

sudo -u reddwarf scp -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -r 10.0.0.1:${PATH_TO_HOST}/guest-agent ~reddwarf
python ~reddwarf/guest-agent/agent.py
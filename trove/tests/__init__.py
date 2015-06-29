import os

DBAAS_API = "dbaas.api"
PRE_INSTANCES = "dbaas.api.pre_instances"
INSTANCES = "dbaas.api.instances"
POST_INSTANCES = "dbaas.api.post_instances"
SSH_CMD = ('ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no '
           + ('-o LogLevel=quiet -i '
              + os.environ.get('TROVE_TEST_SSH_KEY_FILE')
              if 'TROVE_TEST_SSH_KEY_FILE' in os.environ else ""))

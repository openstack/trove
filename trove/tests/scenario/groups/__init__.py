# Copyright 2016 Tesora Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.


# Labels for all the sub-groups are listed here, so that they can be
# referenced by other groups (thus avoiding circular references when
# loading modules).  The main GROUP label is still defined in each
# respective group file.

# Backup Group
BACKUP = "scenario.backup_grp"
BACKUP_CREATE = "scenario.backup_create_grp"
BACKUP_CREATE_NEGATIVE = "scenario.backup_create_negative_grp"
BACKUP_CREATE_WAIT = "scenario.backup_create_wait_grp"
BACKUP_DELETE = "scenario.backup_delete_grp"
BACKUP_INST = "scenario.backup_inst_grp"
BACKUP_INST_CREATE = "scenario.backup_inst_create_grp"
BACKUP_INST_CREATE_WAIT = "scenario.backup_inst_create_wait_grp"
BACKUP_INST_DELETE = "scenario.backup_inst_delete_grp"
BACKUP_INST_DELETE_WAIT = "scenario.backup_inst_delete_wait_grp"

BACKUP_INC = "scenario.backup_inc_grp"
BACKUP_INC_CREATE = "scenario.backup_inc_create_grp"
BACKUP_INC_DELETE = "scenario.backup_inc_delete_grp"
BACKUP_INC_INST = "scenario.backup_inc_inst_grp"
BACKUP_INC_INST_CREATE = "scenario.backup_inc_inst_create_grp"
BACKUP_INC_INST_CREATE_WAIT = "scenario.backup_inc_inst_create_wait_grp"
BACKUP_INC_INST_DELETE = "scenario.backup_inc_inst_delete_grp"
BACKUP_INC_INST_DELETE_WAIT = "scenario.backup_inc_inst_delete_wait_grp"


# Configuration Group
CFGGRP_CREATE = "scenario.cfggrp_create_grp"
CFGGRP_DELETE = "scenario.cfggrp_delete_grp"
CFGGRP_INST = "scenario.cfggrp_inst_grp"
CFGGRP_INST_CREATE = "scenario.cfggrp_inst_create_grp"
CFGGRP_INST_CREATE_WAIT = "scenario.cfggrp_inst_create_wait_grp"
CFGGRP_INST_DELETE = "scenario.cfggrp_inst_delete_grp"
CFGGRP_INST_DELETE_WAIT = "scenario.cfggrp_inst_delete_wait_grp"


# Database Actions Group
DB_ACTION_CREATE = "scenario.db_action_create_grp"
DB_ACTION_DELETE = "scenario.db_action_delete_grp"
DB_ACTION_INST = "scenario.db_action_inst_grp"
DB_ACTION_INST_CREATE = "scenario.db_action_inst_create_grp"
DB_ACTION_INST_CREATE_WAIT = "scenario.db_action_inst_create_wait_grp"
DB_ACTION_INST_DELETE = "scenario.db_action_inst_delete_grp"
DB_ACTION_INST_DELETE_WAIT = "scenario.db_action_inst_delete_wait_grp"


# Instance Actions Group
INST_ACTIONS = "scenario.inst_actions_grp"
INST_ACTIONS_RESIZE = "scenario.inst_actions_resize_grp"
INST_ACTIONS_RESIZE_WAIT = "scenario.inst_actions_resize_wait_grp"


# Instance Upgrade Group
INST_UPGRADE = "scenario.inst_upgrade_grp"


# Instance Create Group
INST_CREATE = "scenario.inst_create_grp"
INST_CREATE_WAIT = "scenario.inst_create_wait_grp"
INST_INIT_CREATE = "scenario.inst_init_create_grp"
INST_INIT_CREATE_WAIT = "scenario.inst_init_create_wait_grp"
INST_INIT_DELETE = "scenario.inst_init_delete_grp"
INST_INIT_DELETE_WAIT = "scenario.inst_init_delete_wait_grp"


# Instance Delete Group
INST_DELETE = "scenario.inst_delete_grp"
INST_DELETE_WAIT = "scenario.inst_delete_wait_grp"


# Instance Error Create Group
INST_ERROR_CREATE = "scenario.inst_error_create_grp"
INST_ERROR_CREATE_WAIT = "scenario.inst_error_create_wait_grp"
INST_ERROR_DELETE = "scenario.inst_error_delete_grp"
INST_ERROR_DELETE_WAIT = "scenario.inst_error_delete_wait_grp"


# Instance Force Delete Group
INST_FORCE_DELETE = "scenario.inst_force_delete_grp"
INST_FORCE_DELETE_WAIT = "scenario.inst_force_delete_wait_grp"


# Module Group
MODULE_CREATE = "scenario.module_create_grp"
MODULE_DELETE = "scenario.module_delete_grp"
MODULE_INST = "scenario.module_inst_grp"
MODULE_INST_CREATE = "scenario.module_inst_create_grp"
MODULE_INST_CREATE_WAIT = "scenario.module_inst_create_wait_grp"
MODULE_INST_DELETE = "scenario.module_inst_delete_grp"
MODULE_INST_DELETE_WAIT = "scenario.module_inst_delete_wait_grp"


# Replication Group
REPL_INST = "scenario.repl_inst_grp"
REPL_INST_CREATE = "scenario.repl_inst_create_grp"
REPL_INST_CREATE_WAIT = "scenario.repl_inst_create_wait_grp"
REPL_INST_MULTI_CREATE = "scenario.repl_inst_multi_create_grp"
REPL_INST_DELETE_NON_AFFINITY_WAIT = "scenario.repl_inst_delete_noaff_wait_grp"
REPL_INST_MULTI_CREATE_WAIT = "scenario.repl_inst_multi_create_wait_grp"
REPL_INST_MULTI_PROMOTE = "scenario.repl_inst_multi_promote_grp"
REPL_INST_DELETE = "scenario.repl_inst_delete_grp"
REPL_INST_DELETE_WAIT = "scenario.repl_inst_delete_wait_grp"


# Root Actions Group
ROOT_ACTION_ENABLE = "scenario.root_action_enable_grp"
ROOT_ACTION_DISABLE = "scenario.root_action_disable_grp"
ROOT_ACTION_INST = "scenario.root_action_inst_grp"
ROOT_ACTION_INST_CREATE = "scenario.root_action_inst_create_grp"
ROOT_ACTION_INST_CREATE_WAIT = "scenario.root_action_inst_create_wait_grp"
ROOT_ACTION_INST_DELETE = "scenario.root_action_inst_delete_grp"
ROOT_ACTION_INST_DELETE_WAIT = "scenario.root_action_inst_delete_wait_grp"


# User Actions Group
USER_ACTION_CREATE = "scenario.user_action_create_grp"
USER_ACTION_DELETE = "scenario.user_action_delete_grp"
USER_ACTION_INST = "scenario.user_action_inst_grp"
USER_ACTION_INST_CREATE = "scenario.user_action_inst_create_grp"
USER_ACTION_INST_CREATE_WAIT = "scenario.user_action_inst_create_wait_grp"
USER_ACTION_INST_DELETE = "scenario.user_action_inst_delete_grp"
USER_ACTION_INST_DELETE_WAIT = "scenario.user_action_inst_delete_wait_grp"

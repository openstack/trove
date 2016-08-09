# Copyright 2013 Hewlett-Packard Development Company, L.P.
# All Rights Reserved.
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
#
from trove.common import cfg

CONF = cfg.CONF

url_ref = {
    "type": "string",
    "minLength": 8,
    "pattern": 'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]'
               '|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
}

boolean_string = {
    "type": "integer",
    "minimum": 0,
    "maximum": 1
}

non_empty_string = {
    "type": "string",
    "minLength": 1,
    "maxLength": 255,
    "pattern": "^.*[0-9a-zA-Z]+.*$"
}

configuration_data_types = {
    "type": "string",
    "minLength": 1,
    "pattern": "integer|string"
}

configuration_integer_size = {
    "type": "string",
    "maxLength": 40,
    "pattern": "[0-9]+"
}

configuration_positive_integer = {
    "type": "string",
    "maxLength": 40,
    "minLength": 1,
    "pattern": "^[0-9]+$"
}

configuration_non_empty_string = {
    "type": "string",
    "minLength": 1,
    "maxLength": 128,
    "pattern": "^.*[0-9a-zA-Z]+.*$"
}

flavorref = {
    'oneOf': [
        non_empty_string,
        {
            "type": "integer"
        }]
}

volume_size = {
    "oneOf": [
        {
            "type": "integer",
            "minimum": 0
        },
        configuration_positive_integer]
}

host_string = {
    "type": "string",
    "minLength": 1,
    "pattern": "^[%]?[\w(-).]*[%]?$"
}

name_string = {
    "type": "string",
    "minLength": 1,
    "pattern": "^.*[0-9a-zA-Z]+.*$"
}

uuid = {
    "type": "string",
    "minLength": 1,
    "maxLength": 64,
    "pattern": "^([0-9a-fA-F]){8}-([0-9a-fA-F]){4}-([0-9a-fA-F]){4}"
               "-([0-9a-fA-F]){4}-([0-9a-fA-F]){12}$"
}

volume = {
    "type": "object",
    "required": ["size"],
    "properties": {
        "size": volume_size,
        "required": True
    }
}

nics = {
    "type": "array",
    "items": {
        "type": "object",
    }
}

databases_ref_list = {
    "type": "array",
    "minItems": 0,
    "uniqueItems": True,
    "items": {
        "type": "object",
        "required": ["name"],
        "additionalProperties": True,
        "properties": {
            "name": non_empty_string
        }
    }
}

databases_ref_list_required = {
    "type": "array",
    "minItems": 0,
    "uniqueItems": True,
    "items": {
        "type": "object",
        "required": ["name"],
        "additionalProperties": True,
        "properties": {
            "name": non_empty_string
        }
    }
}

databases_ref = {
    "type": "object",
    "required": ["databases"],
    "additionalProperties": True,
    "properties": {
        "databases": databases_ref_list_required
    }
}

databases_def = {
    "type": "array",
    "minItems": 0,
    "items": {
        "type": "object",
        "required": ["name"],
        "additionalProperties": True,
        "properties": {
            "name": non_empty_string,
            "character_set": non_empty_string,
            "collate": non_empty_string
        }
    }
}

user_attributes = {
    "type": "object",
    "additionalProperties": True,
    "minProperties": 1,
    "properties": {
        "name": name_string,
        "password": non_empty_string,
        "host": host_string
    }
}


users_list = {
    "type": "array",
    "minItems": 0,
    "items": {
        "type": "object",
        "required": ["name", "password"],
        "additionalProperties": True,
        "properties": {
            "name": name_string,
            "password": non_empty_string,
            "host": host_string,
            "databases": databases_ref_list
        }
    }
}

null_configuration_id = {
    "type": "null"
}

configuration_id = {
    'oneOf': [
        uuid,
        null_configuration_id
    ]
}

module_list = {
    "type": "array",
    "minItems": 0,
    "items": {
        "type": "object",
        "required": ["id"],
        "additionalProperties": True,
        "properties": {
            "id": uuid,
        }
    }
}

cluster = {
    "create": {
        "type": "object",
        "required": ["cluster"],
        "additionalProperties": True,
        "properties": {
            "cluster": {
                "type": "object",
                "required": ["name", "datastore", "instances"],
                "additionalProperties": True,
                "properties": {
                    "name": non_empty_string,
                    "datastore": {
                        "type": "object",
                        "required": ["type", "version"],
                        "additionalProperties": True,
                        "properties": {
                            "type": non_empty_string,
                            "version": non_empty_string
                        }
                    },
                    "instances": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["flavorRef"],
                            "additionalProperties": True,
                            "properties": {
                                "flavorRef": flavorref,
                                "volume": volume,
                                "nics": nics,
                                "availability_zone": non_empty_string,
                                "modules": module_list,
                            }
                        }
                    }
                }
            }
        }
    },
    "add_shard": {
        "type": "object",
        "required": ["add_shard"],
        "additionalProperties": True,
        "properties": {
            "add_shard": {
                "type": "object"
            }
        }
    },
    "grow": {
        "type": "object",
        "required": ["grow"],
        "additionalProperties": True,
        "properties": {
            "grow": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["flavorRef"],
                    "additionalProperties": True,
                    "properties": {
                        "name": non_empty_string,
                        "flavorRef": flavorref,
                        "volume": volume,
                        "nics": nics,
                        "availability_zone": non_empty_string,
                        "related_to": non_empty_string,
                        "type": non_empty_string
                    }
                }
            }
        }
    },
    "shrink": {
        "type": "object",
        "required": ["shrink"],
        "additionalProperties": True,
        "properties": {
            "shrink": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["id"],
                    "additionalProperties": True,
                    "properties": {
                        "id": uuid
                    }
                }
            }
        }
    }
}

instance = {
    "create": {
        "type": "object",
        "required": ["instance"],
        "additionalProperties": True,
        "properties": {
            "instance": {
                "type": "object",
                "required": ["name", "flavorRef"],
                "additionalProperties": True,
                "properties": {
                    "name": non_empty_string,
                    "configuration_id": configuration_id,
                    "flavorRef": flavorref,
                    "volume": volume,
                    "databases": databases_def,
                    "users": users_list,
                    "restorePoint": {
                        "type": "object",
                        "required": ["backupRef"],
                        "additionalProperties": True,
                        "properties": {
                            "backupRef": uuid
                        }
                    },
                    "availability_zone": non_empty_string,
                    "datastore": {
                        "type": "object",
                        "additionalProperties": True,
                        "properties": {
                            "type": non_empty_string,
                            "version": non_empty_string
                        }
                    },
                    "nics": nics,
                    "modules": module_list,
                    "locality": non_empty_string
                }
            }
        }
    },
    "edit": {
        "name": "instance:edit",
        "type": "object",
        "required": ["instance"],
        "properties": {
            "instance": {
                "type": "object",
                "required": [],
                "additionalProperties": False,
                "properties": {
                    "slave_of": {},
                    "replica_of": {},
                    "name": non_empty_string,
                    "configuration": configuration_id,
                }
            }
        }
    },
    "action": {
        "resize": {
            "volume": {
                "type": "object",
                "required": ["resize"],
                "additionalProperties": True,
                "properties": {
                    "resize": {
                        "type": "object",
                        "required": ["volume"],
                        "additionalProperties": True,
                        "properties": {
                            "volume": volume
                        }
                    }
                }
            },
            'flavorRef': {
                "type": "object",
                "required": ["resize"],
                "additionalProperties": True,
                "properties": {
                    "resize": {
                        "type": "object",
                        "required": ["flavorRef"],
                        "additionalProperties": True,
                        "properties": {
                            "flavorRef": flavorref
                        }
                    }
                }
            }
        },
        "restart": {
            "type": "object",
            "required": ["restart"],
            "additionalProperties": True,
            "properties": {
                "restart": {
                    "type": "object"
                }
            }
        }
    }
}

mgmt_cluster = {
    "action": {
        'reset-task': {
            "type": "object",
            "required": ["reset-task"],
            "additionalProperties": True,
            "properties": {
                "reset-task": {
                    "type": "object"
                }
            }
        }
    }
}

mgmt_instance = {
    "action": {
        'migrate': {
            "type": "object",
            "required": ["migrate"],
            "additionalProperties": True,
            "properties": {
                "migrate": {
                    "type": "object"
                }
            }
        },
        "reboot": {
            "type": "object",
            "required": ["reboot"],
            "additionalProperties": True,
            "properties": {
                "reboot": {
                    "type": "object"
                }
            }
        },
        "stop": {
            "type": "object",
            "required": ["stop"],
            "additionalProperties": True,
            "properties": {
                "stop": {
                    "type": "object"
                }
            }
        }
    }
}

user = {
    "create": {
        "name": "users:create",
        "type": "object",
        "required": ["users"],
        "properties": {
            "users": users_list
        }
    },
    "update_all": {
        "users": {
            "type": "object",
            "required": ["users"],
            "additionalProperties": True,
            "properties": {
                "users": users_list
            }
        },
        "databases": databases_ref
    },
    "update": {
        "type": "object",
        "required": ["user"],
        "additionalProperties": True,
        "properties": {
            "user": user_attributes
        }
    }
}

dbschema = {
    "create": {
        "type": "object",
        "required": ["databases"],
        "additionalProperties": True,
        "properties": {
            "databases": databases_def
        }
    }
}

backup = {
    "create": {
        "name": "backup:create",
        "type": "object",
        "required": ["backup"],
        "properties": {
            "backup": {
                "type": "object",
                "required": ["instance", "name"],
                "properties": {
                    "description": non_empty_string,
                    "instance": uuid,
                    "name": non_empty_string,
                    "parent_id": uuid
                }
            }
        }
    }
}

guest_log = {
    "action": {
        "name": "guest_log:action",
        "type": "object",
        "required": ["name"],
        "properties": {
            "name": non_empty_string,
            "enable": boolean_string,
            "disable": boolean_string,
            "publish": boolean_string,
            "discard": boolean_string
        }
    }
}

module_contents = {
    "type": "string",
    "minLength": 1,
    "maxLength": 16777215,
    "pattern": "^.*.+.*$"
}

module = {
    "create": {
        "name": "module:create",
        "type": "object",
        "required": ["module"],
        "properties": {
            "module": {
                "type": "object",
                "required": ["name", "module_type", "contents"],
                "additionalProperties": True,
                "properties": {
                    "name": non_empty_string,
                    "module_type": non_empty_string,
                    "contents": module_contents,
                    "description": non_empty_string,
                    "datastore": {
                        "type": "object",
                        "properties": {
                            "type": non_empty_string,
                            "version": non_empty_string
                        }
                    },
                    "auto_apply": boolean_string,
                    "all_tenants": boolean_string,
                    "visible": boolean_string,
                    "live_update": boolean_string,
                }
            }
        }
    },
    "update": {
        "name": "module:update",
        "type": "object",
        "required": ["module"],
        "properties": {
            "module": {
                "type": "object",
                "required": [],
                "additionalProperties": True,
                "properties": {
                    "name": non_empty_string,
                    "type": non_empty_string,
                    "contents": module_contents,
                    "description": non_empty_string,
                    "datastore": {
                        "type": "object",
                        "additionalProperties": True,
                        "properties": {
                            "type": non_empty_string,
                            "version": non_empty_string
                        }
                    },
                    "auto_apply": boolean_string,
                    "all_tenants": boolean_string,
                    "all_datastores": boolean_string,
                    "all_datastore_versions": boolean_string,
                    "visible": boolean_string,
                    "live_update": boolean_string,
                }
            }
        }
    },
    "apply": {
        "name": "module:apply",
        "type": "object",
        "required": ["modules"],
        "properties": {
            "modules": module_list,
        }
    },
    "list": {
        "name": "module:list",
        "type": "object",
        "required": [],
        "properties": {
            "module": uuid,
            "from_guest": boolean_string,
            "include_contents": boolean_string
        }
    },
}

configuration = {
    "create": {
        "name": "configuration:create",
        "type": "object",
        "required": ["configuration"],
        "properties": {
            "configuration": {
                "type": "object",
                "required": ["values", "name"],
                "properties": {
                    "description": non_empty_string,
                    "values": {
                        "type": "object",
                    },
                    "name": non_empty_string,
                    "datastore": {
                        "type": "object",
                        "additionalProperties": True,
                        "properties": {
                            "type": non_empty_string,
                            "version": non_empty_string
                        }
                    }
                }
            }
        }
    },
    "update": {
        "name": "configuration:update",
        "type": "object",
        "required": ["configuration"],
        "properties": {
            "configuration": {
                "type": "object",
                "required": [],
                "properties": {
                    "description": non_empty_string,
                    "values": {
                        "type": "object",
                    },
                    "name": non_empty_string
                }
            }
        }
    },
    "edit": {
        "name": "configuration:edit",
        "type": "object",
        "required": ["configuration"],
        "properties": {
            "configuration": {
                "type": "object",
                "required": [],
                "properties": {
                    "values": {
                        "type": "object",
                    }
                }
            }
        }
    }
}

mgmt_configuration = {
    "create": {
        "name": "configuration_parameter:create",
        "type": "object",
        "required": ["configuration-parameter"],
        "properties": {
            "configuration-parameter": {
                "type": "object",
                "required": ["name", "restart_required", "data_type"],
                "properties": {
                    "name": configuration_non_empty_string,
                    "data_type": configuration_data_types,
                    "restart_required": boolean_string,
                    "max": configuration_integer_size,
                    "min": configuration_integer_size,
                }
            }
        }
    },
    "update": {
        "name": "configuration_parameter:update",
        "type": "object",
        "required": ["configuration-parameter"],
        "properties": {
            "configuration-parameter": {
                "type": "object",
                "required": ["name", "restart_required", "data_type"],
                "properties": {
                    "name": configuration_non_empty_string,
                    "data_type": configuration_data_types,
                    "restart_required": boolean_string,
                    "max": configuration_integer_size,
                    "min": configuration_integer_size,
                }
            }
        }
    },
}

account = {
    'create': {
        "type": "object",
        "name": "users",
        "required": ["users"],
        "additionalProperties": True,
        "properties": {
            "users": users_list
        }
    }
}

upgrade = {
    "create": {
        "type": "object",
        "required": ["upgrade"],
        "additionalProperties": True,
        "properties": {
            "upgrade": {
                "type": "object",
                "required": [],
                "additionalProperties": True,
                "properties": {
                    "instance_version": non_empty_string,
                    "location": non_empty_string,
                    "metadata": {}
                }
            }
        }
    }
}


package_list = {
    "type": "array",
    "minItems": 0,
    "uniqueItems": True,
    "items": {
        "type": "string",
        "minLength": 1,
        "maxLength": 255,
        "pattern": "^.*[0-9a-zA-Z]+.*$"
    }
}

mgmt_datastore_version = {
    "create": {
        "name": "mgmt_datastore_version:create",
        "type": "object",
        "required": ["version"],
        "properties": {
            "version": {
                "type": "object",
                "required": ["name", "datastore_name", "image", "active"],
                "additionalProperties": True,
                "properties": {
                    "name": non_empty_string,
                    "datastore_name": non_empty_string,
                    "datastore_manager": non_empty_string,
                    "packages": package_list,
                    "image": uuid,
                    "active": {"enum": [True, False]},
                    "default": {"enum": [True, False]}
                }
            }
        }
    },
    "edit": {
        "name": "mgmt_datastore_version:edit",
        "type": "object",
        "required": [],
        "additionalProperties": True,
        "properties": {
            "datastore_manager": non_empty_string,
            "packages": package_list,
            "image": uuid,
            "active": {"enum": [True, False]},
            "default": {"enum": [True, False]},
        }
    }
}

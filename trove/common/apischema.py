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

flavorref = {
    'oneOf': [
        url_ref,
        {
            "type": "string",
            "maxLength": 5,
            "pattern": "[0-9]+"
        },
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
        {
            "type": "string",
            "minLength": 1,
            "pattern": "[0-9]+"
        }]
}

non_empty_string = {
    "type": "string",
    "minLength": 1,
    "maxLength": 255,
    "pattern": "^.*[0-9a-zA-Z]+.*$"
}

host_string = {
    "type": "string",
    "minLength": 1,
    "pattern": "^[%]?[\w(-).]*[%]?$"
}

name_string = {
    "type": "string",
    "minLength": 1,
    "maxLength": 16,
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

configuration_id = {
    'oneOf': [
        uuid
    ]
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
                                "volume": volume
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
                    "nics": nics
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
                "properties": {
                    "slave_of": {},
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

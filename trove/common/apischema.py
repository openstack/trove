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

flavorref = {
    'oneOf': [
        {
            "type": "string",
            "minLength": 8,
            "pattern": 'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]'
                       '|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        },
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
    "minLength": 0,
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


databases_ref_list = {
    "type": "array",
    "minItems": 0,
    "uniqueItems": True,
    "items": {
        "type": "object",
        "required": ["name"],
        "additionalProperties": False,
        "properties": {
            "name": non_empty_string
        }
    }
}

databases_ref_list_required = {
    "type": "array",
    "minItems": 1,
    "uniqueItems": True,
    "items": {
        "type": "object",
        "required": ["name"],
        "additionalProperties": False,
        "properties": {
            "name": non_empty_string
        }
    }
}

databases_ref = {
    "type": "object",
    "required": ["databases"],
    "additionalProperties": False,
    "properties": {
        "databases": databases_ref_list_required
    }
}

databases_def = {
    "type": "array",
    "minItems": 1,
    "items": {
        "type": "object",
        "required": ["name"],
        "additionalProperties": False,
        "properties": {
            "name": non_empty_string,
            "character_set": non_empty_string,
            "collate": non_empty_string
        }
    }
}

user_attributes = {
    "type": "object",
    "additionalProperties": False,
    "minProperties": 1,
    "properties": {
        "name": name_string,
        "password": non_empty_string,
        "host": host_string
    }
}


users_list = {
    "type": "array",
    "minItems": 1,
    "items": {
        "type": "object",
        "required": ["name", "password"],
        "additionalProperties": False,
        "properties": {
            "name": name_string,
            "password": non_empty_string,
            "host": host_string,
            "databases": databases_ref_list
        }
    }
}

instance = {
    "create": {
        "type": "object",
        "required": ["instance"],
        "additionalProperties": False,
        "properties": {
            "instance": {
                "type": "object",
                "required": ["name", "flavorRef",
                             "volume" if CONF.trove_volume_support else None],
                "additionalProperties": True,
                "properties": {
                    "name": non_empty_string,
                    "flavorRef": flavorref,
                    "volume": volume,
                    "databases": databases_def,
                    "users": users_list,
                    "restorePoint": {
                        "type": "object",
                        "required": ["backupRef"],
                        "additionalProperties": False,
                        "properties": {
                            "backupRef": uuid
                        }
                    },
                    "availability_zone": non_empty_string
                }
            }
        }
    },
    "action": {
        "resize": {
            "volume": {
                "type": "object",
                "required": ["resize"],
                "additionalProperties": False,
                "properties": {
                    "resize": {
                        "type": "object",
                        "required": ["volume"],
                        "additionalProperties": False,
                        "properties": {
                            "volume": volume
                        }
                    }
                }
            },
            'flavorRef': {
                "type": "object",
                "required": ["resize"],
                "additionalProperties": False,
                "properties": {
                    "resize": {
                        "type": "object",
                        "required": ["flavorRef"],
                        "additionalProperties": False,
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
            "additionalProperties": False,
            "properties": {
                "restart": {
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
            "additionalProperties": False,
            "properties": {
                "migrate": {
                    "type": "object"
                }
            }
        },
        "reboot": {
            "type": "object",
            "required": ["reboot"],
            "additionalProperties": False,
            "properties": {
                "reboot": {
                    "type": "object"
                }
            }
        },
        "stop": {
            "type": "object",
            "required": ["stop"],
            "additionalProperties": False,
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
            "additionalProperties": False,
            "properties": {
                "users": users_list
            }
        },
        "databases": databases_ref
    },
    "update": {
        "type": "object",
        "required": ["user"],
        "additionalProperties": False,
        "properties": {
            "user": user_attributes
        }
    }
}

dbschema = {
    "create": {
        "type": "object",
        "required": ["databases"],
        "additionalProperties": False,
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
                    "name": non_empty_string
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
        "additionalProperties": False,
        "properties": {
            "users": users_list
        }
    }
}

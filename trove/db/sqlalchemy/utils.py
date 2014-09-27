# Copyright 2014 Tesora Inc.
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

from migrate.changeset.constraint import ForeignKeyConstraint
from sqlalchemy.engine import reflection


def get_foreign_key_constraint_names(engine, table, columns,
                                     ref_table, ref_columns):
    """Retrieve the names of foreign key constraints that match
    the given criteria.
    :param engine: The sqlalchemy engine to be used.
    :param table: Name of the child table.
    :param columns: List of the foreign key columns.
    :param ref_table: Name of the parent table.
    :param ref_columns: List of the referenced columns.
    :return: List of foreign key constraint names.
    """
    constraint_names = []
    inspector = reflection.Inspector.from_engine(engine)
    fks = inspector.get_foreign_keys(table)
    for fk in fks:
        if (fk['referred_table'] == ref_table
                and fk['constrained_columns'] == columns
                and fk['referred_columns'] == ref_columns):
            constraint_names.append(fk['name'])
    return constraint_names


def drop_foreign_key_constraints(constraint_names, columns,
                                 ref_columns):
    """Drop the foreign key constraints that match the given
    criteria.
    :param constraint_names: List of foreign key constraint names
    :param columns: List of the foreign key columns.
    :param ref_columns: List of the referenced columns.
    """
    for constraint_name in constraint_names:
        fkey_constraint = ForeignKeyConstraint(columns=columns,
                                               refcolumns=ref_columns,
                                               name=constraint_name)
        fkey_constraint.drop()

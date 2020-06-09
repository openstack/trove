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
#
from unittest.mock import call
from unittest.mock import Mock
from unittest.mock import patch
from sqlalchemy.engine import reflection
from sqlalchemy.schema import Column

from trove.db.sqlalchemy.migrate_repo.schema import String
from trove.db.sqlalchemy import utils as db_utils
from trove.tests.unittests import trove_testtools


class TestDbMigrationUtils(trove_testtools.TestCase):
    def setUp(self):
        super(TestDbMigrationUtils, self).setUp()

    def tearDown(self):
        super(TestDbMigrationUtils, self).tearDown()

    @patch.object(reflection.Inspector, 'from_engine')
    def test_get_foreign_key_constraint_names_single_match(self,
                                                           mock_inspector):
        mock_engine = Mock()
        (mock_inspector.return_value.
         get_foreign_keys.return_value) = [{'constrained_columns': ['col1'],
                                            'referred_table': 'ref_table1',
                                            'referred_columns': ['ref_col1'],
                                            'name': 'constraint1'},
                                           {'constrained_columns': ['col2'],
                                            'referred_table': 'ref_table2',
                                            'referred_columns': ['ref_col2'],
                                            'name': 'constraint2'}]
        ret_val = db_utils.get_foreign_key_constraint_names(mock_engine,
                                                            'table1',
                                                            ['col1'],
                                                            'ref_table1',
                                                            ['ref_col1'])
        self.assertEqual(['constraint1'], ret_val)

    @patch.object(reflection.Inspector, 'from_engine')
    def test_get_foreign_key_constraint_names_multi_match(self,
                                                          mock_inspector):
        mock_engine = Mock()
        (mock_inspector.return_value.
         get_foreign_keys.return_value) = [
             {'constrained_columns': ['col1'],
              'referred_table': 'ref_table1',
              'referred_columns': ['ref_col1'],
              'name': 'constraint1'},
             {'constrained_columns': ['col2', 'col3'],
              'referred_table': 'ref_table1',
              'referred_columns': ['ref_col2', 'ref_col3'],
              'name': 'constraint2'},
             {'constrained_columns': ['col2', 'col3'],
              'referred_table': 'ref_table1',
              'referred_columns': ['ref_col2', 'ref_col3'],
              'name': 'constraint3'},
             {'constrained_columns': ['col4'],
              'referred_table': 'ref_table2',
              'referred_columns': ['ref_col4'],
              'name': 'constraint4'}]
        ret_val = db_utils.get_foreign_key_constraint_names(
            mock_engine, 'table1', ['col2', 'col3'],
            'ref_table1', ['ref_col2', 'ref_col3'])
        self.assertEqual(['constraint2', 'constraint3'], ret_val)

    @patch.object(reflection.Inspector, 'from_engine')
    def test_get_foreign_key_constraint_names_no_match(self, mock_inspector):
        mock_engine = Mock()
        (mock_inspector.return_value.
         get_foreign_keys.return_value) = []
        ret_val = db_utils.get_foreign_key_constraint_names(mock_engine,
                                                            'table1',
                                                            ['col1'],
                                                            'ref_table1',
                                                            ['ref_col1'])
        self.assertEqual([], ret_val)

    @patch('trove.db.sqlalchemy.utils.ForeignKeyConstraint')
    def test_drop_foreign_key_constraints(self, mock_constraint):
        test_columns = [Column('col1', String(5)),
                        Column('col2', String(5))]
        test_refcolumns = [Column('ref_col1', String(5)),
                           Column('ref_col2', String(5))]
        test_constraint_names = ['constraint1', 'constraint2']
        db_utils.drop_foreign_key_constraints(test_constraint_names,
                                              test_columns,
                                              test_refcolumns)
        expected = [call(columns=test_columns,
                         refcolumns=test_refcolumns,
                         name='constraint1'),
                    call(columns=test_columns,
                         refcolumns=test_refcolumns,
                         name='constraint2')]
        self.assertEqual(expected, mock_constraint.call_args_list)

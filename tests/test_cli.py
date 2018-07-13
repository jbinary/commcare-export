# -*- coding: utf-8 -*-
import csv
import os
import unittest
from argparse import Namespace
from collections import namedtuple
from copy import copy
from itertools import izip_longest

import pytest
import sqlalchemy
from mock import mock

from commcare_export.checkpoint import CheckpointManager
from commcare_export.cli import CLI_ARGS, main_with_args
from commcare_export.commcare_hq_client import MockCommCareHqClient
from commcare_export.writers import JValueTableWriter, SqlTableWriter

CLI_ARGS_BY_NAME = {
    arg.name: arg
    for arg in CLI_ARGS
}


def make_args(project='test', username='test', password='test', **kwargs):
    kwargs['project'] = project
    kwargs['username'] = username
    kwargs['password'] = password

    args_by_name = copy(CLI_ARGS_BY_NAME)
    namespace = Namespace()
    for name, val in kwargs.items():
        args_by_name.pop(name)
        setattr(namespace, name, val)

    for name, arg in args_by_name.items():
        setattr(namespace, name, arg.default)

    return namespace

client = MockCommCareHqClient({
    'form': [
        (
            {'limit': 1000, 'order_by': ['server_modified_on', 'received_on']},
            [
                {'id': 1, 'form': {'name': 'f1', 'case': {'@case_id': 'c1'}}},
                {'id': 2, 'form': {'name': 'f2', 'case': {'@case_id': 'c2'}}},
            ]
        ),
    ],
    'case': [
        (
            {'limit': 1000, 'order_by': 'server_date_modified'},
            [
                {'id': 'case1'},
                {'id': 'case2'},
            ]
        )
    ]
})


class TestCli(unittest.TestCase):

    @mock.patch('commcare_export.cli._get_api_client', return_value=client)
    def test_cli(self, mock_client):
        args = make_args(
            query='tests/008_multiple-tables.xlsx',
            output_format='json',
        )
        writer = JValueTableWriter()
        with mock.patch('commcare_export.cli._get_writer', return_value=writer):
            main_with_args(args)

        expected = [
            {
                "name": "Forms",
                "headings": ["id", "name"],
                "rows": [
                    ["1", "f1"],
                    ["2", "f2"]
                ],
            },
            {
                "name": "Other cases",
                "headings": ["id"],
                "rows": [
                    ["case1"],
                    ["case2"]
                ],
            },
            {
                "name": "Cases",
                "headings": ["case_id"],
                "rows": [
                    ["c1"],
                    ["c2"]
                ],
            }
        ]

        assert writer.tables.values() == expected


@pytest.fixture(scope='class')
def writer(pg_db_params):
    return SqlTableWriter(pg_db_params['url'], poolclass=sqlalchemy.pool.NullPool)


@pytest.fixture(scope='class')
def checkpoint_manager(pg_db_params):
    return CheckpointManager(pg_db_params['url'], 'query', '123', poolclass=sqlalchemy.pool.NullPool)


class TestCLIIntegrationTests(object):
    def test_write_to_sql_with_checkpoints(self, writer, checkpoint_manager):
        def _pull_data(since, until):
            args = make_args(
                query='tests/009_integration.xlsx',
                output_format='sql',
                output='',
                username=os.environ['HQ_USERNAME'],
                password=os.environ['HQ_API_KEY'],
                auth_mode='apikey',
                project='corpora',
                batch_size=10,
                since=since,
                until=until
            )

            # have to mock these to override the pool class otherwise they hold the db connection open
            writer_patch = mock.patch('commcare_export.cli._get_writer', return_value=writer)
            checkpoint_patch = mock.patch('commcare_export.cli._get_checkpoint_manager', return_value=checkpoint_manager)
            with writer_patch, checkpoint_patch:
                main_with_args(args)

        with open('tests/009_expected_form_data.csv', 'r') as f:
            reader = csv.reader(f)
            expected_form_data = list(reader)[1:]

        _pull_data('2012-01-01', '2012-08-01')

        expected_first_pull = expected_form_data[:16]
        self._check_data(writer, expected_first_pull)

    def _check_data(self, writer, expected):
        actual = [
            list(row) for row in
            writer.engine.execute("SELECT id, name, received_on, server_modified_on FROM forms")
        ]

        if actual != expected:
            print('Data not equal to expected:')
            if len(actual) != len(expected):
                print('    {} rows compared to {} expected'.format(len(actual), len(expected)))
            print('Diff:')
            for i, rows in enumerate(izip_longest(actual, expected)):
                if rows[0] != rows[1]:
                    print('{}: {} != {}'.format(i, rows[0], rows[1]))

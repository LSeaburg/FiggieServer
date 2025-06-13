import sys
import os
import importlib
import unittest
from unittest.mock import patch

class TestConfig(unittest.TestCase):
    @patch.dict(os.environ, {'NUM_PLAYERS': '3'})
    def test_invalid_num_players(self):
        # Import with invalid NUM_PLAYERS should raise
        sys.modules.pop('figgie_server.game', None)
        with self.assertRaises(RuntimeError):
            importlib.import_module('figgie_server.game')

        # Restore to valid setting and ensure import succeeds
        with patch.dict(os.environ, {'NUM_PLAYERS': '4'}):
            sys.modules.pop('figgie_server.game', None)
            importlib.import_module('figgie_server.game')
import threading
import unittest

from utils.plc_client import PLCClient


class PLCAsyncQueueTests(unittest.TestCase):
    def test_submit_preserves_command_order(self):
        client = PLCClient()
        values = []
        done = threading.Event()

        def append(value):
            values.append(value)
            if len(values) == 4:
                done.set()

        for value in range(4):
            client.submit(append, value)
        self.assertTrue(done.wait(1.0))
        self.assertEqual(values, [0, 1, 2, 3])


if __name__ == "__main__":
    unittest.main()

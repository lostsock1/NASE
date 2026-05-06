import unittest

from util.rate_limiter import TokenBucket


class TokenBucketTests(unittest.TestCase):
    def test_long_retry_after_opens_circuit_flag(self):
        bucket = TokenBucket(1, 1)
        bucket.handle_429(600)

        status = bucket.status
        self.assertTrue(status["rate_limited"])
        self.assertTrue(status["circuit_open"])

    def test_zero_retry_after_uses_exponential_backoff(self):
        bucket = TokenBucket(1, 1)
        bucket.handle_429(0)

        status = bucket.status
        self.assertTrue(status["rate_limited"])
        self.assertFalse(status["circuit_open"])
        self.assertGreaterEqual(status["time_until_next"], 5.0)
        self.assertEqual(status["current_delay"], 6.0)

    def test_success_resets_retry_after_zero_backoff(self):
        bucket = TokenBucket(0.5, 1)
        bucket.handle_429(0)
        bucket.handle_success()

        status = bucket.status
        self.assertFalse(status["rate_limited"])
        self.assertEqual(status["consecutive_429s"], 0)
        self.assertEqual(status["current_delay"], 2.0)


if __name__ == "__main__":
    unittest.main()

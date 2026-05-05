import unittest

from util.rate_limiter import TokenBucket


class TokenBucketTests(unittest.TestCase):
    def test_long_retry_after_opens_circuit_flag(self):
        bucket = TokenBucket(1, 1)
        bucket.handle_429(600)

        status = bucket.status
        self.assertTrue(status["rate_limited"])
        self.assertTrue(status["circuit_open"])


if __name__ == "__main__":
    unittest.main()

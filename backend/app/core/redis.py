class RedisClient:
    def get(self, _key):
        return None

    def set(self, _key, _value, ex=None):
        return True


redis_client = RedisClient()

"""Token-bucket rate limiter implemented as a Lua script so the
read-refill-consume-write cycle is ONE atomic Redis operation. That makes it
correct with many API workers hitting the same bucket concurrently."""
import time
from dataclasses import dataclass

TOKEN_BUCKET_LUA = """
local key      = KEYS[1]
local rate     = tonumber(ARGV[1])   -- tokens added per second
local capacity = tonumber(ARGV[2])   -- bucket size (burst)
local now      = tonumber(ARGV[3])   -- client time in ms
local cost     = tonumber(ARGV[4])

local data   = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts     = tonumber(data[2])
if tokens == nil then
  tokens = capacity
  ts = now
end

local elapsed = math.max(0, now - ts)
tokens = math.min(capacity, tokens + elapsed * rate / 1000)

local allowed = 0
local retry_ms = 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
else
  retry_ms = math.ceil((cost - tokens) / rate * 1000)
end

redis.call('HSET', key, 'tokens', tostring(tokens), 'ts', tostring(now))
redis.call('PEXPIRE', key, math.ceil(capacity / rate * 1000) * 2)
return {allowed, tostring(tokens), retry_ms}
"""


@dataclass
class RateResult:
    allowed: bool
    remaining: int
    limit: int
    retry_after_s: int


class TokenBucketLimiter:
    def __init__(self, client):
        self.client = client
        self._script = client.register_script(TOKEN_BUCKET_LUA)

    def check(self, bucket_id: str, rate_per_sec: float, burst: int, cost: int = 1, now_ms: int | None = None) -> RateResult:
        now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
        allowed, tokens, retry_ms = self._script(
            keys=[f"rl:{bucket_id}"], args=[rate_per_sec, burst, now_ms, cost]
        )
        return RateResult(
            allowed=bool(int(allowed)),
            remaining=int(float(tokens)),
            limit=burst,
            retry_after_s=max(1, -(-int(retry_ms) // 1000)) if not int(allowed) else 0,
        )

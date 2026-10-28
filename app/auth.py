"""Password hashing (scrypt, standard library) and a simple failed-login limiter."""
import hashlib, hmac, re, secrets, threading, time

N, R, P = 2**14, 8, 1
USERNAME = re.compile(r'^[A-Za-z0-9_.-]{2,32}$')
MIN_PASSWORD = 10

def valid_username(name):
 return bool(USERNAME.match(name))

def hash_password(password):
 salt = secrets.token_bytes(16)
 digest = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, dklen=32)
 return f'scrypt${N}${R}${P}${salt.hex()}${digest.hex()}'

def verify_password(password, stored):
 try:
  _, n, r, p, salt, digest = stored.split('$')
  candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32)
 except (ValueError, TypeError):
  return False
 return hmac.compare_digest(candidate.hex(), digest)

# Used when a username does not exist, so unknown users cost the same time as wrong passwords.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))

class LoginLimiter:
 """Blocks a key after `max_failures` failed attempts within `window` seconds. In memory, so it resets on restart."""
 def __init__(self, max_failures=5, window=900, clock=time.monotonic):
  self.max_failures, self.window, self.clock = max_failures, window, clock
  self.failures = {}
  self.lock = threading.Lock()

 def _recent(self, key):
  now = self.clock()
  recent = [t for t in self.failures.get(key, []) if now - t < self.window]
  self.failures[key] = recent
  return recent

 def blocked(self, key):
  with self.lock:
   return len(self._recent(key)) >= self.max_failures

 def record_failure(self, key):
  with self.lock:
   self._recent(key).append(self.clock())

 def reset(self, key):
  with self.lock:
   self.failures.pop(key, None)

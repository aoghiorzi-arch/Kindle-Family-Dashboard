"""Setup commands for the Family Hub database. Run from the repo root.

  python3 -m app.manage add-user USERNAME [--admin]   # first user in a household is always an admin
  python3 -m app.manage seed-demo                     # fills an empty household with sample items
  python3 -m app.manage set-location LAT LON TIMEZONE # e.g. 51.5074 -0.1278 Europe/London
  python3 -m app.manage refresh-feeds                 # manual refresh; do not also schedule alongside the built-in worker
  python3 -m app.manage backup NEW_DIRECTORY          # snapshot; preserve key separately
  python3 -m app.manage restore BACKUP_DB NEW_DIRECTORY # requires matching KFD_KEY_FILE
  python3 -m app.manage init-db                       # initialize/migrate offline; preserve the matching key file
"""
from pathlib import Path
import getpass, json, sys
from . import store, auth, validate, feeds, secrets as storage_secrets
import time

def open_db():
 try:
  store.init_db(store.default_db_path())
 except storage_secrets.StorageError as exc:
  sys.exit(str(exc))
 return store.connect(store.default_db_path())

def add_user(username, admin=False):
 try:
  validate.clean_username(username)
 except ValueError as exc:
  sys.exit(str(exc))
 password = getpass.getpass('Password (at least 10 characters): ')
 try:
  validate.clean_password(password)
 except ValueError as exc:
  sys.exit(str(exc))
 if getpass.getpass('Repeat password: ') != password:
  sys.exit('Passwords do not match')
 conn = open_db()
 try:
  household = store.first_household_id(conn)
  if household is None:
   household = store.create_household(conn, 'Family')
   role = 'admin'  # the first member of a household runs its settings
  else:
   role = 'admin' if admin else 'member'
  store.create_user(conn, household, username, auth.hash_password(password), role)
 except ValueError as exc:
  sys.exit(str(exc))
 finally:
  conn.close()
 print(f'Added {username} as {role}.')

def seed_demo():
 conn = open_db()
 try:
  household = store.first_household_id(conn)
  if household is None: sys.exit('Add a user first: python3 -m app.manage add-user USERNAME')
  if store.list_shopping(conn, household) or store.list_events(conn, household):
   sys.exit('Household already has items; not seeding.')
  fixture = json.loads((Path(__file__).resolve().parent/'seed.json').read_text())
  for item in fixture['shopping']: store.add_shopping(conn, household, None, item['title'])
  for event in fixture['events']: store.add_event(conn, household, None, event['title'], event['time'], event['private'])
 finally:
  conn.close()
 print('Sample shopping and events added.')

def refresh_feeds():
 conn = open_db()
 try:
  household = store.first_household_id(conn)
  if household is None: sys.exit('Add a user first: python3 -m app.manage add-user USERNAME')
  location = store.get_location(conn, household)
  if location is None: sys.exit('Set the location first: python3 -m app.manage set-location LAT LON TIMEZONE')
  for feed in store.list_feeds(conn, household):
   ok, error = feeds.refresh(conn, household, store.get_feed(conn, household, feed['id']),
    feeds.fetch_https, location['tz'], int(time.time()))
   print(f"{feed['label']}: " + ('updated' if ok else f'failed ({error})'))
 finally:
  conn.close()

def set_location(lat, lon, tz):
 try:
  lat, lon, tz = validate.clean_location(lat, lon, tz)
 except ValueError as exc:
  sys.exit(str(exc))
 conn = open_db()
 try:
  household = store.first_household_id(conn)
  if household is None: sys.exit('Add a user first: python3 -m app.manage add-user USERNAME')
  store.set_location(conn, household, lat, lon, tz)
 finally:
  conn.close()
 print(f'Location set to {lat}, {lon} ({tz}).')

if __name__ == '__main__':
 args = sys.argv[1:]
 if args[:1] == ['add-user'] and len(args) in (2, 3) and args[2:] in ([], ['--admin']):
  add_user(args[1], admin=len(args) == 3)
 elif args[:1] in (['backup'], ['restore']):
  from . import backup
  try:
   if args[0] == 'backup' and len(args) == 2:
    result = backup.backup(store.default_db_path(), args[1])
   elif args[0] == 'restore' and len(args) == 3:
    result = backup.restore(args[1], args[2])
   else: sys.exit(__doc__)
  except (OSError, ValueError, storage_secrets.StorageError) as exc:
   sys.exit(str(exc))
  print(f'Database saved: {result}. Preserve the matching key separately.')
 elif args == ['seed-demo']:
  seed_demo()
 elif args == ['refresh-feeds']:
  refresh_feeds()
 elif args == ['init-db']:
  open_db().close()
  print('Database initialized; calendar storage encrypted. Preserve the separate key file.')
 elif args[:1] == ['set-location'] and len(args) == 4:
  set_location(*args[1:4])
 else:
  sys.exit(__doc__)

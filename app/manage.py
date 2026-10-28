"""Setup commands for the Family Hub database. Run from the repo root.

  python3 -m app.manage add-user USERNAME   # creates the household on first use
  python3 -m app.manage seed-demo           # fills an empty household with the sample items
"""
from pathlib import Path
import getpass, json, sys
from . import store, auth

def add_user(username):
 if not auth.valid_username(username):
  sys.exit('Usernames are 2–32 characters: letters, digits, _ . or -')
 password = getpass.getpass('Password (at least 10 characters): ')
 if len(password) < auth.MIN_PASSWORD:
  sys.exit('Password is too short')
 if getpass.getpass('Repeat password: ') != password:
  sys.exit('Passwords do not match')
 store.init_db(store.default_db_path())
 conn = store.connect(store.default_db_path())
 try:
  household = store.first_household_id(conn) or store.create_household(conn, 'Family')
  store.create_user(conn, household, username, auth.hash_password(password))
 except ValueError as exc:
  sys.exit(str(exc))
 finally:
  conn.close()
 print(f'Added {username}.')

def seed_demo():
 store.init_db(store.default_db_path())
 conn = store.connect(store.default_db_path())
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

if __name__ == '__main__':
 commands = {'add-user': lambda: add_user(sys.argv[2]) if len(sys.argv) == 3 else sys.exit(__doc__),
             'seed-demo': seed_demo}
 if len(sys.argv) < 2 or sys.argv[1] not in commands: sys.exit(__doc__)
 commands[sys.argv[1]]()

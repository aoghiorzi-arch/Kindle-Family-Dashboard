"""python3 -m display_client CONFIG.json [--once]"""
import sys
from . import client

def main(argv):
    if not argv or argv[0].startswith('-') or argv[1:] not in ([], ['--once']):
        sys.exit(__doc__)
    try:
        cfg = client.load_config(argv[0])
        if argv[1:] == ['--once']:
            print(client.check_once(cfg, client.Cache(cfg['cache_dir'])))
        else:
            client.run(cfg)
    except (client.ClientError, OSError, ValueError) as exc:
        sys.exit(f'display client: {exc}')
    except KeyboardInterrupt:
        pass

main(sys.argv[1:])

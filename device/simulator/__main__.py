"""Usage: python3 -m device.simulator SNAPSHOT.json OUT.png"""
import sys

from device.simulator.snapshot_view import load_snapshot, save_preview

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    print(save_preview(load_snapshot(sys.argv[1]), sys.argv[2]))

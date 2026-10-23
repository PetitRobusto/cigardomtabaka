"""Read-only SQLite deployment gate. Never repair or delete business records."""

import argparse
from pathlib import Path
import sqlite3
import sys


def check_database(path):
    # mode=ro refuses missing files and includes committed WAL contents.
    connection = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True, timeout=5)
    try:
        violations = connection.execute('PRAGMA foreign_key_check').fetchall()
        if violations:
            raise ValueError(f'{len(violations)} foreign-key violations; deployment stopped, no records changed')
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database', type=Path)
    args = parser.parse_args()
    try:
        check_database(args.database)
    except (OSError, sqlite3.Error, ValueError) as error:
        print(f'Database preflight failed: {error}', file=sys.stderr)
        return 1
    print('Read-only foreign-key check passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

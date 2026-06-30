from __future__ import annotations
from pathlib import Path
import argparse, json, sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config_backend import create_api_token, create_user, init_sqlite

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Manage local users and API tokens in the v10 SQLite backend')
    sub = ap.add_subparsers(dest='cmd', required=True)
    u = sub.add_parser('user')
    u.add_argument('--user-id', required=True)
    u.add_argument('--email', required=True)
    u.add_argument('--role', default='advisor', choices=['admin','advisor','analyst','viewer'])
    u.add_argument('--workspace', default='local')
    u.add_argument('--display-name', default='')
    t = sub.add_parser('token')
    t.add_argument('--user-id', required=True)
    t.add_argument('--role', default='advisor', choices=['admin','advisor','analyst','viewer'])
    t.add_argument('--workspace', default='local')
    t.add_argument('--name', default='api')
    args = ap.parse_args()
    db = init_sqlite()
    if args.cmd == 'user':
        print(json.dumps(create_user(args.user_id, args.email, args.role, args.workspace, args.display_name, db), indent=2))
    else:
        print(json.dumps(create_api_token(args.user_id, args.name, args.role, args.workspace, db), indent=2))

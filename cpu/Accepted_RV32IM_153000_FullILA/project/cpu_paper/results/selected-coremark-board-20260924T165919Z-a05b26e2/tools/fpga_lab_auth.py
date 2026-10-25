"""Authenticate the pinned FPGA Lab client without requiring a browser.

Account files contain identifier and password on separate nonempty lines, as
documented by upstream. Credentials and refreshed tokens remain in memory.
This module performs no device reservation, programming, or serial operations.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
from fpga_lab_native import ORIGIN, PLATFORM_SOURCE, public_device

REPOSITORY = Path(__file__).resolve().parents[2]
DEFAULT_ACCOUNT = REPOSITORY / 'tool/account.txt'
DEFAULT_SESSION = REPOSITORY / 'tool/fpga_lab/sessions/platform_session.json'


def client_class():
    spec = importlib.util.spec_from_file_location('pinned_fpga_lab_auth', PLATFORM_SOURCE)
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module.PlatformClient


def credential_paths(account_file=None, session_file=None):
    account = Path(account_file or os.environ.get('FPGA_LAB_ACCOUNT') or DEFAULT_ACCOUNT).resolve()
    session = Path(session_file or DEFAULT_SESSION).resolve()
    # Explicit paths must not silently select some other account/session.
    if (account_file or os.environ.get('FPGA_LAB_ACCOUNT')) and not account.is_file():
        raise ValueError('The selected FPGA Lab account file does not exist')
    if session_file and not session.is_file():
        raise ValueError('The selected FPGA Lab session file does not exist')
    return account, session


def connect_native(account_file=None, session_file=None, *, factory=None):
    account, session = credential_paths(account_file, session_file)
    if not account.is_file() and not session.is_file():
        raise RuntimeError('Native FPGA Lab login needs a local account file or saved session; no credentials were found')
    client = (factory or client_class())(base_url=ORIGIN, session_file=None)
    try:
        if session.is_file() and (session_file or not (account_file or os.environ.get('FPGA_LAB_ACCOUNT'))):
            saved = json.loads(session.read_text(encoding='utf-8-sig'))
            client.token = saved.get('token')
            client.refresh_token = saved.get('refreshToken')
            client.expires_at = saved.get('expires_at')
            if client.is_authenticated():
                return client
        if account.is_file():
            lines = [line.strip() for line in account.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
            if len(lines) != 2:
                raise ValueError('The account file must contain exactly two nonempty lines')
            client.login(lines[0], lines[1])
            del lines
            if client.is_authenticated():
                return client
        raise RuntimeError('The existing native session could not be authenticated')
    except Exception:
        client.close()
        # Do not propagate server responses or parser excerpts containing secrets.
        raise RuntimeError('Native FPGA Lab authentication failed; check the local account/session file and service availability') from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account-file', type=Path)
    parser.add_argument('--session-file', type=Path)
    parser.add_argument('--check-files', action='store_true', help='Inspect availability without reading credentials or contacting the service')
    args = parser.parse_args()
    if args.check_files:
        account, session = credential_paths(args.account_file, args.session_file)
        print(json.dumps(dict(account_file_present=account.is_file(), session_file_present=session.is_file())))
        return
    client = connect_native(args.account_file, args.session_file)
    try:
        print(json.dumps(dict(authenticated=True, current=public_device(client.current_device())), ensure_ascii=True))
    finally:
        client.close()


if __name__ == '__main__':
    main()

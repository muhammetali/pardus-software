#!/usr/bin/env python3
"""Run the real installed GUI in a dedicated lab desktop; restore network rules."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

p = argparse.ArgumentParser()
p.add_argument('name')
p.add_argument('--desktop', choices=['gnome-shell', 'xfce4-session'], required=True)
p.add_argument('--network', choices=['online', 'offline'], required=True)
p.add_argument('--remove', action='store_true')
p.add_argument('--baseline', action='store_true')
args = p.parse_args()
assert Path('/etc/hostname').read_text().strip() in ('pardus-domain-lab', 'pardus-software23-lab')
root = Path.home() / 'software-ready'
out = root / 'results'
out.mkdir(exist_ok=True)
pid = subprocess.check_output(['pgrep', '-u', str(os.getuid()), '-x', args.desktop], text=True).split()[0]
session = dict(item.split('=', 1) for item in Path('/proc/' + pid + '/environ').read_bytes().decode().split('\0') if '=' in item)
env = os.environ.copy()
keys = ['DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS', 'XDG_CURRENT_DESKTOP', 'XDG_SESSION_TYPE', 'DESKTOP_SESSION', 'XDG_RUNTIME_DIR']
env.update({key: session[key] for key in keys if key in session})
env.update(LANG='tr_TR.UTF-8', LC_ALL='tr_TR.UTF-8', GDK_BACKEND='x11',
           PARDUS_LAB_MODE='baseline' if args.baseline else args.network,
           PARDUS_LAB_RESULT=str(out / args.name),
           PARDUS_LAB_SETTINGS='1', PARDUS_LAB_REMOVE='1' if args.remove else '0',
           PARDUS_LAB_RECOVER='1' if args.network == 'offline' and not args.baseline else '0')
print(json.dumps({key: env.get(key) for key in keys}, indent=2), flush=True)
assert env.get('DISPLAY') and env.get('DBUS_SESSION_BUS_ADDRESS')
if args.desktop == 'gnome-shell':
    # Leave GNOME's initial overview before directing real pointer events.
    subprocess.run(['xdotool', 'key', 'Escape'], env=env, check=True)
cache = Path.home() / '.cache/pardus/pardus-software'
if cache.exists():
    shutil.rmtree(cache)
subprocess.run(['pkill', '-u', str(os.getuid()), '-x', 'gvfsd-http'])
def cleanup():
    subprocess.run(['sudo', '-n', 'nft', 'delete', 'table', 'inet', 'codex_pardus_lab'], capture_output=True)
try:
    cleanup()
    if args.network == 'offline':
        subprocess.run(['sudo', '-n', 'nft', '-f', '-'], input='table inet codex_pardus_lab {\n chain output {\n'
            ' type filter hook output priority 0; policy accept;\n'
            ' oifname "lo" accept; ip daddr 192.168.122.0/24 accept; reject;\n }\n}\n', text=True, check=True)
    subprocess.run(['timeout', '360s', 'python3', str(root / 'software-ready-gui.py')], env=env, check=True, timeout=380)
finally:
    cleanup()

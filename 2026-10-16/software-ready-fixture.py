#!/usr/bin/env python3
"""Install an isolated, removable desktop package in the dedicated test VMs."""
from pathlib import Path
import subprocess
import tempfile

assert Path('/etc/hostname').read_text().strip() in ('pardus-domain-lab', 'pardus-software23-lab')
name = 'pardus-offline-removal-test'
with tempfile.TemporaryDirectory(prefix='offline-removal-fixture-') as temp:
    root = Path(temp) / name
    (root / 'DEBIAN').mkdir(parents=True)
    (root / 'DEBIAN/control').write_text('Package: ' + name + '\nVersion: 1.0\nArchitecture: all\n'
        'Maintainer: Pardus Test <test@example.invalid>\nDescription: Disposable offline removal test fixture\n')
    target = root / 'usr/share/applications'
    target.mkdir(parents=True)
    (target / (name + '.desktop')).write_text('[Desktop Entry]\nType=Application\n'
        'Name=Offline Removal Test\nComment=Disposable GUI removal test\nExec=/usr/bin/true\n'
        'Icon=application-x-executable\nCategories=Utility;\nTerminal=false\n')
    package = Path(temp) / (name + '.deb')
    subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(root), str(package)], check=True)
    subprocess.run(['sudo', '-n', 'dpkg', '-i', str(package)], check=True)
subprocess.run(['sudo', '-n', 'usermod', '-aG', 'pardus-software', 'pardus'], check=True)
subprocess.run(['dpkg-query', '-W', name], check=True)

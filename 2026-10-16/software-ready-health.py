#!/usr/bin/env python3
"""Verify the disposable lab after the real removal scenario."""
import hashlib
import json
from pathlib import Path
import subprocess

import apt

assert Path('/etc/hostname').read_text().strip() in ('pardus-domain-lab', 'pardus-software23-lab')
root = Path.home() / 'software-ready'
files = {}
for relative in ('src/MainWindow.py', 'ui/MainWindow.glade'):
    files[relative] = {
        label: hashlib.sha256((base / relative).read_bytes()).hexdigest()
        for label, base in [('source', root / 'source'),
                            ('installed', Path('/usr/share/pardus/pardus-software'))]
    }
    assert len(set(files[relative].values())) == 1, files
fixture = subprocess.run(['dpkg-query', '-W', '-f=${Status}', 'pardus-offline-removal-test'], capture_output=True)
assert fixture.returncode == 1, fixture.stdout
assert not Path('/usr/share/applications/pardus-offline-removal-test.desktop').exists()
assert apt.Cache().broken_count == 0
for command in (['sudo', '-n', 'dpkg', '--audit'], ['sudo', '-n', 'dpkg', '-V', 'pardus-software']):
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    assert not result.stdout.strip(), result.stdout
subprocess.run(['sudo', '-n', 'apt-get', 'check'], check=True)
rules = subprocess.check_output(['sudo', '-n', 'nft', 'list', 'ruleset'], text=True)
assert 'codex_pardus_lab' not in rules
package = root / 'pardus-software_1.0.6_all.deb'
print(json.dumps({'files': files, 'broken_count': 0, 'fixture_absent': True,
                  'network_rule_absent': True,
                  'package_sha256': hashlib.sha256(package.read_bytes()).hexdigest()}, indent=2))

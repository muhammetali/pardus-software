#!/usr/bin/env python3
"""Compare a PR's migration with settings written by the real 0.8.3 module.

Usage: python3 pr62-migration-check.py OLD_SRC NEW_SRC
Extract the official 0.8.3 .deb first; no installation is necessary.
Every scenario runs in temporary XDG directories and separate Python processes.
Exit 1 means at least one preference-preservation check failed.
"""
import configparser
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

OLD = r'''
from UserSettings import UserSettings
settings = UserSettings()
settings.createDefaultConfig()
assert settings.writeConfig(True, False, False, True, 'default', False, True, False, 1700000000, 86400)
print('OLD_CONFIG_PATH=' + settings.configdir + settings.configfile)
'''
NEW = r'''
import json
from UserSettings import UserSettings
settings = UserSettings()
settings.create_default_config()
settings.read_config()
print('RESULT=' + json.dumps({
    'animations': settings.config_animations,
    'only_available': settings.config_only_available,
    'gnome_comments': settings.config_gnome_comments,
    'dark_theme': settings.config_dark_theme,
    'auto_apt_update': settings.config_auto_apt_update,
    'last_update': settings.config_last_apt_update,
    'force_update_time': settings.config_force_apt_update_time,
}))
'''
EXPECTED = dict(animations=False, only_available=False, gnome_comments=False,
                dark_theme=True, auto_apt_update=False, last_update=1700000000,
                force_update_time=86400)


def run(source, code, env):
    process = subprocess.run([sys.executable, '-c', code],
                             env={**env, 'PYTHONPATH': str(Path(source).resolve())},
                             capture_output=True, text=True, check=True)
    return process.stdout


def scenario(name, old_src, new_src):
    with tempfile.TemporaryDirectory(prefix='pardus-settings-review-') as tmp:
        root = Path(tmp)
        env = {**os.environ, 'XDG_CONFIG_HOME': str(root / 'config'),
               'XDG_CACHE_HOME': str(root / 'cache')}
        if name in ('old_directory', 'existing_main'):
            (root / 'config/pardus-software').mkdir(parents=True)
        output = run(old_src, OLD, env)
        old_path = Path(next(line.split('=', 1)[1] for line in output.splitlines()
                             if line.startswith('OLD_CONFIG_PATH=')))
        old_text = old_path.read_text()
        target = root / 'config/pardus/pardus-software/settings.ini'
        expected = EXPECTED.copy()
        if name == 'existing_main':
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('[MAIN]\nAnimations=yes\nOnlyAvailableApps=yes\n'
                              'GnomeComments=yes\nDarkTheme=no\nAutoAptUpdate=no\n'
                              'LastAutoAptUpdate=1800000000\nForceAutoAptUpdateTime=43200\n')
            expected = dict(animations=True, only_available=True, gnome_comments=True,
                            dark_theme=False, auto_apt_update=False, last_update=1800000000,
                            force_update_time=43200)
        before = target.read_bytes() if target.exists() else None
        output = run(new_src, NEW, env)
        actual = json.loads(next(line[7:] for line in output.splitlines() if line.startswith('RESULT=')))
        parsed = configparser.ConfigParser()
        parsed.read(target)
        result = dict(case=name, legacy_relative_path=str(old_path.relative_to(root)),
                      legacy_config=old_text, expected=expected, actual=actual,
                      file_changed=before != target.read_bytes(), sections=parsed.sections(),
                      passed=actual == expected)
        if name == 'existing_main':
            result['passed'] = result['passed'] and before == target.read_bytes()
        return result


if __name__ == '__main__':
    old_src, new_src = sys.argv[1:]
    results = [scenario(case, old_src, new_src)
               for case in ('old_directory', 'new_directory', 'existing_main')]
    print(json.dumps(results, ensure_ascii=False, indent=2))
    sys.exit(0 if all(result['passed'] for result in results) else 1)

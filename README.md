# dRPG downloads and keeps your purchases from DriveThruRPG up to date
[![Maintainability](https://api.codeclimate.com/v1/badges/b3128ba6938f92088135/maintainability)](https://codeclimate.com/github/glujan/drpg/maintainability)

## Installation

This script is tested with Python 3.8 and requires Python 3.8 or newer to run.

You can install dRPG from PyPI:
```bash
pip install --user drpg
drpg --help  # or python -m drpg --help
```

## Usage

1. Go to [your account settings](https://www.drivethrurpg.com/account_edit.php)
   and generate a new application key.
2. Copy the key and run the script: `drpg --token <YOUR_DRPG_TOKEN>`.
3. Now just sit, relax and wait. Initial synchronization may take a while so
   why don't you grab a cup of tea or whatever your favourite beverage is. On
   consecutive runs the script will download only new and changed files which
   will be a way faster.

### Advanced options

You can change where your files will be downloaded by using `--library-path
path/to/your/directory`.

By default the script does not compare files by md5 checksum to save time. You
can turn it on by using `--use-checksums`.

You can change a log level by using `--log-level=<YOUR_LOG_LEVEL>`. Choices are
DEBUG, INFO, WARNING, ERROR, CRITICAL.

For more information, run the script with `--help`.

## Roadmap

- [x] Have a working scipt
- [x] Allow to choose where to sync purchased products
- [x] Allow for fast - based on modification timestamps - or strict - based on both modification timestamps and md5 checksums - comparison of synced and remote files
- [ ] Publish a stable release
  - [ ] Compatible with [DriveThruRPG Library App](https://www.drivethrurpg.com/library_client.php) v. 3.0.1.3
  - [ ] Document which official client version is the script compatible with
  - [ ] Decide on a versioning scheme - currently I'm considering using a [CalVer](https://calver.org/) with a version number matching the official client release date. For example version 2021.1.5 would be compatible with DriveThruRPG Library App v. 3.0.1.3 which was released on January 5, 2021 (see its [changelog](https://www.drivethrurpg.com/library_client.php#changelog-mac) for release dates)


## Found a bug?

Pull requests and bug reports are welcomed! See [CONTRIBUTING.md](CONTRIBUTING.md)
for more details.

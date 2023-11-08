# dRPG downloads and keeps your purchases from DriveThruRPG up to date
[![Maintainability](https://api.codeclimate.com/v1/badges/b3128ba6938f92088135/maintainability)](https://codeclimate.com/github/glujan/drpg/maintainability)
![PyPI](https://img.shields.io/pypi/v/drpg?label=drpg)

## Installation

This script runs with Python 3.8 and newer.

You can install dRPG from PyPI:
```bash
pip install --user drpg
drpg --help  # or python -m drpg --help
```

## Usage

1. Go to [your account settings](https://www.drivethrurpg.com/account_edit.php)
   and generate a new application key.
2. Copy the key and run the script: `drpg --token <YOUR_DRPG_TOKEN>` - or set
   `DRPG_TOKEN` env variable and run `drpg`.
3. Now just sit, relax and wait. Initial synchronization may take a while so
   why don't you grab a cup of tea or whatever your favourite beverage is. On
   consecutive runs the script will download only new and changed files which
   will be a way faster.

## Compatibility

Because of the nature of using an undocumented API, this software may break
without a notice. Version number indicates a year and a month when the software
was proved to be working with a real DriveThruRPG account.

### File name compatibility

The DriveThruRPG client does some interesting things with the names of directories.
For example, if you buy a product from publisher "Game Designers' Workshop (GDW)"
the DriveThruRPG client app will download it to a directory with the unwieldy name
"Game Designers__039_ Workshop _GDW_".

By default, `drpg` gives directories more user friendly name. In the example above,
the directory would be "Game Designers' Workshop (GDW)". However, this causes a
problem if you intend to try to manage the same e-book library using both `drpg` and
the DriveThruRPG client app. When you run the former, you'll get a friendly name,
then when you run the latter it will download all the same files again and put them
in a directory with the unfriendly name.

You can use the command line option `--compatibility-mode` to make `drpg` use the
same naming scheme for files and directories as the DriveThruRPG client. We have
also done our best to imitate DriveThruRPG's bugs while in `--compatibility-mode`
but I'm sure there are some we missed.


### Advanced options

You can change where your files will be downloaded by using `--library-path
path/to/your/directory`.

By default the script does not compare files by md5 checksum to save time. You
can turn it on by using `--use-checksums`.

You can change a log level by using `--log-level=<YOUR_LOG_LEVEL>`. Choices are
DEBUG, INFO, WARNING, ERROR, CRITICAL.

You can do a "dry run" of the app by specifying `--dry-run`. This will determine
all the digital content you have purchased, but instead of downloading each file
it will print one line of information to show what file *would* have been downloaded
if the `--dry-run` flag wasn't on. Use this if you want to test out the app without
taking the time to download anything.

For more information, run the script with `--help`.

## Found a bug?

Pull requests and bug reports are welcomed! See [CONTRIBUTING.md](CONTRIBUTING.md)
for more details.

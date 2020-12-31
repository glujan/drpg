# dRPG downloads and keeps your purchases from DriveThruRPG up to date
[![Maintainability](https://api.codeclimate.com/v1/badges/b3128ba6938f92088135/maintainability)](https://codeclimate.com/github/glujan/drpg/maintainability)

## Installation

This script is tested with and requires Python 3.8.

You can install dRPG from PyPI:
```bash
pip install --user drpg
drpg --help  # or python -m drpg --help
```

Alternatively, you can checkout a repository, install dependencies from
`requirements.txt` and run it using:

```bash
python3.8 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m drpg
```

## Usage

1. Go to [your account settings](https://www.drivethrurpg.com/account_edit.php)
   and generate a new application key.
2. Copy the key and run the script: `drpg --token <YOUR_DRPG_TOKEN>`.
3. Now just sit, relax and wait. Initial synchronization may take a while.  On
   consecutive runs the script will download only changed files.

### Advanced options

You can change where your files will be downloaded by using `--library-path
path/to/your/directory`.

By default the script does not compare files by md5 checksum to save time. You
can turn it on by using `--use-checksums`.

You can change a log level by using `--log-level=<YOUR_LOG_LEVEL>`. Choices are
DEBUG, INFO, WARNING, ERROR, CRITICAL.

For more information, run the script with `--help`.

## Development

Pull requests and bug reports are welcomed!

### Running tests

To run tests, install dependencies from `requirements.dev.txt` and run tests
with `unittest`:

```bash
pip install -r requirements.dev.txt
python -m unittest discover
```

### Building a wheel

The project is using setuptools. To generate a wheel package run:

```bash
python3 setup.py bdist_wheel
```

The wheel package will be saved in a `dist/` directory.

### Building a binary distribution

Stand-alone executables are generated using PyInstaller. To generate a binary
for your platform install dev requirements and run PyInstaller:

```bash
pip install -r requirements.dev.txt
pyinstaller drpg.spec
```

The binary will be saved in a `dist/` directory.

# Contributing

## Bug reports, features requests

Just go ahead and create [a new issue](issues/new). Please make your
description clear so it's easy to understand what the issue is about.
Is this is possible, paste the output of the program with a
`--log-level DEBUG` option.

## New features or bug fixes

Use standard GitHub Flow - create a fork of this repo, prepare a branch with
changes you'd like to have merged to the project and create a new Pull Request.

Please provide tests for the code you are contributing.

## Development

### Prerequisites

As a first step, you need to install `uv`, and install development dependencies:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
```

### Running tests

Tests are implemented in `unittest` standard library. To run them simply
execute:

```bash
uv run -m unittest discover
```

### Building a wheel

The project is using `build` with `hatchling` as a backend. To generate a source or wheel package run:

```bash
uv build
```

The wheel and source distribution will be saved in a `dist/` directory.


### Testing out the wheel

If you want to test the wheel you just created, install it in your project, like this:

```bash
uv pip install dist/drpg-2023.6.12.dev0-py3-none-any.whl --force-reinstall
```
Use the name of your own `.whl` file, of course.

Then you can do a test run like this:

```bash
uv run python -m drpg --dry-run --token <whatever> --library-path <whatever>
```

### Building a binary distribution

Stand-alone executables are generated using PyInstaller. To generate a binary
for your platform run:

```bash
uv run pyinstaller pyinstaller-linux.spec # If you run on Linux
uv run pyinstaller pyinstaller-macos.spec # If you run on MacOS
```

The binary will be saved in a `dist/` directory.

## Configuring mitmproxy

1. Set up and run mitmproxy
2. Set proxy in wine to 127.0.0.1:8080
   ```
   wine rundll32.exe shell32.dll,Control_RunDLL inetcpl.cpl
   ```
3. Run the official DriveThruRPG client. Login, download some products.
4. Save the mitmproxy flow. You can open it with:
   ```bash
   mitmproxy --rfile drpg.flow -n
   ```

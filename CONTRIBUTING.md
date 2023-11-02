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

# Development

## Prerequisites

As a first step, you need to create a new virtualenv and install development
dependencies:

```bash
python3.8 -m venv venv
source venv/bin/activate
pip install -r requirements.dev.txt

```

## Running tests

Tests are implemented in `unittest` standard library. To run them simply
execute:

```bash
source venv/bin/activate
python -m unittest discover
```

## Building a wheel

The project is using `build` with `hatchling` as a backend. To generate a source or wheel package run:

```bash
source venv/bin/activate
python -m build --sdist --wheel --outdir dist/
```

The wheel and source distribution will be saved in a `dist/` directory.


## Testing out the wheel

If you want to test the wheel you just created, install it in your project, like this:

```bash
source venv/bin/activate
pip install dist/drpg-2023.6.12.dev0-py3-none-any.whl --force-reinstall
```
Use the name of your own `.whl` file, of course.

Then you can do a test run like this:

```bash
python -m drpg --dry-run --token <whatever> --library-path <whatever>
```

# Changelog

## Unreleased

## 2025.7.8
* automatically retry failed API requests
* support httpx 0.27-0.28+
* publish distributions to GitHub release

## 2025.1.1
* add `--validate` that checks if downloaded file has correct checksums
* add `--threads` to allow user to specify a number of threads
* use HTTP2 for API communication
* support httpx 0.23-0.28+

## 2024.12.19
* rewrite client to use new API

## 2024.11.8
* add `--omit-publisher` - allows flat directory structure
* support Python 3.9-3.13
* test on Python 3.14 alpha
* support httpx 0.21-0.27+

## 2024.1.17
* support Python 3.8-3.12
* test on Python 3.13 alpha
* support httpx 0.20-0.26+

## 2023.11.10
* add `--compatibility-mode`

## 2023.11.8
* add `--dry-run` mode
* support Python 3.8-3.12.0-beta.2
* support httpx 0.20-0.24+
* move to pyproject.toml
* run `pre-commit` in CI

## 2023.5.11
* fixed a bug that interrupted some downloads (#34)

## 2022.12.0
* support Python 3.8-3.11

## 2022.9.0
* support httpx 0.20-0.22+

## 2022.2.0
* support httpx 0.16-0.22+

## 2021.10.0
* support Python 3.8-3.10

## 2021.9.0
* support Python 3.8-3.9
* support httpx 0.16-0.19
* specify options via CLI or env vars
* first _stable_ release

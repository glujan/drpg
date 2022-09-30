import setuptools

if __name__ == "__main__":
    # setuptools does not support setting install_requires from a file in setup.cfg
    with open("requirements.in", encoding="utf-8") as fh:
        install_requires = fh.read().splitlines()

    setuptools.setup(install_requires=install_requires)

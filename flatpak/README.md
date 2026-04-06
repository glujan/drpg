# Flatpak

The flatpak can manually be built as follows:

1. `flatpak install --assumeyes https://dl.flathub.org/build-repo/272081/org.flatpak.Builder.flatpakref`
    * This is a hack while we wait for https://github.com/flathub/org.flatpak.Builder/pull/393 to get merged
2. `flatpak run --command=flatpak-pip-generator org.flatpak.Builder --pyproject-file=../pyproject.toml --yaml`
3. `flatpak remote-add --if-not-exists --user flathub https://dl.flathub.org/repo/flathub.flatpakrepo`
4. `flatpak run org.flatpak.Builder --force-clean --user --install-deps-from=flathub --repo=repo --install builddir io.github.glujan.drpg.yaml`

And then `flatpak run io.github.glujan.drpg` will work

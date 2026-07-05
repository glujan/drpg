# Flatpak

The flatpak can manually be built as follows:

1. `flatpak remote-add --if-not-exists --user flathub https://dl.flathub.org/repo/flathub.flatpakrepo`
2. `flatpak install --user --assumeyes org.flatpak.Builder`
3. `flatpak run --command=flatpak-pip-generator org.flatpak.Builder --pyproject-file=../pyproject.toml --yaml`
4. `flatpak run org.flatpak.Builder --force-clean --user --install-deps-from=flathub --repo=repo --install builddir io.github.glujan.drpg.yaml`

And then `flatpak run io.github.glujan.drpg` will work

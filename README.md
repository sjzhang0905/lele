# LELE

**Local Environment and Lattice Explorer** is a desktop application for viewing molecular and crystal structures and exploring computational chemistry results.

[Online manual](https://sjzhang0905.dpdns.org/lele/manual/) · [Release notes](CHANGELOG.md) · [中文说明](README_CN.md)

## Run on Windows

Use 64-bit CPython 3.12 or 3.11. Extract the complete source archive and double-click `start_windows.bat`. The launcher creates the environment, installs dependencies and starts LELE.

To build a Windows executable after the first successful launch, run `build_windows.bat`. Distribute the complete `dist/LELE` folder.

## Run from source

```bash
python -m pip install -e ".[test]"
python -m lele
```

Run the tests with `python -m pytest tests -q`.

## Project

[Repository](https://github.com/sjzhang0905/lele) · [Development and releases](docs/GITHUB_PREPARATION_CN.md) · [Contact](mailto:sjzhang0905@hotmail.com)

[MIT License](LICENSE) · [Third-party notices](SOURCE_NOTICE.md)

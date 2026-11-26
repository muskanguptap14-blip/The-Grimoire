# Offline wheelhouse

Real wheels for the dependencies of `samples/sample-legacy-2`, so `grimoire prove` can install them with `pip --no-index` and reach ALIVE with no network.

| Package | Version | License |
| --- | --- | --- |
| beautifulsoup4 | 4.15.0 | MIT |
| soupsieve | 4.1.3 | MIT |
| six | 1.17.0 | MIT |
| typing_extensions | 4.16.0 | PSF-2.0 |

Source: PyPI. These are the unmodified published wheels, not stubs.

Grimoire never downloads anything at runtime. Use the wheelhouse with:

    python -m grimoire prove samples/sample-legacy-2 --wheelhouse wheelhouse

To refresh (needs network, run by a maintainer, not by Grimoire):

    pip download --no-deps -d wheelhouse six beautifulsoup4 soupsieve typing_extensions

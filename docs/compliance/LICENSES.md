# seismograph-probe -- dependencies and licences

The probe is distributed under **Apache-2.0**. This page and the two
CycloneDX SBOMs beside it answer the first question a security or
legal review asks before running the probe inside a company: what is
in it, and under which terms. The gate checks them
(`tests/test_sbom_licences.py`).

Resolution: 2026-10-01, Python 3.11, `pip` from PyPI, against the
version ranges in `pyproject_probe.toml` (probe 1.1.0). An SBOM
describes one resolution; your resolver may pick newer versions. The
SBOM is regenerated at every release.

## Runtime dependencies (`pip install seismograph-probe`)

| Package | Version | Licence |
|---|---|---|
| httpx | 0.28.1 | BSD-3-Clause |
| httpcore | 1.0.9 | BSD-3-Clause |
| h11 | 0.16.0 | MIT |
| anyio | 4.15.1 | MIT |
| idna | 3.20 | BSD-3-Clause |
| certifi | 2026.7.22 | MPL-2.0 |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause |
| cffi | 2.1.1 | MIT-0 |
| pycparser | 3.0 | BSD-3-Clause |
| typing_extensions | 4.16.0 | PSF-2.0 |

## Optional (`pip install seismograph-probe[otel]` / `[all]`)

| Package | Version | Licence |
|---|---|---|
| opentelemetry-sdk | 1.45.0 | Apache-2.0 |
| opentelemetry-api | 1.45.0 | Apache-2.0 |
| opentelemetry-semantic-conventions | 0.66b0 | Apache-2.0 |

## Findings

- No GPL, AGPL or LGPL component, direct or transitive.
- One file-level copyleft licence: **certifi, MPL-2.0**. It is used as
  an unmodified dependency and not vendored; MPL-2.0 obligations apply
  only to modified MPL files, so it imposes nothing on the probe or on
  code that uses it.
- Every component declares a licence.

## Files

- `sbom/seismograph-probe-1.1.0-core.cdx.json` -- runtime install.
- `sbom/seismograph-probe-1.1.0-all.cdx.json` -- with the `[all]` extra.

CycloneDX 1.6, JSON, generated with `cyclonedx-py` 7.5.0.

## How to regenerate

From the repository root, on a machine with network access to PyPI:

    python3.11 -m venv --without-pip sbom-env
    pip install --target sbom-env/lib/python3.11/site-packages "httpx>=0.24" "cryptography>=41.0" "opentelemetry-sdk>=1.20"
    pip install cyclonedx-bom
    cyclonedx-py environment --of JSON --spec-version 1.6 --output-reproducible --mc-type library --pyproject pyproject_probe.toml -o docs/compliance/sbom/seismograph-probe-<version>-all.cdx.json sbom-env/bin/python

Repeat without `opentelemetry-sdk` for the `core` file. Update the
tables above and the file names in `tests/test_sbom_licences.py`.

## EU Cyber Resilience Act

While the probe is free, non-commercial open source, it is outside
the CRA's manufacturer obligations. Any commercial distribution
(a paid service or product built on it) is in scope: vulnerability
and incident reporting from 11 September 2026, full obligations,
including a machine-readable SBOM available to authorities, from
11 December 2027. This page is the starting point for that.

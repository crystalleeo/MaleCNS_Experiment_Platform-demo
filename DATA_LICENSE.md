# MaleCNS-derived data and visualization assets

This document covers the MaleCNS-derived assets in this repository and its
associated GitHub Release assets. It does **not** extend the project's MIT code
license to data, geometry, or third-party software.

## Source attribution and applicable terms

Assets A1–A6 are derived from the **MaleCNS v1.0** dataset, maintained by the
[MaleCNS project](https://male-cns.janelia.org/) and distributed through its
[official download page](https://male-cns.janelia.org/download/). The source
dataset is available under [Creative Commons Attribution 4.0 International
(CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/).

Please retain this attribution and comply with the applicable CC BY 4.0 terms
when redistributing, adapting, or using these derived assets. Cite the MaleCNS
dataset and its primary publication: Berg et al. (2026), *Sexual dimorphism in
the complete Drosophila male central nervous system connectome*, Cell,
doi: [10.1016/j.cell.2026.08.015](https://doi.org/10.1016/j.cell.2026.08.015).

## Asset scope

| Assets | Description | Treatment |
|---|---|---|
| A1 | `canonical_body_ids.txt` | Derived list of traced body IDs. |
| A2 | `neurons.json` | Processed and downsampled 1,200-neuron viewer metadata subset. |
| A3 | `neurons_lines.bin` | **Project-derived visualization binary**: the subset was re-encoded and packed as M5LN. |
| A4 | `brain_shell.bin` | **Project-derived visualization binary**: brain ROI shell geometry was processed, recentered, and packed as M5MS. |
| A5 | `vnc_shell.bin` | **Project-derived visualization binary**: VNC ROI shell geometry was processed, recentered, and packed as M5MS. |
| A6 | `shell_meta.json` | Processed metadata for the packed shell geometry. |

These assets are modified, processed, downsampled, recentered, and/or packed
derivatives prepared for this viewer. They are not original raw MaleCNS assets
and must not be described as such.

For A4 and A5, the release provenance records a medium-confidence caveat: the
script's local ROI aliases are not byte-verified against the named upstream
ROI-parent identifiers. This does not change their status as project-derived
MaleCNS visualization assets or their applicable CC BY 4.0 terms.

Exact asset hashes, source references, and download locations are recorded in
`assets/manifest.json`.

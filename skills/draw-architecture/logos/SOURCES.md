# Logo sources

Every mark in `registry.json` came through `bin/add-logo.cjs`, which keeps its brand colours (a single-colour mark gets its brand colour from Simple Icons' data), keeps a one-ink copy for a theme where the colours do not read, and normalises its size and ink; its entry records the source, licence and aliases (the names a sheet may use for it).
The licence covers the drawing; the names and marks stay their owners' trademarks, used here only to name the technology a diagram shows (nominative use), never to suggest endorsement.

| Id | Mark | Source | Licence | One ink on |
|---|---|---|---|---|
| `adk` | Agent Development Kit | the `google-adk` wheel on PyPI, `google/adk/cli/browser/adk_favicon.svg` | Apache-2.0 | |
| `apacheairflow` | Apache Airflow | `@iconify-json/logos` on npm (`airflow-icon`, from gilbarbara/logos) | CC0-1.0 | |
| `dbt` | dbt | `@iconify-json/logos` (`dbt-icon`) | CC0-1.0 | |
| `github` | GitHub | `@iconify-json/logos` (`github-icon`) | CC0-1.0 | dark |
| `googlebigquery` | BigQuery | `simple-icons` on npm, in its brand colour | CC0-1.0 | |
| `googlecloudcomposer` | Cloud Composer | `simple-icons`, in its brand colour | CC0-1.0 | |
| `googlecloudrun` | Cloud Run | `@iconify-json/logos` (`google-cloud-run`) | CC0-1.0 | |
| `googlecloudstorage` | Cloud Storage | `simple-icons`, in its brand colour | CC0-1.0 | light |
| `googlepubsub` | Pub/Sub | `simple-icons`, in its brand colour | CC0-1.0 | light |
| `grafana` | Grafana | `@iconify-json/logos` (`grafana`) | CC0-1.0 | |
| `helm` | Helm | `@iconify-json/logos` (`helm`) | CC0-1.0 | dark |
| `kubernetes` | Kubernetes | `@iconify-json/logos` (`kubernetes`) | CC0-1.0 | |
| `postgresql` | PostgreSQL | `@iconify-json/logos` (`postgresql`) | CC0-1.0 | |
| `prometheus` | Prometheus | `@iconify-json/logos` (`prometheus`) | CC0-1.0 | |

## Left out, and why

- **MetricFlow:** no official mark exists in its repository or package; never borrow another product's (dbt's) for it.
- **Model providers (OpenRouter, a model family):** a diagram's model is a setting, swapped without changing the picture; it carries no logo by policy (SKILL.md), so none is kept.

## Adding one

Prefer, in order: the product's own package or repository (the mark it ships), `@iconify-json/logos` (full colour), `simple-icons` with `--hex` set to the brand colour its data records.
Run `node bin/add-logo.cjs <id> <file.svg> --title … --aliases … --source … --license … [--hex …]`, then regenerate `proof.png` and `proof-dark.png` here (`node bin/check.cjs --proof logos/proof.png`) and look at the mark at 14 px in both themes before using it: if the mark does not read, leave it out and say so above.

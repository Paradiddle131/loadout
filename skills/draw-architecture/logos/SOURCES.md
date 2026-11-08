# Logo sources

Every mark in `registry.json` came through `bin/add-logo.cjs`, which keeps it as drawn (its masks, clip paths and filters too) in its brand colours (a single-colour mark gets its brand colour from Simple Icons' data), keeps a one-ink copy for a theme where the colours do not read, and normalises its size and ink; its entry records the source, licence and aliases (the names a sheet may use for it).
The licence covers the drawing; the names and marks stay their owners' trademarks, used here only to name the technology a diagram shows (nominative use), never to suggest endorsement.

| Id | Mark | Source | Licence | One ink on |
|---|---|---|---|---|
| `adk` | Agent Development Kit | the `google-adk` wheel on PyPI, `google/adk/cli/browser/adk_favicon.svg` | Apache-2.0 | |
| `apacheairflow` | Apache Airflow | `@iconify-json/logos` on npm (`airflow-icon`, from gilbarbara/logos) | CC0-1.0 | |
| `dbt` | dbt | `@iconify-json/logos` (`dbt-icon`) | CC0-1.0 | |
| `github` | GitHub | `@iconify-json/logos` (`github-icon`) | CC0-1.0 | dark |
| `googlebigquery` | BigQuery | cloud.google.com/icons, core products zip (`BigQuery-512-color`) | Google Cloud icons, offered for architecture diagrams and docs | |
| `googlecloudcomposer` | Cloud Composer | cloud.google.com/icons, legacy icons zip (`cloud_composer`) | Google Cloud icons, offered for architecture diagrams and docs | |
| `googlecloudfirestore` | Firestore | cloud.google.com/icons, legacy icons zip (`firestore`) | Google Cloud icons, offered for architecture diagrams and docs | |
| `googlecloudlogging` | Cloud Logging | cloud.google.com/icons, legacy icons zip (`cloud_logging`) | Google Cloud icons, offered for architecture diagrams and docs | |
| `googlecloudmonitoring` | Cloud Monitoring | cloud.google.com/icons, legacy icons zip (`cloud_monitoring`) | Google Cloud icons, offered for architecture diagrams and docs | |
| `googlecloudrun` | Cloud Run | cloud.google.com/icons, core products zip (`CloudRun-512-color-rgb`) | Google Cloud icons, offered for architecture diagrams and docs | |
| `googlecloudscheduler` | Cloud Scheduler | cloud.google.com/icons, legacy icons zip (`cloud_scheduler`) | Google Cloud icons, offered for architecture diagrams and docs | |
| `googlecloudsql` | Cloud SQL | cloud.google.com/icons, core products zip (`CloudSQL-512-color`) | Google Cloud icons, offered for architecture diagrams and docs | |
| `googlecloudstorage` | Cloud Storage | cloud.google.com/icons, core products zip (`Cloud_Storage-512-color`) | Google Cloud icons, offered for architecture diagrams and docs | |
| `googlecloudworkflows` | Workflows | cloud.google.com/icons, legacy icons zip (`workflows`) | Google Cloud icons, offered for architecture diagrams and docs | |
| `googlegemini` | Gemini Enterprise | `@iconify-json/logos` (`google-gemini-icon`) | CC0-1.0 | |
| `googlepubsub` | Pub/Sub | cloud.google.com/icons, legacy icons zip (`pubsub`) | Google Cloud icons, offered for architecture diagrams and docs | |
| `grafana` | Grafana | `@iconify-json/logos` (`grafana`) | CC0-1.0 | |
| `helm` | Helm | `@iconify-json/logos` (`helm`) | CC0-1.0 | dark |
| `iap` | Identity-Aware Proxy | cloud.google.com/icons, legacy icons zip (`identity-aware_proxy`) | Google Cloud icons, offered for architecture diagrams and docs | |
| `kubernetes` | Kubernetes | `@iconify-json/logos` (`kubernetes`) | CC0-1.0 | |
| `mcp` | Model Context Protocol | `@iconify-json/logos` (`model-context-protocol-icon`), in black | CC0-1.0 | dark |
| `postgresql` | PostgreSQL | `@iconify-json/logos` (`postgresql`) | CC0-1.0 | |
| `prometheus` | Prometheus | `@iconify-json/logos` (`prometheus`) | CC0-1.0 | |
| `vertexai` | Vertex AI | cloud.google.com/icons, core products zip (`VertexAI-512-color`) | Google Cloud icons, offered for architecture diagrams and docs | |

## Left out, and why

- **MetricFlow:** no official mark exists in its repository or package; never borrow another product's (dbt's) for it.
- **OAuth:** its mark is a white letter on a black disc, so its one-ink copy on a dark card is a blank disc.
- **Model Armor:** Google publishes no product icon for it (only Cloud Armor's, a different product).
- **Model providers (OpenRouter, a model family):** a diagram's model is a setting, swapped without changing the picture; it carries no logo by policy (SKILL.md), so none is kept.

## Adding one

Prefer, in order: the product's own package or repository (the mark it ships), Google's own product icons for a Google Cloud service (cloud.google.com/icons; `add-logo.cjs` inlines their `<style>` class fills), `@iconify-json/logos` (full colour), `simple-icons` with `--hex` set to the brand colour its data records.
Run `node bin/add-logo.cjs <id> <file.svg> --title … --aliases … --source … --license … [--hex …]`, then regenerate `proof.png` and `proof-dark.png` here (`node bin/check.cjs --proof logos/proof.png`) and look at the mark at 14 px in both themes before using it: if the mark does not read, leave it out and say so above.

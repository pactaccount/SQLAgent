# Using SeaQL

Open the deployed app and choose **Connect a database**. For a file on your computer,
choose the file option, upload a **CSV or SQLite** file, continue and connect. CSV
files require a header row and UTF-8 comma-separated text. The upload message shows
the imported table and number of rows. Ask a question using the displayed columns.

The result table and SQL let you inspect what the agent actually queried. You can
edit and rerun read queries, inspect the schema, and keep conversations in tabs.
An ambiguous question should produce clarification. Successful SQL execution does
not guarantee the correct business answer; use the evaluation framework to measure it.

The application calls one NVIDIA-hosted model; the deployment needs NVIDIA_API_KEY
in server-side environment settings. No Qdrant, Hugging Face token or local GPU is
required. Use the repository Dockerfile for the locked Python 3.12 environment.

Render free hosting does not preserve uploads across restarts or redeployments.
If a saved connection no longer exists, upload the file again and reconnect.
Connections and write approval are for trusted demonstration use, not authenticated
multi-user database administration. The original Olist dataset is protected from
writes; use a working copy for change demonstrations.

For local startup, testing, evaluation commands and measured limitations, see
[README.md](README.md), [System overview](docs/SYSTEM_OVERVIEW.md), and
[Evaluation](docs/EVALUATION.md). The previous guide is preserved under archive/legacy/.

# Example data

`support_demo.csv` is a small synthetic customer-support dataset (generated from templates, no real customer
text) with the label contract in `support_demo.contract.yaml`. It exists so a fresh clone can exercise import,
snapshot, training, promotion and scoring on CPU in seconds.

Metrics obtained on it are **demo metrics**: the texts are templated and near-duplicates are common, so scores
are not evidence about any real dataset. Split assignment groups rows by `group_id` and exact duplicate text.

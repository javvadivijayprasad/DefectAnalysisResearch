# Datasets — Paper 7

The labeled dataset consumed by `scripts/run_experiment.py` is produced by `scripts/build_dataset.py`. This directory is the landing zone for the raw inputs and the generated parquet.

## Expected inputs

```
datasets/
├── repos/                          # git clones of the five subject projects
│   ├── spring-boot/
│   ├── kafka/
│   ├── hadoop/
│   ├── elasticsearch/
│   └── express/
├── runs/                           # one JSON per historical test run, per repo
│   ├── spring-boot/*.json
│   ├── kafka/*.json
│   └── ...
├── issues/                         # issue-tracker dumps for SZZ labeling
│   ├── spring-boot.json
│   └── ...
└── audit/                          # build audit logs (auto-generated)
```

## Run JSON format

Each file describes one historical test run:

```jsonc
{
  "run_id": "run-2024-07-12-1312",
  "commit_sha": "a1b2c3d...",
  "timestamp_iso": "2024-07-12T13:12:00Z",
  "diff_summary": {
    "schema_changed": true,
    "fixture_changed": false,
    "validator_changed": false,
    "config_changed": false,
    "app_code_changed": true
  },
  "failures": [
    {
      "test_file": "tests/order/order_service_test.java",
      "test_name": "OrderServiceTest#submit_order_with_new_currency",
      "exception_type": "ValidationException",
      "http_status": 422,
      "schema_error_path": "$.currency",
      "implicated_files": ["src/main/java/.../OrderService.java"],
      "locator_healed": false
    }
  ]
}
```

## Generated output

```
datasets/paper7_labeled.parquet     # primary consumed by run_experiment.py
datasets/audit/build_summary.json   # reproducibility audit (seed, hash, counts)
```

## Privacy

Nothing in this directory may include customer data, commit messages, or author emails beyond what is already public in the source repositories. The build script passes everything through the shared `ai-quality.config.yaml` filter.

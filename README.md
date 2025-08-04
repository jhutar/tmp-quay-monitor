Programable exporter
====================

Very simple Prometheus exporter written in Python meant to measure execution of
different functions, so you can measure various stuff repeatedly with separate
metrics for each of these probes.

E.g. how quickly can be pull from quay.io and also clone from github.com?

These 3 metrics are available for each of configured probes:

```
progexp_probe_duration{args="quay.io/prometheus/node-exporter:latest",name="probe_quay"} 3.985490802966524
progexp_probe_success{args="quay.io/prometheus/node-exporter:latest",name="probe_quay"} 0.0
progexp_probe_last_start{args="quay.io/prometheus/node-exporter:latest",name="probe_quay"} 1.7542906657376735e+09
```

Development
-----------

Prepare environment:

    python -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt

See it in action:

    python programable-exporter.py
    curl http://localhost:8000   # from different terminal

Build and run container:

    podman build -f Containerfile . -t quay-monitor
    podman run --network=host -p 8000 --rm -ti quay-monitor
    curl http://localhost:8000   # from different terminal

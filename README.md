Programable exporter
====================

Very simple Python exporter meant to measure execution of given code.

E.g. how quickly can be pull from quay.io?

Development
-----------

Prepare environment:

    python -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt

See it in action:

    python programable-exporter.py
    curl http://localhost:8000

#!/usr/bin/env python

import configparser
import logging
import os
import prometheus_client
import stopit2
import time
import subprocess
import shutil

# Load config
config = configparser.ConfigParser()
config.read(os.environ.get("CONFIG_FILE", "programable-exporter.ini"))

_logging_lvl_map = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}

# Create logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=_logging_lvl_map[config["config"]["logging_level"]])
logger.debug(f"Loaded config: {dict(config['config'])}")

# Create a Prometheus gauge metrics
probe_duration = prometheus_client.Gauge(
    "progexp_probe_duration",
    "How long the last execution of the Programable exporter probe took in seconds",
    ["image"],
)
probe_success = prometheus_client.Gauge(
    "progexp_probe_success",
    "Was the last Programable exporter probe execution successful? 0 for pass, 1 otherwise",
    ["image"],
)
probe_last_start = prometheus_client.Gauge(
    "progexp_probe_last_start",
    "When was the Programable exporter probe last started time as unix timestamp",
    ["image"],
)


def measure(image):
    """
    Perform a measured action
    """
    logger = logging.getLogger("probe")

    logger.debug("Cleanup")
    try:
        shutil.rmtree("/tmp/storage")
    except FileNotFoundError:
        pass

    logger.debug(f"Pulling {image}")
    completed = subprocess.run(
        ["skopeo", "copy", "docker://" + image, "dir:///tmp/storage"],
        capture_output=True,
        check=True,
    )
    logger.debug(f"Pulled: {completed}")


if __name__ == "__main__":
    logger.info("Starting metrics endpoint server")
    prometheus_client.start_http_server(int(config["config"]["port"]))

    logger.info("Starting probing loop")
    while True:
        probe_last_start.labels(image=config["config"]["image"]).set_to_current_time()
        before = time.perf_counter()
        try:
            with stopit2.ThreadingTimeout(int(config["config"]["probe_timeout"])) as timeout_mgr:
                measure(config["config"]["image"])
            if not timeout_mgr:
                raise Exception("Probe did not finished before timeout")
        except Exception as e:
            probe_success.labels(image=config["config"]["image"]).set(1)
            logger.exception(f"Probe failed with {e}")
        else:
            probe_success.labels(image=config["config"]["image"]).set(0)
            logger.info(f"Probe passed")
        after = time.perf_counter()
        duration = after - before
        probe_duration.labels(image=config["config"]["image"]).set(duration)
        logger.info(f"Probe took {duration} seconds to run")

        # Wait for next iteration
        interval = int(config["config"]["interval"]) - (after - before)
        logger.debug(f"Waiting for {interval} seconds for next test")
        time.sleep(interval)

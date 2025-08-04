#!/usr/bin/env python

import configparser
import logging
import os
import prometheus_client
import stopit2
import time
import subprocess
import shutil
import threading

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
logging.basicConfig(
    format='%(asctime)s %(name)s %(threadName)s %(levelname)s %(message)s',
    level=_logging_lvl_map[config.get("config", "logging_level")],
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger.debug(f"Loaded config: {dict(config['config'])}")

# Create a Prometheus gauge metrics
probe_duration = prometheus_client.Gauge(
    "progexp_probe_duration",
    "How long the last execution of the Programable exporter probe took in seconds",
    ["name", "args"],
)
probe_success = prometheus_client.Gauge(
    "progexp_probe_success",
    "Was the last Programable exporter probe execution successful? 0 for pass, 1 otherwise",
    ["name", "args"],
)
probe_last_start = prometheus_client.Gauge(
    "progexp_probe_last_start",
    "When was the Programable exporter probe last started time as unix timestamp",
    ["name", "args"],
)

class Probes():
    def probe_slow(self, _):
        """
        Test probe to ensure we handle timeouting probes.
        """
        logger = logging.getLogger("probe_slow")

        logger.debug("Starting slow probe")
        time.sleep(20)
        logger.debug("Timeout did not happened - this should not happen!")

    def probe_exception(self, _):
        """
        Test probe to ensure we handle probes that throw traceback.
        """
        logger = logging.getLogger("probe_exception")

        logger.debug("Starting buggy probe")
        raise Exception("Just to test we handle exceptions")
        logger.debug("Exception did not happened - this should not happen!")

    def probe_quay(self, image):
        """
        Test if we can pull from quay.io
        """
        logger = logging.getLogger("probe_quay")

        logger.debug("Cleanup")
        try:
            shutil.rmtree("/tmp/probe_quay")
        except FileNotFoundError:
            pass

        logger.debug(f"Pulling {image}")
        completed = subprocess.run(
            ["skopeo", "copy", "docker://" + image, "dir:///tmp/probe_quay"],
            capture_output=True,
            check=True,
        )
        logger.debug(f"Pulled: {completed}")


    def probe_github(self, repo):
        """
        Test if we canclone from github.com
        """
        logger = logging.getLogger("probe_github")

        logger.debug("Cleanup")
        try:
            shutil.rmtree("/tmp/probe_github")
        except FileNotFoundError:
            pass

        logger.debug(f"Cloning {repo}")
        completed = subprocess.run(
            ["git", "clone", repo, "/tmp/probe_github"],
            capture_output=True,
            check=True,
        )
        logger.debug(f"Cloned: {completed}")


def iteration(probe):
    logger = logging.getLogger("iteration")

    probe_last_start.labels(name=probe["name"], args=probe["args"]).set_to_current_time()
    before = time.perf_counter()
    try:
        with stopit2.ThreadingTimeout(probe["timeout"]) as timeout_mgr:
            probe["func"](probe["args"])
        if not timeout_mgr:
            raise Exception(f"Probe {probe['name']} did not finished before timeout {probe['timeout']}")
    except Exception as e:
        probe_success.labels(name=probe["name"], args=probe["args"]).set(1)
        logger.exception(f"Probe {probe['name']} failed with {e}")
    else:
        probe_success.labels(name=probe["name"], args=probe["args"]).set(0)
        logger.info(f"Probe {probe['name']} passed")
    after = time.perf_counter()
    duration = after - before
    probe_duration.labels(name=probe["name"], args=probe["args"]).set(duration)
    logger.info(f"Probe {probe['name']} took {duration} seconds to run")


if __name__ == "__main__":
    logger.info("Starting metrics endpoint server")
    prometheus_client.start_http_server(int(config["config"]["port"]))

    probes = Probes()
    probes_list = []
    for probe_name in config.sections():
        if probe_name == "config":
            continue
        if hasattr(probes, probe_name) and callable(getattr(probes, probe_name)):
            probes_list.append({
                "name": probe_name,
                "func": getattr(probes, probe_name),
                "args": config.get(probe_name, "args"),
                "timeout": config.getint(probe_name, "timeout"),
            })
        else:
            logger.warning(f"Failed to load probe '{probe_name}'")
    logger.info(f"Loaded {len(probes_list)} probes: {', '.join([p['name'] for p in probes_list])}")

    logger.info("Starting probing loop")
    while True:
        start = time.perf_counter()
        threads = []
        for probe in probes_list:
            t = threading.Thread(target=iteration, args=(probe,))
            t.start()
            threads.append(t)
        for t in threads:
            t.join()
        end = time.perf_counter()

        # Wait for next iteration
        interval = config.getint("config", "interval") - (end - start)
        logger.debug(f"Waiting for {interval} seconds for next iteration")
        time.sleep(interval)

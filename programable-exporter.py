#!/usr/bin/env python

import asyncio
import configparser
import logging
import os
import prometheus_client
import time
import subprocess
import shutil

# --- CONFIG, LOGGING, and PROMETHEUS METRICS (Unchanged) ---
# Load config
config = configparser.ConfigParser()
config.read(os.environ.get("CONFIG_FILE", "programable-exporter.ini"))

_logging_lvl_map = {
    "DEBUG": logging.DEBUG, "INFO": logging.INFO,
    "WARNING": logging.WARNING, "ERROR": logging.ERROR,
}

# Create logger
logger = logging.getLogger(__name__)
logging.basicConfig(
    format='%(asctime)s %(name)s %(levelname)s %(message)s',
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
    "Was the last Programable exporter probe execution successful? 0 for fail, 1 for pass",
    ["name", "args"],
)
probe_last_start = prometheus_client.Gauge(
    "progexp_probe_last_start",
    "When was the Programable exporter probe last started time as unix timestamp",
    ["name", "args"],
)

# --- ASYNC PROBE IMPLEMENTATIONS ---

class Probes():
    async def probe_slow(self, _):
        """Test probe to ensure we handle timeouting probes."""
        logger = logging.getLogger("probe_slow")
        logger.debug("Starting slow probe")
        await asyncio.sleep(20) # Use non-blocking sleep
        logger.debug("Timeout did not happen - this should not happen!")

    async def probe_exception(self, _):
        """Test probe to ensure we handle probes that throw traceback."""
        logger = logging.getLogger("probe_exception")
        logger.debug("Starting buggy probe")
        raise Exception("Just to test we handle exceptions")
        logger.debug("Exception did not happen - this should not happen!")

    async def _run_command(self, cmd_args: list):
        """Helper to run external commands asynchronously."""
        proc = await asyncio.create_subprocess_exec(
            *cmd_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            # Recreate the exception that subprocess.run(check=True) would raise
            raise subprocess.CalledProcessError(
                proc.returncode, cmd_args, output=stdout, stderr=stderr
            )
        return stdout.decode()

    async def probe_quay(self, image):
        """Test if we can pull from quay.io asynchronously."""
        logger = logging.getLogger("probe_quay")
        logger.debug("Cleanup")
        shutil.rmtree("/tmp/probe_quay", ignore_errors=True)

        logger.debug(f"Pulling {image}")
        completed = await self._run_command(
            ["skopeo", "copy", f"docker://{image}", "dir:///tmp/probe_quay"]
        )
        logger.debug(f"Pulled: {completed}")

    async def probe_github(self, repo):
        """Test if we can clone from github.com asynchronously."""
        logger = logging.getLogger("probe_github")
        logger.debug("Cleanup")
        shutil.rmtree("/tmp/probe_github", ignore_errors=True)

        logger.debug(f"Cloning {repo}")
        completed = await self._run_command(
            ["git", "clone", repo, "/tmp/probe_github"]
        )
        logger.debug(f"Cloned: {completed}")

# --- ASYNC ORCHESTRATION LOGIC ---

async def run_single_probe(probe):
    """Manages the execution and metrics for a single async probe."""
    logger = logging.getLogger(f"runner.{probe['name']}")
    probe_labels = {"name": probe["name"], "args": probe["args"]}

    probe_last_start.labels(**probe_labels).set_to_current_time()
    before = time.perf_counter()
    
    try:
        # Use asyncio.wait_for for reliable timeouts
        await asyncio.wait_for(
            probe["func"](probe["args"]),
            timeout=probe["timeout"]
        )
    except asyncio.TimeoutError:
        probe_success.labels(**probe_labels).set(0) # 0 for fail
        logger.error(f"Probe timed out after {probe['timeout']} seconds")
    except Exception:
        probe_success.labels(**probe_labels).set(0) # 0 for fail
        logger.exception("Probe failed with an exception")
    else:
        probe_success.labels(**probe_labels).set(1) # 1 for pass
        logger.info("Probe passed")
    finally:
        after = time.perf_counter()
        duration = after - before
        probe_duration.labels(**probe_labels).set(duration)
        logger.info(f"Probe took {duration:.2f} seconds to run")

async def main():
    """Main async function to load probes and run the main loop."""
    probes = Probes()
    probes_list = []
    for probe_name in config.sections():
        if probe_name == "config":
            continue
        # Important: check for 'probe_' prefix to ensure it's a real probe
        if probe_name.startswith("probe_") and hasattr(probes, probe_name):
            probes_list.append({
                "name": probe_name,
                "func": getattr(probes, probe_name),
                "args": config.get(probe_name, "args", fallback=""),
                "timeout": config.getint(probe_name, "timeout"),
            })
        else:
            logger.warning(f"Failed to load or find a valid probe method for '{probe_name}'")
    
    logger.info(f"Loaded {len(probes_list)} probes: {', '.join([p['name'] for p in probes_list])}")

    logger.info("Starting probing loop")
    while True:
        start = time.perf_counter()
        
        # Create a list of tasks to run concurrently
        tasks = [run_single_probe(p) for p in probes_list]
        await asyncio.gather(*tasks) # Run all probes concurrently

        end = time.perf_counter()
        
        # Wait for the next iteration
        interval = config.getint("config", "interval")
        wait_time = max(0, interval - (end - start))
        logger.debug(f"Waiting for {wait_time:.2f} seconds for next iteration")
        await asyncio.sleep(wait_time)


if __name__ == "__main__":
    logger.info("Starting metrics endpoint server")
    prometheus_client.start_http_server(int(config["config"]["port"]))
    
    # Run the main asynchronous event loop
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down exporter.")

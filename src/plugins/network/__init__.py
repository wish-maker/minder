"""Network discovery & inventory plugin (first-party module plugin).

Not a passive scanner — an autonomous **discover → reconcile → act** loop. On a
configurable interval it discovers the configured targets and fans the findings out
across the platform, so newly-found devices are automatically inventoried and
monitored:

  Discovery
    - nmap connect scan (``-sT -sV`` — no root) → open ports + service/version;
      stdlib TCP-connect fallback if nmap is absent.
    - SNMP (UDP, **v2c or v3** — net-snmp CLI, no extra Python lib) for every live
      host (non-SNMP hosts fast-skip after one timed-out get), gathered concurrently:
        · system group (sysDescr/sysObjectID/sysUpTime/sysContact/sysName/sysLocation),
        · rich interface table (ifDescr/ifType/ifSpeed/ifPhysAddress-MAC/ifOperStatus/
          ifAlias) via snmpbulkwalk,
        · Host-Resources MIB (uptime / memory / per-CPU load / storage table),
        · ARP / neighbour table (ipNetToMediaPhysAddress → IP↔MAC).

  Fan-out (each sink is independently toggled + fails soft — a down backend never
  breaks the cycle):
    - **telegraf**  → the telegraf plugin's managed region (net_response per port +
                      snmp per SNMP host) so telegraf monitors them → InfluxDB/Grafana.
                      Only when NETWORK_AUTO_APPLY=1 (the safety switch) and only on
                      change (no reload churn).
    - **postgres**  → a `network_inventory` table (ip/hostname/os/ports/snmp/status/
                      first_seen/last_seen) — the structured device inventory.
    - **neo4j**     → a topology graph (Host / Service / Interface nodes + RUNS /
                      HAS_INTERFACE) via the HTTP transactional Cypher API.
    - **rabbitmq**  → change events (`network.host.new` / `.down` / `.changed`) on the
                      amq.topic exchange, via the management API.

Uses only deps already in the plugin-registry image (httpx + asyncpg); Neo4j and
RabbitMQ are reached over HTTP, no extra drivers.

Config (env on plugin-registry):
  NETWORK_SCAN_TARGETS    hosts/CIDRs, comma-sep. EMPTY default → scans nothing.
  NETWORK_SCAN_PORTS      nmap port spec (default "22,80,161,443,8080").
  NETWORK_SCAN_MAX_HOSTS  cap on expanded hosts (default 256).
  NETWORK_SCAN_INTERVAL   autonomous reconcile interval, seconds (default 3600).
  NETWORK_AUTO_APPLY      "1"/"0" — auto-write telegraf on each cycle (default "1").
  NETWORK_AUTO_EXPAND     "1"/"0" — fold ARP neighbours into scope (default "0").
  NETWORK_EXPAND_CIDRS    CIDRs auto-expansion is allowed within (the boundary).
  NETWORK_SNMP_ENABLED / NETWORK_SNMP_COMMUNITY (v2c)
  NETWORK_SNMP_VERSION    "2c" (default) or "3".
  NETWORK_SNMP_V3_USER / _LEVEL (noAuthNoPriv|authNoPriv|authPriv) /
  _AUTH_PROTO (SHA|MD5) / _AUTH_PASS / _PRIV_PROTO (AES|DES) / _PRIV_PASS.
  NETWORK_SINK_TELEGRAF / _POSTGRES / _NEO4J / _RABBITMQ  ("1"/"0", default "1").

Only scan networks you are authorised to (your own infra).

SECURITY: SNMP v3 auth/priv passphrases are passed to the net-snmp CLI on argv
(visible via ps / /proc within this container, which already holds them as env). Sink
credentials go over HTTP client auth, not URLs; sink error logs record the exception
TYPE only, never the message, to avoid leaking secrets.
"""

import asyncio
import json
import logging
import os
import shutil
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx

from plugins._contract import PluginMetadata

from .helpers import (  # noqa: F401 (re-exported for the plugin + its tests)
    _ARP_MAC_OID,
    _HR_MEMSIZE_OID,
    _HR_PROC_LOAD_OID,
    _HR_STOR_DESCR_OID,
    _HR_STOR_SIZE_OID,
    _HR_STOR_USED_OID,
    _HR_UPTIME_OID,
    _IF_ALIAS_OID,
    _IF_DESCR_OID,
    _IF_MAC_OID,
    _IF_OPER,
    _IF_OPERSTATUS_OID,
    _IF_SPEED_OID,
    _IF_TYPE_OID,
    _SNMP_SYSTEM_OIDS,
    _configured_cidrs,
    _diff_hosts,
    _expand_targets,
    _extract_neighbor_ips,
    _normalize_mac,
    _parse_arp,
    _parse_nmap_xml,
    _parse_snmpwalk,
    _summarize,
    _telegraf_config,
)

__all__ = ["NetworkPlugin"]

logger = logging.getLogger("minder.plugin.network")

_CONNECT_TIMEOUT = 2.0
_MAX_CONCURRENCY = 64
_NMAP_HOST_TIMEOUT = "30s"
_NMAP_MAX_TIMEOUT = 1800  # cap the whole-scan timeout (s) regardless of host count
_SNMP_TIMEOUT = "2"
_SNMP_MAX_CONCURRENCY = 16


class NetworkPlugin:
    """Autonomous nmap+SNMP discovery that fans findings into telegraf/PG/Neo4j/RabbitMQ."""

    ACTIONS = frozenset({"scan", "reconcile"})

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.targets = os.environ.get("NETWORK_SCAN_TARGETS", "")
        self.ports = os.environ.get("NETWORK_SCAN_PORTS", "22,80,161,443,8080")
        self.max_hosts = int(os.environ.get("NETWORK_SCAN_MAX_HOSTS", "256"))
        self.interval = int(os.environ.get("NETWORK_SCAN_INTERVAL", "3600"))
        self.auto_apply = os.environ.get("NETWORK_AUTO_APPLY", "1") == "1"
        # Self-expanding discovery: add ARP neighbours found inside an explicitly
        # authorised range to the scan scope. Opt-in (off by default) + bounded to
        # NETWORK_EXPAND_CIDRS (the operator's authorisation boundary) — it widens
        # what gets scanned, so both the toggle and the range are deliberate.
        self.auto_expand = os.environ.get("NETWORK_AUTO_EXPAND", "0") == "1"
        self.expand_cidrs = os.environ.get("NETWORK_EXPAND_CIDRS", "")
        self.snmp_enabled = os.environ.get("NETWORK_SNMP_ENABLED", "1") == "1"
        self.snmp_version = os.environ.get("NETWORK_SNMP_VERSION", "2c")  # "2c" | "3"
        self.snmp_community = os.environ.get("NETWORK_SNMP_COMMUNITY", "public")
        # SNMPv3 (used when NETWORK_SNMP_VERSION=3):
        self.snmp_v3_user = os.environ.get("NETWORK_SNMP_V3_USER", "")
        self.snmp_v3_level = os.environ.get("NETWORK_SNMP_V3_LEVEL", "authPriv")
        self.snmp_v3_auth_proto = os.environ.get("NETWORK_SNMP_V3_AUTH_PROTO", "SHA")
        self.snmp_v3_auth_pass = os.environ.get("NETWORK_SNMP_V3_AUTH_PASS", "")
        self.snmp_v3_priv_proto = os.environ.get("NETWORK_SNMP_V3_PRIV_PROTO", "AES")
        self.snmp_v3_priv_pass = os.environ.get("NETWORK_SNMP_V3_PRIV_PASS", "")
        self.sink_telegraf = os.environ.get("NETWORK_SINK_TELEGRAF", "1") == "1"
        self.sink_postgres = os.environ.get("NETWORK_SINK_POSTGRES", "1") == "1"
        self.sink_neo4j = os.environ.get("NETWORK_SINK_NEO4J", "1") == "1"
        self.sink_rabbitmq = os.environ.get("NETWORK_SINK_RABBITMQ", "1") == "1"
        self.status = "registered"
        self._last: Dict = {}
        self._prev: Dict[str, Dict] = {}
        self._expanded: set = set()  # ARP-discovered IPs auto-added to the scan scope
        self._applied_cfg = ""
        self._lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None

    # ── lifecycle ────────────────────────────────────────────────────────────
    async def register(self) -> PluginMetadata:
        return PluginMetadata(
            name="network",
            version="1.0.0",
            description="Autonomous nmap+SNMP discovery; inventories & monitors found hosts.",
            author="Minder <core@minder.local>",
            capabilities=["collect", "analyze", "discovery", "snmp", "inventory"],
            data_sources=["nmap", "snmp"],
            databases=["postgres", "neo4j", "influxdb", "rabbitmq"],
        )

    async def initialize(self) -> None:
        self.status = "ready"
        # Start the autonomous reconcile loop (only when there is a running loop —
        # i.e. inside the registry, not in a bare unit-test construction).
        if self._task is None and self.interval > 0:
            try:
                self._task = asyncio.get_running_loop().create_task(self._loop())
            except RuntimeError:
                self._task = None

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self.interval)
            try:
                result = await self.reconcile()
                errs = {
                    k: v
                    for k, v in result.get("sinks", {}).items()
                    if v.get("status") in ("error", "partial")
                }
                if errs:
                    logger.warning("network reconcile sink issues: %s", errs)
            except asyncio.CancelledError:  # shutdown → let it propagate
                raise
            except Exception:  # a bad cycle must never kill the loop
                logger.exception("network autonomous reconcile cycle failed")

    async def health_check(self) -> Dict:
        return {
            "healthy": True,
            "targets_configured": bool(self.targets.strip()),
            "nmap": shutil.which("nmap") is not None,
            "snmp": shutil.which("snmpget") is not None,
            "auto_apply": self.auto_apply,
            "interval_s": self.interval,
        }

    async def shutdown(self) -> None:
        self.status = "shutdown"
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    # ── subprocess helper ────────────────────────────────────────────────────
    async def _run(self, *cmd: str, timeout: float = 60.0) -> "tuple[int, str]":
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return proc.returncode or 0, out.decode("utf-8", "replace")
        except (OSError, asyncio.TimeoutError):
            return 1, ""

    # ── discovery backends ───────────────────────────────────────────────────
    async def _nmap_scan(self, hosts: List[str]) -> List[Dict]:
        rc, out = await self._run(
            "nmap",
            "-sT",
            "-sV",
            "-Pn",
            "-p",
            self.ports,
            "--host-timeout",
            _NMAP_HOST_TIMEOUT,
            "-oX",
            "-",
            *hosts,
            timeout=min(len(hosts) * 30 + 30, _NMAP_MAX_TIMEOUT),
        )
        return _parse_nmap_xml(out) if rc == 0 else []

    async def _tcp_fallback(self, hosts: List[str]) -> List[Dict]:
        try:
            port = int(self.ports.split(",")[0])
        except (ValueError, IndexError):
            port = 80
        sem = asyncio.Semaphore(_MAX_CONCURRENCY)

        async def _probe(host: str) -> Dict:
            async with sem:
                writer = None
                open_ = False
                try:
                    _, writer = await asyncio.wait_for(
                        asyncio.open_connection(host, port), timeout=_CONNECT_TIMEOUT
                    )
                    open_ = True
                except (OSError, asyncio.TimeoutError):
                    open_ = False
                finally:
                    if writer is not None:
                        writer.close()
                        try:
                            await writer.wait_closed()
                        except OSError:
                            pass
            return {
                "host": host,
                "hostname": "",
                "state": "up" if open_ else "down",
                "ports": (
                    [
                        {
                            "port": port,
                            "protocol": "tcp",
                            "service": "",
                            "product": "",
                            "version": "",
                        }
                    ]
                    if open_
                    else []
                ),
            }

        return list(await asyncio.gather(*[_probe(h) for h in hosts]))

    # ── SNMP (v2c / v3; system + rich interfaces + host-resources + ARP) ──────
    def _snmp_base_args(self) -> List[str]:
        """Version-specific snmp CLI args (before the -O flags / host / oid)."""
        if self.snmp_version == "3":
            args = ["-v3", "-u", self.snmp_v3_user, "-l", self.snmp_v3_level]
            if self.snmp_v3_level in ("authNoPriv", "authPriv"):
                args += ["-a", self.snmp_v3_auth_proto, "-A", self.snmp_v3_auth_pass]
            if self.snmp_v3_level == "authPriv":
                args += ["-x", self.snmp_v3_priv_proto, "-X", self.snmp_v3_priv_pass]
            return args
        return ["-v2c", "-c", self.snmp_community]

    async def _snmp_get(self, host: str, oid: str) -> Optional[str]:
        rc, out = await self._run(
            "snmpget",
            *self._snmp_base_args(),
            "-Ovq",
            "-t",
            _SNMP_TIMEOUT,
            "-r",
            "0",
            host,
            oid,
            timeout=8.0,
        )
        val = out.strip().strip('"')
        if rc == 0 and val and "No Such" not in val and "No more" not in val:
            return val
        return None

    async def _snmp_walk(self, host: str, oid: str) -> Dict[str, str]:
        """snmpbulkwalk (fast) of a table column → {index: value}."""
        rc, out = await self._run(
            "snmpbulkwalk",
            *self._snmp_base_args(),
            "-Oqn",
            "-t",
            _SNMP_TIMEOUT,
            "-r",
            "0",
            host,
            oid,
            timeout=20.0,
        )
        return _parse_snmpwalk(out, oid) if rc == 0 else {}

    async def _snmp_interfaces(self, host: str) -> List[Dict]:
        descr, itype, speed, mac, oper, alias = await asyncio.gather(
            self._snmp_walk(host, _IF_DESCR_OID),
            self._snmp_walk(host, _IF_TYPE_OID),
            self._snmp_walk(host, _IF_SPEED_OID),
            self._snmp_walk(host, _IF_MAC_OID),
            self._snmp_walk(host, _IF_OPERSTATUS_OID),
            self._snmp_walk(host, _IF_ALIAS_OID),
        )
        result = []
        for idx in sorted(descr, key=lambda k: int(k) if k.isdigit() else 0):
            result.append(
                {
                    "index": idx,
                    "descr": descr.get(idx, ""),
                    "type": itype.get(idx, ""),
                    "speed_bps": speed.get(idx, ""),
                    "mac": _normalize_mac(mac.get(idx, "")),
                    "oper_status": _IF_OPER.get(oper.get(idx, ""), oper.get(idx, "")),
                    "alias": alias.get(idx, ""),
                }
            )
        return result

    async def _snmp_host_resources(self, host: str) -> Dict:
        uptime, memsize, procs, s_descr, s_size, s_used = await asyncio.gather(
            self._snmp_get(host, _HR_UPTIME_OID),
            self._snmp_get(host, _HR_MEMSIZE_OID),
            self._snmp_walk(host, _HR_PROC_LOAD_OID),
            self._snmp_walk(host, _HR_STOR_DESCR_OID),
            self._snmp_walk(host, _HR_STOR_SIZE_OID),
            self._snmp_walk(host, _HR_STOR_USED_OID),
        )
        storage = [
            {"descr": d, "size": s_size.get(i, ""), "used": s_used.get(i, "")}
            for i, d in sorted(
                s_descr.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0
            )
        ]
        hr: Dict = {}
        if uptime:
            hr["uptime"] = uptime
        if memsize:
            hr["memory_kb"] = memsize
        if procs:
            hr["processor_load"] = list(procs.values())
        if storage:
            hr["storage"] = storage
        return hr

    async def _snmp_arp(self, host: str) -> Dict[str, str]:
        return _parse_arp(await self._snmp_walk(host, _ARP_MAC_OID))

    async def _snmp_lookup(self, host: str) -> Dict:
        """Fast-skip non-SNMP hosts (one timed-out sysDescr get); else gather the
        system group, rich interface table, host-resources and ARP concurrently."""
        descr = await self._snmp_get(host, _SNMP_SYSTEM_OIDS["sysDescr"])
        if descr is None:
            return {}
        other = [k for k in _SNMP_SYSTEM_OIDS if k != "sysDescr"]
        sys_vals, interfaces, host_res, arp = await asyncio.gather(
            asyncio.gather(
                *[self._snmp_get(host, _SNMP_SYSTEM_OIDS[k]) for k in other]
            ),
            self._snmp_interfaces(host),
            self._snmp_host_resources(host),
            self._snmp_arp(host),
        )
        system = {"sysDescr": descr}
        system.update({k: v for k, v in zip(other, sys_vals) if v is not None})
        result: Dict = {"system": system, "interfaces": interfaces}
        if host_res:
            result["host_resources"] = host_res
        if arp:
            result["arp"] = arp
        return result

    # ── discovery orchestration ──────────────────────────────────────────────
    def _effective_targets(self) -> str:
        """Configured targets plus any ARP-discovered IPs auto-added to scope."""
        if self._expanded:
            extra = ",".join(sorted(self._expanded))
            return f"{self.targets},{extra}" if self.targets.strip() else extra
        return self.targets

    async def collect_data(self) -> Dict:
        hosts = _expand_targets(self._effective_targets(), self.max_hosts)
        if not hosts:
            self._last = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "targets": self.targets,
                "method": "none",
                "scanned": 0,
                "hosts": [],
            }
            return self._last

        use_nmap = shutil.which("nmap") is not None
        discovered = (
            await self._nmap_scan(hosts)
            if use_nmap
            else await self._tcp_fallback(hosts)
        )
        if self.snmp_enabled and shutil.which("snmpget") is not None:
            live = [h for h in discovered if h.get("state") == "up" or h.get("ports")]
            sem = asyncio.Semaphore(_SNMP_MAX_CONCURRENCY)

            async def _snmp(h: Dict) -> None:
                async with sem:
                    snmp = await self._snmp_lookup(h.get("host", ""))
                if snmp:
                    h["snmp"] = snmp

            await asyncio.gather(*[_snmp(h) for h in live])

        self._last = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "targets": self.targets,
            "method": "nmap" if use_nmap else "tcp-fallback",
            "scanned": len(discovered),
            "hosts": discovered,
        }
        return self._last

    async def scan(self) -> Dict:
        """Action: discover only (no fan-out)."""
        return await self.collect_data()

    # ── the autonomous reconcile: discover → detect change → fan out ──────────
    async def reconcile(self) -> Dict:
        """Action: full cycle — discover, detect changes, write to every enabled
        sink. Serialised so the loop, the registry's hourly call and a manual
        trigger can't overlap."""
        async with self._lock:
            data = await self.collect_data()
            live = [
                h for h in data["hosts"] if h.get("state") == "up" or h.get("ports")
            ]
            curr = _summarize(live)
            changes = _diff_hosts(self._prev, curr)

            # Self-expanding discovery: fold ARP neighbours found inside a configured
            # CIDR into the scan scope for subsequent cycles (bounded by max_hosts).
            expanded_added: List[str] = []
            if self.auto_expand:
                cidrs = _configured_cidrs(self.expand_cidrs)
                already = set(
                    _expand_targets(self._effective_targets(), self.max_hosts)
                )
                for ip in _extract_neighbor_ips(data["hosts"], cidrs):
                    if ip not in already and len(self._expanded) < self.max_hosts:
                        self._expanded.add(ip)
                        expanded_added.append(ip)

            sinks: Dict[str, Dict] = {}
            if self.sink_telegraf and self.auto_apply:
                sinks["telegraf"] = await self._sink_telegraf(live)
            if self.sink_postgres:
                sinks["postgres"] = await self._sink_postgres(live, changes)
            if self.sink_neo4j:
                sinks["neo4j"] = await self._sink_neo4j(live)
            if self.sink_rabbitmq:
                sinks["rabbitmq"] = await self._sink_rabbitmq(changes)

            self._prev = curr
            return {
                "timestamp": data["timestamp"],
                "method": data["method"],
                "live": len(live),
                "changes": changes,
                "expanded_added": expanded_added,
                "expanded_total": len(self._expanded),
                "sinks": sinks,
            }

    # ── sinks (each fails soft — a down backend never breaks the cycle) ───────
    async def _sink_telegraf(self, live: List[Dict]) -> Dict:
        try:
            from core.state import plugin_instances  # registry-only, lazy
        except ImportError:
            return {"status": "unavailable"}
        tg = plugin_instances.get("telegraf")
        if tg is None:
            return {"status": "telegraf-not-loaded"}
        cfg = _telegraf_config(live, self.snmp_community)
        if cfg == self._applied_cfg:
            return {"status": "unchanged"}
        try:
            await tg.set_managed_region(cfg, reload=True)
            self._applied_cfg = cfg
            return {"status": "applied", "bytes": len(cfg)}
        except Exception as e:
            return {"status": "error", "error": f"{type(e).__name__}: {e}"}

    async def _sink_postgres(self, live: List[Dict], changes: Dict) -> Dict:
        try:
            import asyncpg
        except ImportError:
            return {"status": "unavailable"}
        try:
            conn = await asyncpg.connect(
                host=os.environ.get("POSTGRES_HOST", "postgres"),
                port=int(os.environ.get("POSTGRES_PORT", "5432")),
                user=os.environ.get("POSTGRES_USER", "minder"),
                password=os.environ.get("POSTGRES_PASSWORD", ""),
                database=os.environ.get("POSTGRES_DB", "minder"),
                timeout=8,
            )
        except Exception as e:
            return {"status": "error", "error": f"{type(e).__name__}: {e}"}
        try:
            await conn.execute(
                """CREATE TABLE IF NOT EXISTS network_inventory (
                    ip TEXT PRIMARY KEY, hostname TEXT, os TEXT,
                    ports JSONB, snmp JSONB, status TEXT DEFAULT 'up',
                    first_seen TIMESTAMPTZ DEFAULT NOW(),
                    last_seen TIMESTAMPTZ DEFAULT NOW())"""
            )
            for h in live:
                os_str = h.get("snmp", {}).get("system", {}).get("sysDescr", "")
                await conn.execute(
                    """INSERT INTO network_inventory
                         (ip, hostname, os, ports, snmp, status, last_seen)
                       VALUES ($1,$2,$3,$4,$5,'up',NOW())
                       ON CONFLICT (ip) DO UPDATE SET
                         hostname=$2, os=$3, ports=$4, snmp=$5,
                         status='up', last_seen=NOW()""",
                    h.get("host", ""),
                    h.get("hostname", ""),
                    os_str,
                    json.dumps(h.get("ports", [])),
                    json.dumps(h.get("snmp", {})),
                )
            for ip in changes.get("down", []):
                await conn.execute(
                    "UPDATE network_inventory SET status='down' WHERE ip=$1", ip
                )
            return {
                "status": "ok",
                "upserted": len(live),
                "marked_down": len(changes.get("down", [])),
            }
        except Exception as e:
            return {"status": "error", "error": f"{type(e).__name__}: {e}"}
        finally:
            await conn.close()

    async def _sink_neo4j(self, live: List[Dict]) -> Dict:
        auth = os.environ.get("NEO4J_AUTH", "")
        if "/" not in auth:
            return {"status": "no-auth"}
        user, pw = auth.split("/", 1)
        url = os.environ.get("NEO4J_HTTP", "http://neo4j:7474") + "/db/neo4j/tx/commit"
        payload = [
            {
                "host": h.get("host", ""),
                "hostname": h.get("hostname", ""),
                "os": h.get("snmp", {}).get("system", {}).get("sysDescr", ""),
                "ports": [p["port"] for p in h.get("ports", [])],
                "ifaces": [i["descr"] for i in h.get("snmp", {}).get("interfaces", [])],
            }
            for h in live
            if h.get("host")
        ]
        statement = (
            "UNWIND $hosts AS h "
            "MERGE (host:Host {ip: h.host}) "
            "SET host.hostname=h.hostname, host.os=h.os, host.last_seen=timestamp() "
            "FOREACH (p IN h.ports | "
            "  MERGE (s:Service {key: h.host + ':' + toString(p)}) SET s.port=p "
            "  MERGE (host)-[:RUNS]->(s)) "
            "FOREACH (nm IN h.ifaces | "
            "  MERGE (i:Interface {key: h.host + ':' + nm}) SET i.descr=nm "
            "  MERGE (host)-[:HAS_INTERFACE]->(i))"
        )
        try:
            async with httpx.AsyncClient(timeout=12, auth=(user, pw)) as c:
                r = await c.post(
                    url,
                    json={
                        "statements": [
                            {"statement": statement, "parameters": {"hosts": payload}}
                        ]
                    },
                )
            if r.status_code != 200:
                logger.warning("network neo4j sink HTTP %s", r.status_code)
                return {
                    "status": "error",
                    "http_status": r.status_code,
                    "hosts": len(payload),
                }
            try:
                errs = r.json().get("errors", [])
            except ValueError:
                return {
                    "status": "error",
                    "error": "non-JSON response",
                    "hosts": len(payload),
                }
            if errs:
                logger.warning("network neo4j cypher errors: %s", errs)
            return {
                "status": "ok" if not errs else "error",
                "hosts": len(payload),
                "errors": errs,
            }
        except Exception as e:  # log the TYPE only — the message may carry creds
            logger.warning("network neo4j sink failed: %s", type(e).__name__)
            return {"status": "error", "error": f"{type(e).__name__}: {e}"}

    async def _sink_rabbitmq(self, changes: Dict) -> Dict:
        events = [
            (f"network.host.{kind}", ip)
            for kind in ("new", "down", "changed")
            for ip in changes.get(kind, [])
        ]
        if not events:
            return {"status": "no-events"}
        user = os.environ.get("NETWORK_RABBITMQ_USER", "minder")
        pw = os.environ.get("RABBITMQ_PASSWORD", "")
        base = os.environ.get("NETWORK_RABBITMQ_URL", "http://rabbitmq:15672")
        url = base + "/api/exchanges/%2f/amq.topic/publish"
        sent = 0  # accepted by the exchange (HTTP 200)
        routed = 0  # actually delivered to a bound queue (a consumer exists)
        errors = 0  # HTTP-level failures
        try:
            async with httpx.AsyncClient(timeout=8, auth=(user, pw)) as c:
                for routing_key, ip in events:
                    body = {
                        "properties": {},
                        "routing_key": routing_key,
                        "payload": json.dumps({"ip": ip, "event": routing_key}),
                        "payload_encoding": "string",
                    }
                    r = await c.post(url, json=body)
                    if r.status_code != 200:
                        errors += 1
                        continue
                    sent += 1
                    try:
                        if r.json().get("routed"):
                            routed += 1
                    except ValueError:
                        pass
            if errors:
                logger.warning(
                    "network rabbitmq: %d/%d publishes failed (HTTP)",
                    errors,
                    len(events),
                )
            return {
                "status": "ok" if errors == 0 else "partial",
                "events": len(events),
                "sent": sent,
                "routed": routed,
                "errors": errors,
            }
        except Exception as e:  # log the TYPE only — the message may carry creds
            logger.warning("network rabbitmq sink failed: %s", type(e).__name__)
            return {"status": "error", "error": f"{type(e).__name__}: {e}"}

    # ── analysis (read-only view) ─────────────────────────────────────────────
    async def analyze(self) -> Dict:
        hosts = self._last.get("hosts", [])
        live = [h for h in hosts if h.get("state") == "up" or h.get("ports")]
        return {
            "method": self._last.get("method", "none"),
            "live": len(live),
            "scanned": len(hosts),
            "live_hosts": [h.get("host") for h in live],
            "open_ports": {
                h.get("host"): [p["port"] for p in h.get("ports", [])] for h in live
            },
            "snmp": {h["host"]: h["snmp"] for h in live if h.get("snmp")},
            "telegraf_config": _telegraf_config(live, self.snmp_community),
        }

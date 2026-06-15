#!/usr/bin/env python3
"""
IPTV Ultra Pro - Core Probe Engine
OpenWrt LuCI plugin for automatic IPTV source fetching, testing and optimization.
"""
import argparse
import concurrent.futures
import json
import logging
import os
import re
import subprocess
import sys
import time
import urllib.request
import xml.sax
import xml.sax.handler
from collections import defaultdict
from pathlib import Path
from typing import Any

# ─── Constants ───────────────────────────────────────────────────────────────

VERSION = "2.0.0"
IPTV_BASE = "https://iptv-org.github.io/iptv"
COUNTRY_URL = IPTV_BASE + "/countries/{cc}.m3u"
FULL_URL = IPTV_BASE + "/index.m3u"
EPG_URL = "https://epg.iptv-org.github.io/epg.xml"

OUTPUT_DIR = Path("/www/iptv")
STATUS_FILE = Path("/tmp/iptv-ultra-status.json")
CACHE_FILE = Path("/tmp/iptv-ultra-cache.json")
TMP_DIR = Path("/tmp/iptv-ultra")

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"

# Scoring constants
SCORE_4K_1080P = 30
SCORE_720P = 15
SCORE_FAST_START = 20
SCORE_STABLE = 20
PENALTY_STUTTER = -40
PENALTY_AUDIO_ONLY = -80
PENALTY_BLACK_SCREEN = -100
MIN_SCORE = 60

# Default config
DEFAULT_COUNTRIES = ["cn", "hk", "tw"]
DEFAULT_SORT = "hot"
DEFAULT_THREADS = 20

log = logging.getLogger("iptv-ultra")


# ─── Utilities ───────────────────────────────────────────────────────────────

def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(format=LOG_FORMAT, level=level, stream=sys.stderr)


def load_uci_config() -> dict:
    """Load config from /etc/config/iptv-ultra (UCI format)."""
    cfg: dict[str, Any] = {
        "enabled": True,
        "countries": DEFAULT_COUNTRIES[:],
        "sort_by": DEFAULT_SORT,
        "max_threads": DEFAULT_THREADS,
        "min_score": MIN_SCORE,
    }
    config_path = Path("/etc/config/iptv-ultra")
    if not config_path.exists():
        return cfg
    section = None
    for line in config_path.read_text().splitlines():
        line = line.strip()
        if line.startswith("config ") or line.startswith("package "):
            section = "global"
        elif line.startswith("option "):
            parts = line.split()
            if len(parts) >= 3 and section:
                key = parts[1].strip("'\"")
                val = parts[2].strip("'\"")
                if key in ("enabled", "auto_update"):
                    cfg[key] = val == "1"
                elif key == "max_threads":
                    cfg[key] = int(val)
                elif key == "min_score":
                    cfg[key] = int(val)
                else:
                    cfg[key] = val
        elif line.startswith("list "):
            parts = line.split()
            if len(parts) >= 3 and section:
                key = parts[1].strip("'\"")
                val = parts[2].strip("'\"")
                if key == "countries":
                    cfg.setdefault("countries", []).append(val)
    return cfg


def save_status(data: dict):
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    # Also write /www/iptv/status.json for HTTP access
    try:
        status_www = OUTPUT_DIR / "status.json"
        status_www.parent.mkdir(parents=True, exist_ok=True)
        status_www.write_text(json.dumps(data, ensure_ascii=False))
    except OSError:
        pass


def load_status() -> dict:
    if STATUS_FILE.exists():
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    return {
        "version": VERSION,
        "total_channels": 0,
        "success_rate": "0%",
        "failed_today": 0,
        "avg_latency": "0ms",
        "last_update": None,
        "countries": [],
    }


# ─── M3U Download & Parse ───────────────────────────────────────────────────

class M3UEntry:
    def __init__(self, name: str, url: str, tvg_id: str = "", tvg_name: str = "",
                 tvg_logo: str = "", tvg_country: str = "", group: str = ""):
        self.name = name.strip()
        self.url = url.strip()
        self.tvg_id = tvg_id
        self.tvg_name = tvg_name or name.strip()
        self.tvg_logo = tvg_logo
        self.tvg_country = tvg_country.lower() if tvg_country else ""
        self.group = group

    def __repr__(self):
        return f"<M3UEntry {self.name} [{self.tvg_country}]>"


def download_m3u(url: str, timeout: int = 30) -> str | None:
    """Download an M3U playlist, return content or None on failure."""
    try:
        log.info("Downloading: %s", url)
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "*/*",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            # Try UTF-8, fall back to latin-1
            try:
                return data.decode("utf-8")
            except UnicodeDecodeError:
                return data.decode("latin-1")
    except Exception as e:
        log.warning("Download failed for %s: %s", url, e)
        return None


def parse_m3u(content: str) -> list[M3UEntry]:
    """Parse Extended M3U content into M3UEntry list."""
    entries: list[M3UEntry] = []
    current_attrs: dict[str, str] = {}
    lines = content.splitlines()

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("#EXTM3U"):
            continue
        if line.startswith("#EXTINF:"):
            # Parse attributes
            current_attrs = {}
            # Remove #EXTINF:-1 or #EXTINF:-1 tvg-id="..."
            rest = line.split(",", 1)
            if len(rest) >= 1:
                attr_part = rest[0]
                # Extract tvg-id, tvg-name, tvg-logo, tvg-country, group-title
                for attr_match in re.finditer(r'(\w+)="([^"]*)"', attr_part):
                    key = attr_match.group(1)
                    val = attr_match.group(2)
                    current_attrs[key] = val
                # The name after the last comma
                if len(rest) >= 2:
                    current_attrs["_name"] = rest[1].strip()
            continue
        if line.startswith("#"):
            continue

        # This is a URL line
        if not current_attrs:
            continue

        name = current_attrs.get("_name", "Unknown")
        # Skip empty URLs
        if not line or line.startswith("#"):
            continue

        entry = M3UEntry(
            name=name,
            url=line,
            tvg_id=current_attrs.get("tvg-id", ""),
            tvg_name=current_attrs.get("tvg-name", ""),
            tvg_logo=current_attrs.get("tvg-logo", ""),
            tvg_country=current_attrs.get("tvg-country", ""),
            group=current_attrs.get("group-title", ""),
        )
        entries.append(entry)
        current_attrs = {}

    return entries


# ─── FFmpeg Prober ───────────────────────────────────────────────────────────

class ProbeResult:
    def __init__(self, entry: M3UEntry):
        self.entry = entry
        self.success = False
        self.resolution = "unknown"
        self.width = 0
        self.height = 0
        self.fps = 0
        self.has_video = False
        self.has_audio = False
        self.startup_time = 999.0
        self.errors: list[str] = []
        self.stutter = False
        self.audio_only = False
        self.black_screen = False
        self.latency = 999.0
        self.score = 0
        self.raw_output = ""

    def to_dict(self) -> dict:
        return {
            "name": self.entry.name,
            "url": self.entry.url,
            "tvg_id": self.entry.tvg_id,
            "tvg_logo": self.entry.tvg_logo,
            "resolution": self.resolution,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "has_video": self.has_video,
            "has_audio": self.has_audio,
            "startup_time": round(self.startup_time, 2),
            "latency": round(self.latency, 2),
            "success": self.success,
            "stutter": self.stutter,
            "audio_only": self.audio_only,
            "black_screen": self.black_screen,
            "score": self.score,
            "errors": self.errors[:3],
        }


def probe_stream(entry: M3UEntry, timeout: int = 15) -> ProbeResult:
    """Probe a single stream URL using ffmpeg."""
    result = ProbeResult(entry)
    url = entry.url

    cmd = [
        "ffmpeg", "-v", "info",
        "-i", url,
        "-t", "5",
        "-f", "null",
        "-",
    ]

    start = time.time()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        wall_time = time.time() - start
        output = proc.stderr + "\n" + proc.stdout
        result.raw_output = output[:2000]  # keep last 2KB for analysis
        result.latency = round(wall_time, 2)

        # Parse output for stream info
        result._parse_stream_info(output, wall_time)

        # Determine score
        result.score = result._calculate_score()

    except subprocess.TimeoutExpired:
        result.errors.append("timeout")
        result.latency = timeout
    except FileNotFoundError:
        log.error("ffmpeg not found! Install with: opkg install ffmpeg ffprobe")
        result.errors.append("ffmpeg_missing")
    except Exception as e:
        result.errors.append(str(e)[:100])

    return result


def _probe_worker(entry: M3UEntry, timeout: int = 15) -> ProbeResult | None:
    """Worker function for threading."""
    return probe_stream(entry, timeout)


# ProbeResult methods (defined as mixin-style via monkey-patch or inline)

def _parse_stream_info(self: ProbeResult, output: str, wall_time: float):
    """Parse ffmpeg output to extract stream metadata."""
    # Detect video stream
    video_match = re.search(r"Stream #\d+:\d+.*Video:\s*(\S+)", output)
    audio_match = re.search(r"Stream #\d+:\d+.*Audio:\s*(\S+)", output)

    self.has_video = video_match is not None
    self.has_audio = audio_match is not None

    # Resolution
    res_match = re.search(r"(\d{3,4})x(\d{3,4})", output)
    if res_match:
        self.width = int(res_match.group(1))
        self.height = int(res_match.group(2))
        if self.height >= 2160:
            self.resolution = "4K"
        elif self.height >= 1080:
            self.resolution = "1080p"
        elif self.height >= 720:
            self.resolution = "720p"
        elif self.height >= 540:
            self.resolution = "540p"
        elif self.height >= 480:
            self.resolution = "480p"
        else:
            self.resolution = f"{self.height}p"
    else:
        self.resolution = "unknown"

    # FPS
    fps_match = re.search(r"(\d+)\s*fps", output)
    if fps_match:
        self.fps = int(fps_match.group(1))

    # Frame count to detect black screen / stutter
    frame_match = re.search(r"frame=\s*(\d+)", output)
    frames = int(frame_match.group(1)) if frame_match else 0

    # Detect audio-only (no video stream)
    if not self.has_video:
        self.audio_only = True

    # Detect black screen (has video stream but 0 or very few frames)
    if self.has_video and frames < 5:
        self.black_screen = True

    # Detect stutter / errors
    error_patterns = [
        "Invalid data", "buffer underflow", "packet loss",
        "corrupt", "broken", "Error while decoding",
        "Header missing", "Could not find codec",
        "Invalid frame", " discontinuity ",
    ]
    for pattern in error_patterns:
        if re.search(pattern, output, re.IGNORECASE):
            self.errors.append(pattern)
            self.stutter = True

    # Count error/warning lines
    error_count = len(re.findall(r"(?i)\berror\b", output))
    if error_count > 2:
        self.errors.append(f"{error_count} errors")

    # Actually run for 5 seconds with -t 5
    # Wall time minus 5s ≈ startup time
    # For live streams, ffmpeg reads 5s of content, so:
    # wall_time ≈ startup_time + 5s (+ decode overhead)
    self.startup_time = max(0, wall_time - 5.5)

    # Check return code - non-zero means failure
    # (but we do this via the subprocess.run returncode)

    # Also check for successful frame decoding
    # If we got frames and have no fatal errors, consider it successful
    if self.has_video and frames >= 5:
        self.success = True
    elif frames > 0 and self.has_video:
        self.success = True
    # Audio-only with audio data
    elif self.has_audio and not self.has_video:
        self.success = False


def _calculate_score(self: ProbeResult) -> int:
    """Calculate quality score 0-100."""
    if not self.success:
        return 0
    if self.audio_only:
        return max(0, SCORE_4K_1080P + PENALTY_AUDIO_ONLY)  # will be ≤ 0
    if self.black_screen:
        return max(0, SCORE_4K_1080P + PENALTY_BLACK_SCREEN)

    score = 50  # base

    # Resolution bonus
    if self.resolution in ("4K", "1080p"):
        score += SCORE_4K_1080P
    elif self.resolution == "720p":
        score += SCORE_720P
    elif self.resolution in ("540p", "480p"):
        score += 5

    # Startup time bonus
    if self.startup_time < 2.0:
        score += SCORE_FAST_START
    elif self.startup_time < 4.0:
        score += 10

    # Stable stream
    if not self.stutter and not self.errors:
        score += SCORE_STABLE
    elif self.stutter:
        score += PENALTY_STUTTER

    return max(0, min(100, score))


# Attach methods to ProbeResult
ProbeResult._parse_stream_info = _parse_stream_info
ProbeResult._calculate_score = _calculate_score


# ─── Prober Pool ─────────────────────────────────────────────────────────────

class ProberPool:
    """Multi-threaded ffmpeg probe pool."""

    def __init__(self, max_workers: int = 20, probe_timeout: int = 15):
        self.max_workers = max_workers
        self.probe_timeout = probe_timeout
        self.cache: dict[str, ProbeResult] = {}
        self._load_cache()

    def _load_cache(self):
        if CACHE_FILE.exists():
            try:
                data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
                for url, d in data.items():
                    entry = M3UEntry(
                        d.get("name", ""), url,
                        tvg_id=d.get("tvg_id", ""),
                        tvg_logo=d.get("tvg_logo", ""),
                    )
                    pr = ProbeResult(entry)
                    pr.success = d.get("success", False)
                    pr.resolution = d.get("resolution", "unknown")
                    pr.width = d.get("width", 0)
                    pr.height = d.get("height", 0)
                    pr.fps = d.get("fps", 0)
                    pr.has_video = d.get("has_video", False)
                    pr.has_audio = d.get("has_audio", False)
                    pr.startup_time = d.get("startup_time", 999)
                    pr.latency = d.get("latency", 999)
                    pr.score = d.get("score", 0)
                    pr.stutter = d.get("stutter", False)
                    pr.audio_only = d.get("audio_only", False)
                    pr.black_screen = d.get("black_screen", False)
                    pr.errors = d.get("errors", [])
                    pr.raw_output = ""
                    self.cache[url] = pr
                log.info("Loaded %d cached results", len(self.cache))
            except Exception as e:
                log.warning("Cache load failed: %s", e)

    def _save_cache(self):
        try:
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {}
            for url, pr in self.cache.items():
                data[url] = pr.to_dict()
            CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            log.warning("Cache save failed: %s", e)

    def probe_all(self, entries: list[M3UEntry]) -> list[ProbeResult]:
        """Probe all entries, using cache for previously tested URLs."""
        log.info("Probing %d streams with %d threads...", len(entries), self.max_workers)
        to_probe: list[M3UEntry] = []
        results: list[ProbeResult] = []

        for entry in entries:
            if entry.url in self.cache:
                results.append(self.cache[entry.url])
            else:
                to_probe.append(entry)

        log.info("%d cached, %d to probe", len(results), len(to_probe))

        if to_probe:
            new_results = self._probe_batch(to_probe)
            for pr in new_results:
                if pr:
                    self.cache[pr.entry.url] = pr
                    results.append(pr)
            self._save_cache()

        return results

    def _probe_batch(self, entries: list[M3UEntry]) -> list[ProbeResult]:
        results: list[ProbeResult] = []
        n = len(entries)
        done = 0
        log.debug("Pool workers: %d", self.max_workers)
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            fut_map = {
                ex.submit(_probe_worker, entry, self.probe_timeout): entry
                for entry in entries
            }
            for future in concurrent.futures.as_completed(fut_map):
                done += 1
                entry = fut_map[future]
                try:
                    pr = future.result()
                    if pr:
                        results.append(pr)
                        if pr.success:
                            log.info("[%d/%d] ✓ %s → %s score=%d",
                                     done, n, entry.name[:30], pr.resolution, pr.score)
                        else:
                            log.info("[%d/%d] ✗ %s → failed", done, n, entry.name[:30])
                except Exception as e:
                    log.error("Probe failed for %s: %s", entry.name, e)
        return results


# ─── Channel Aggregator ──────────────────────────────────────────────────────

def normalize_channel_name(name: str) -> str:
    """Normalize channel name for grouping."""
    name = name.strip()
    # Remove common suffixes like " HD", " FHD", " 4K", " UHD"
    name = re.sub(r'\s+(HD|FHD|4K|UHD|HDR|60fps|50fps)$', '', name, flags=re.IGNORECASE)
    # Remove leading/trailing special chars
    name = name.strip(" -|")
    return name.lower()


def aggregate_channels(results: list[ProbeResult], min_score: int = 60) -> list[ProbeResult]:
    """Group by normalized channel name, keep highest score * resolution per group."""
    groups: dict[str, list[ProbeResult]] = defaultdict(list)
    for pr in results:
        key = normalize_channel_name(pr.entry.name)
        groups[key].append(pr)

    aggregated: list[ProbeResult] = []
    removed_count = 0
    for ch_name, group in groups.items():
        # Filter by minimum score
        valid = [pr for pr in group if pr.score >= min_score and pr.success]
        if not valid:
            removed_count += len(group)
            continue

        # Score by: score first, then resolution quality, then startup time
        def sort_key(pr: ProbeResult):
            res_order = {"4K": 4, "1080p": 3, "720p": 2, "unknown": 1}
            return (pr.score, res_order.get(pr.resolution, 0), -pr.startup_time)

        valid.sort(key=sort_key, reverse=True)
        best = valid[0]
        # Keep the original display name
        if best.entry.name != ch_name and group[0].entry.name.strip():
            best.entry.name = group[0].entry.name  # Use first entry's exact name
        aggregated.append(best)
        removed_count += len(group) - 1

    log.info("Aggregation: %d inputs → %d output (removed %d duplicates/low-score)",
             len(results), len(aggregated), removed_count)
    return aggregated


# ─── Sorting ─────────────────────────────────────────────────────────────────

def hot_score(pr: ProbeResult) -> float:
    """Calculate 'heat' score for sorting."""
    # Base from probe quality
    base = pr.score / 100.0  # 0-1
    # Resolution bonus
    res_bonus = {"4K": 0.2, "1080p": 0.15, "720p": 0.1, "unknown": 0}.get(pr.resolution, 0)
    # Latency penalty (0-1, lower is better)
    latency_score = max(0, 1.0 - pr.latency / 30.0)
    # Startup bonus
    startup_score = 0.2 if pr.startup_time < 2.0 else (0.1 if pr.startup_time < 4.0 else 0)
    return base + res_bonus + latency_score * 0.15 + startup_score


def sort_channels(results: list[ProbeResult], sort_by: str) -> list[ProbeResult]:
    """Sort channels according to user preference."""
    if sort_by == "latency":
        return sorted(results, key=lambda r: r.latency)
    elif sort_by == "resolution":
        res_order = {"4K": 0, "1080p": 1, "720p": 2, "unknown": 3}
        return sorted(results, key=lambda r: (res_order.get(r.resolution, 9), -r.score))
    else:  # "hot" - default
        return sorted(results, key=lambda r: hot_score(r), reverse=True)


# ─── Output Generation ───────────────────────────────────────────────────────

def generate_m3u(channels: list[ProbeResult], name: str) -> str:
    """Generate M3U playlist content."""
    lines = [
        "#EXTM3U",
        f"#PLAYLIST: IPTV Ultra Pro - {name}",
        f"#GENERATED: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"#SOURCE: iptv-org",
        f"#TOTAL: {len(channels)}",
        "",
    ]
    for ch in channels:
        tvg_id = ch.entry.tvg_id or ""
        tvg_name = ch.entry.tvg_name or ch.entry.name
        tvg_logo = ch.entry.tvg_logo or ""
        res_tag = f' resolution="{ch.resolution}"' if ch.resolution != "unknown" else ""
        score_tag = f' score="{ch.score}"'
        extinf = f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{tvg_name}" tvg-logo="{tvg_logo}"{res_tag}{score_tag} group-title="IPTV Ultra",{ch.entry.name}'
        lines.append(extinf)
        lines.append(ch.entry.url)
        lines.append("")
    return "\n".join(lines)


def write_output_files(channels: list[ProbeResult], epg_path: Path | None = None):
    """Write all output M3U files."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # best.m3u - all channels sorted by quality
    content = generate_m3u(channels, "Best Quality")
    (OUTPUT_DIR / "best.m3u").write_text(content, encoding="utf-8")
    log.info("Wrote best.m3u with %d channels", len(channels))

    # hd.m3u - only HD channels (720p+)
    hd = [ch for ch in channels if ch.resolution in ("720p", "1080p", "4K")]
    content = generate_m3u(hd, "HD Quality")
    (OUTPUT_DIR / "hd.m3u").write_text(content, encoding="utf-8")
    log.info("Wrote hd.m3u with %d channels", len(hd))

    # clean.m3u - all channels (no score filter applied, but passes basic checks)
    content = generate_m3u(channels, "Clean List")
    (OUTPUT_DIR / "clean.m3u").write_text(content, encoding="utf-8")
    log.info("Wrote clean.m3u with %d channels", len(channels))


# ─── EPG Sync ────────────────────────────────────────────────────────────────

class EPGHandler(xml.sax.handler.ContentHandler):
    """SAX handler for streaming EPG XML parsing."""

    def __init__(self, channel_ids: set[str]):
        self.channel_ids = channel_ids
        self.in_channel = False
        self.in_programme = False
        self.current_tag = ""
        self.buffer = ""
        self.output_lines: list[str] = []
        self._channel_match = False

    def startElement(self, tag, attrs):
        self.current_tag = tag
        self.buffer = ""
        if tag == "tv":
            self.output_lines.append('<?xml version="1.0" encoding="UTF-8"?>')
            self.output_lines.append('<tv>')
        elif tag == "channel":
            ch_id = attrs.get("id", "")
            self._channel_match = ch_id in self.channel_ids
            self.in_channel = self._channel_match
            if self._channel_match:
                self.output_lines.append(f'<channel id="{ch_id}">')
        elif tag == "programme":
            ch_id = attrs.get("channel", "")
            self._channel_match = ch_id in self.channel_ids
            self.in_programme = self._channel_match
            if self._channel_match:
                start = attrs.get("start", "")
                stop = attrs.get("stop", "")
                self.output_lines.append(f'<programme channel="{ch_id}" start="{start}" stop="{stop}">')

    def endElement(self, tag):
        if tag == "channel" and self._channel_match:
            self.output_lines.append("</channel>")
            self._channel_match = False
        self.in_channel = False
        if tag == "programme" and self._channel_match:
            self.output_lines.append("</programme>")
            self._channel_match = False
        self.in_programme = False
        if tag == "tv":
            self.output_lines.append("</tv>")

    def characters(self, content):
        if self._channel_match and self.in_channel:
            self.output_lines.append(f"<{self.current_tag}>{content.strip()}</{self.current_tag}>")


def fetch_epg(channels: list[ProbeResult]) -> Path | None:
    """Fetch EPG, filter for our channels, write trimmed XML."""
    channel_ids = {ch.entry.tvg_id for ch in channels if ch.entry.tvg_id}
    if not channel_ids:
        log.warning("No tvg-id available, skipping EPG")
        return None

    log.info("Fetching EPG from %s (filtering %d channels)...", EPG_URL, len(channel_ids))
    try:
        req = urllib.request.Request(EPG_URL, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Encoding": "gzip",
        })
        # Download to temp file first (EPG can be 50MB+)
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        epg_tmp = TMP_DIR / "epg_raw.xml"
        urllib.request.urlretrieve(EPG_URL, epg_tmp)
        log.info("EPG downloaded (%d bytes)", epg_tmp.stat().st_size)

        # SAX parse
        handler = EPGHandler(channel_ids)
        parser = xml.sax.make_parser()
        parser.setContentHandler(handler)
        parser.parse(str(epg_tmp))

        # Write filtered EPG
        epg_out = OUTPUT_DIR / "epg.xml"
        epg_out.write_text("\n".join(handler.output_lines), encoding="utf-8")
        log.info("Wrote filtered EPG (%d lines)", len(handler.output_lines))
        epg_tmp.unlink(missing_ok=True)
        return epg_out

    except Exception as e:
        log.warning("EPG sync failed: %s", e)
        return None


# ─── Main ────────────────────────────────────────────────────────────────────

def cmd_update(args):
    """Main update command: download → probe → aggregate → output."""
    cfg = load_uci_config()
    countries = args.countries or cfg.get("countries", DEFAULT_COUNTRIES)
    sort_by = args.sort_by or cfg.get("sort_by", DEFAULT_SORT)
    max_threads = args.threads or cfg.get("max_threads", DEFAULT_THREADS)
    min_score = args.min_score or cfg.get("min_score", MIN_SCORE)

    log.info("IPTV Ultra Pro v%s Update", VERSION)
    log.info("Countries: %s | Sort: %s | Threads: %d | MinScore: %d",
             ",".join(countries), sort_by, max_threads, min_score)

    # 1. Download M3U
    all_entries: list[M3UEntry] = []
    for cc in countries:
        cc = cc.strip().lower()
        url = COUNTRY_URL.format(cc=cc)
        content = download_m3u(url)
        if content:
            entries = parse_m3u(content)
            for e in entries:
                e.tvg_country = cc
            all_entries.extend(entries)
            log.info("  %s: %d channels", cc.upper(), len(entries))
        else:
            log.warning("  %s: download failed", cc.upper())

    if not all_entries:
        log.error("No channels downloaded!")
        sys.exit(1)

    log.info("Total entries: %d", len(all_entries))

    # 2. Deduplicate URLs before probing
    seen_urls: set[str] = set()
    unique_entries: list[M3UEntry] = []
    for e in all_entries:
        if e.url not in seen_urls:
            seen_urls.add(e.url)
            unique_entries.append(e)
    log.info("Unique URLs: %d", len(unique_entries))

    # 3. Probe all streams
    prober = ProberPool(max_workers=max_threads)
    results = prober.probe_all(unique_entries)

    # 4. Aggregate channels
    channels = aggregate_channels(results, min_score=min_score)

    # 5. Sort
    channels = sort_channels(channels, sort_by)

    # 6. Status tracking
    total = len(results)
    success_count = sum(1 for r in results if r.success)
    failed_count = total - success_count
    avg_latency = sum(r.latency for r in results if r.success) / max(success_count, 1)

    status = {
        "version": VERSION,
        "total_channels": len(channels),
        "total_probed": total,
        "success_count": success_count,
        "failed_today": failed_count,
        "success_rate": f"{int(success_count / max(total, 1) * 100)}%",
        "avg_latency": f"{int(avg_latency * 1000)}ms",
        "last_update": time.strftime("%Y-%m-%d %H:%M:%S"),
        "countries": countries,
    }
    save_status(status)

    # 7. Write output
    write_output_files(channels)

    # 8. Fetch EPG
    fetch_epg(channels)

    # 9. Summary
    log.info("=" * 50)
    log.info("UPDATE COMPLETE")
    log.info("  Total probed:   %d", total)
    log.info("  Successful:     %d", success_count)
    log.info("  Failed:         %d", failed_count)
    log.info("  Final channels: %d", len(channels))
    log.info("  Avg latency:    %.1fs", avg_latency)
    log.info("  Output:         %s", OUTPUT_DIR)
    log.info("=" * 50)


def cmd_status(args):
    """Print status information."""
    status = load_status()
    print(json.dumps(status, indent=2, ensure_ascii=False))


def cmd_clear(args):
    """Clear cache and output files."""
    log.info("Clearing cache and output...")
    if CACHE_FILE.exists():
        CACHE_FILE.unlink()
    if STATUS_FILE.exists():
        STATUS_FILE.unlink()
    for f in OUTPUT_DIR.glob("*"):
        if f.suffix in (".m3u", ".xml", ".json"):
            f.unlink(missing_ok=True)
    log.info("Cleared.")


def cmd_list_countries(args):
    """List supported countries from iptv-org categories."""
    log.info("Fetching country list from iptv-org...")
    # Use the country index
    url = "https://iptv-org.github.io/iptv/countries/"
    # Alternative: use the channels.json index
    try:
        req = urllib.request.Request("https://iptv-org.github.io/api/channels.json",
                                     headers={"User-Agent": "IPTV-Ultra-Pro/2.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            channels = json.loads(resp.read())
        countries = set()
        for ch in channels:
            if ch.get("country"):
                countries.add((ch["country"]["code"].lower(), ch["country"]["name"]))
        # Also try to get country codes from the playlist categories
        content = download_m3u("https://iptv-org.github.io/iptv/index.m3u", timeout=15)
        if content:
            for m in re.finditer(r'tvg-country="([^"]+)"', content):
                countries.add((m.group(1).lower(), m.group(1).upper()))

        # Try /countries/ endpoint
        try:
            req2 = urllib.request.Request(
                "https://iptv-org.github.io/iptv/index.country.m3u",
                headers={"User-Agent": "IPTV-Ultra-Pro/2.0"},
            )
            with urllib.request.urlopen(req2, timeout=10) as resp2:
                data = resp2.read().decode()
                for line in data.splitlines():
                    if line.startswith("#EXTINF"):
                        m = re.search(r'tvg-country="([^"]+)"', line)
                        if m:
                            cc = m.group(1).lower()
                            countries.add((cc, cc.upper()))
        except Exception:
            pass

        sorted_countries = sorted(countries, key=lambda x: x[1])
        print(f"\nSupported countries ({len(sorted_countries)}):\n")
        for code, name in sorted_countries:
            print(f"  {code.upper():4s}  {name}")
        print()
    except Exception as e:
        log.error("Failed to fetch country list: %s", e)
        print("Common countries: cn, hk, tw, us, jp, kr, gb, de, fr, ca, au, in")


def main():
    parser = argparse.ArgumentParser(description="IPTV Ultra Pro v%s" % VERSION)
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    sub = parser.add_subparsers(dest="command", help="Command")

    # update
    p_update = sub.add_parser("update", help="Full update: download → probe → output")
    p_update.add_argument("-c", "--countries", nargs="+", default=None, help="Country codes")
    p_update.add_argument("-s", "--sort-by", default=None, choices=["hot", "latency", "resolution"])
    p_update.add_argument("-t", "--threads", type=int, default=None, help="Max probe threads")
    p_update.add_argument("-m", "--min-score", type=int, default=None, help="Minimum score (0-100)")

    # status
    sub.add_parser("status", help="Show status")

    # clear
    sub.add_parser("clear", help="Clear cache and outputs")

    # list-countries
    sub.add_parser("list-countries", help="List supported countries")

    args = parser.parse_args()
    setup_logging(args.verbose if hasattr(args, "verbose") and args.verbose else False)

    if args.command == "update":
        cmd_update(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "clear":
        cmd_clear(args)
    elif args.command == "list-countries":
        cmd_list_countries(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

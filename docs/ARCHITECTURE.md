# IPTV Ultra Pro - Architecture Documentation

## System Overview

IPTV Ultra Pro is a comprehensive OpenWrt LuCI plugin designed to automatically fetch, test, optimize, and serve high-quality IPTV streams. The system consists of multiple components working in harmony:

```
┌─────────────────────────────────────────────────────────┐
│                    LuCI Web Interface                    │
│         (Services → IPTV Ultra Pro Dashboard)           │
└───────────────┬─────────────────────────────────────────┘
                │
        ┌───────▼───────┐
        │  UCI Config   │
        │ (iptv-ultra)  │
        └───────┬───────┘
                │
┌───────────────▼────────────────────────────────────────┐
│          Main Control Script (iptv-ultra.sh)           │
│  - Orchestrates workflow                               │
│  - Manages cron tasks                                  │
│  - Handles HTTP service                                │
└───┬────────────┬────────────┬────────────┬─────────────┘
    │            │            │            │
    ▼            ▼            ▼            ▼
  ┌────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
  │Fetch│  │  Test   │  │Aggregate │  │Generate  │
  │IPTV │  │ Streams │  │ Channels │  │  Output  │
  └────┘  └──────────┘  └──────────┘  └──────────┘
    │            │            │            │
    ▼            ▼            ▼            ▼
┌─────────────────────────────────────────────────────────┐
│              Backend Services (Python)                   │
│                                                          │
│  iptv-probe.py              - FFmpeg stream testing     │
│  channel-aggregator.py      - Channel deduplication     │
│  country-filter.py          - Country-based filtering   │
│  epg-sync.py                - EPG synchronization       │
└────────────┬────────────────────────────┬───────────────┘
             │                            │
    ┌────────▼──────────┐    ┌───────────▼────────┐
    │  Data Storage     │    │  HTTP Server       │
    │  (/var/lib/iptv)  │    │  (Uhttpd module)   │
    │  - cache.db       │    │  - /iptv/*         │
    │  - channels.json  │    │  - /iptv/status    │
    │  - stats.json     │    └────────────────────┘
    └─────────┬─────────┘
              │
    ┌─────────▼─────────────────┐
    │  Output Files             │
    │  - best.m3u (Top quality) │
    │  - hd.m3u (720p+)         │
    │  - clean.m3u (All valid)  │
    │  - epg.xml (EPG data)     │
    └───────────────────────────┘
```

## Component Details

### 1. LuCI Web Interface

**Location**: `/usr/lib/lua/luci/`

#### Controllers
- `controller/iptv_ultra.lua` - RPC endpoints for frontend
  - `action_status()` - Get current system status
  - `action_update()` - Trigger source update
  - `action_get_config()` - Retrieve configuration
  - `action_set_config()` - Save configuration
  - `action_test_stream()` - Manual stream test

#### CBI Models
- `model/cbi/iptv_config.lua` - Configuration form
  - Country selection (multi-checkbox)
  - Sorting options (popularity, latency, resolution)
  - Quality threshold (0-100 slider)
  - Update schedule (cron time picker)
  - Output format options

- `model/cbi/iptv_status.lua` - Status monitoring
  - Real-time channel count
  - Success rate percentage
  - Average latency
  - Last update timestamp
  - Failed sources today
  - Top channels by popularity

### 2. Main Control Script (iptv-ultra.sh)

**Location**: `/usr/bin/iptv-ultra`

**Responsibilities**:
```bash
# Workflow orchestration
iptv-ultra update          # Full source update cycle
iptv-ultra test [url]      # Test single stream
iptv-ultra clean           # Cleanup invalid sources
iptv-ultra config [key]    # Read UCI config
iptv-ultra status          # JSON status output
```

**Main workflow**:
1. Read configuration from UCI
2. Fetch IPTV source list (with caching)
3. Filter by selected countries
4. Launch parallel ffmpeg probes
5. Aggregate duplicate channels
6. Sort by quality metrics
7. Generate output files
8. Update HTTP service

### 3. FFmpeg Probe Engine (iptv-probe.py)

**Location**: `/usr/bin/iptv-probe.py`

**Features**:
- Concurrent stream testing (thread pool)
- Timeout handling (5-second probe window)
- Quality detection from ffmpeg output
- Resolution parsing (4K, 1080p, 720p)
- Error classification
- Performance metric extraction

**Scoring Algorithm**:
```python
score = 0

# Resolution bonus
if resolution == '4K' or '2160p':
    score += 30
elif resolution == '1080p':
    score += 30
elif resolution == '720p':
    score += 15

# Startup time bonus
if startup_time < 2.0:
    score += 20
elif startup_time < 4.0:
    score += 10

# Stability check
if no_errors and no_buffering:
    score += 20

# Error penalties
if is_audio_only:
    score -= 80
if is_black_screen:
    score -= 100
if has_buffering:
    score -= 40

return max(0, score)
```

### 4. Channel Aggregator (channel-aggregator.py)

**Location**: `/usr/bin/channel-aggregator.py`

**Purpose**: Deduplicate channels with same name

**Logic**:
```
For each unique channel name:
  - Collect all URLs
  - Select URL with:
    1. Highest quality score
    2. Highest resolution
    3. Lowest latency
  - Keep only best URL
```

### 5. Country Filter (country-filter.py)

**Location**: `/usr/bin/country-filter.py`

**Supported Countries**:
- Asia: CN, HK, TW, JP, KR, TH, VN, SG, MY, PH
- Americas: US, CA, MX, BR, AR, CL, CO
- Europe: GB, DE, FR, IT, ES, NL, RU, UA
- And 180+ more

**Filtering by**:
- ISO country code
- Region
- Language

### 6. EPG Synchronization (epg-sync.py)

**Location**: `/usr/bin/epg-sync.py`

**Features**:
- Fetch EPG from iptv-org
- Match channels with EPG data
- Generate XML output
- Cache EPG locally

## Data Flow

### Source Fetching
```
1. HTTP GET https://iptv-org.github.io/iptv/index.m3u
2. Parse M3U format
3. Extract metadata (name, logo, country)
4. Store in cache
```

### Stream Testing
```
1. Read cached sources
2. Filter by selected countries
3. Create test queue
4. Parallel ffmpeg probes (20-50 threads)
5. Collect results
6. Score each stream
7. Filter score >= 60
```

### Channel Aggregation
```
1. Group by channel name
2. For each group:
   - Sort by score DESC
   - Select top 1
3. Output deduplicated list
```

### Output Generation
```
1. Generate M3U8 playlists:
   - best.m3u     (score >= 80)
   - hd.m3u       (score >= 60, resolution >= 720p)
   - clean.m3u    (all valid, score >= 60)

2. Generate EPG XML

3. Write to /var/lib/iptv/output/
```

## Performance Optimization

### Caching Strategy
```
/var/lib/iptv/
├── cache/
│   ├── sources.m3u      (24h TTL)
│   ├── channels.json    (48h TTL)
│   └── epg.xml          (24h TTL)
└── output/
    ├── best.m3u        (live)
    ├── hd.m3u          (live)
    ├── clean.m3u       (live)
    └── epg.xml         (live)
```

### Parallel Processing
- Thread pool: 20-50 concurrent ffmpeg probes
- Queue-based job distribution
- Timeout protection (5s per stream)
- CPU throttling awareness

### Resource Management
- Memory: ~200MB peak (stream testing)
- Disk: ~50MB (cache + output)
- CPU: 15-30% (during probe phase)
- Network: Adaptive based on router capacity

## Integration Points

### OpenWrt Integration
```
/etc/init.d/iptv-ultra   → Service control
/etc/config/iptv-ultra   → UCI configuration
/etc/cron.d/iptv-ultra   → Scheduled updates
/etc/uhttpd.conf         → HTTP service routing
```

### HTTP Service
```
Uhttpd module configuration:
- Listen on port 80 (standard)
- Route /iptv/* to /var/lib/iptv/output/
- Enable caching headers
- GZIP compression enabled
```

## Security Considerations

1. **Input Validation**: All URLs validated before ffmpeg execution
2. **Process Isolation**: Separate user for probing (nobody)
3. **File Permissions**: Output world-readable, config readable-owner-only
4. **Timeout Protection**: Hard 5-second limit per stream
5. **URL Blacklist**: Malicious URL pattern detection

## Error Handling

### Graceful Degradation
```
- Network error → Use cached sources
- FFmpeg unavailable → Skip testing, use as-is
- EPG fetch failed → Generate without EPG
- Corrupted cache → Automatic cleanup and refresh
```

### Recovery Mechanisms
```
- Automatic retry (exponential backoff)
- Partial source publication (don't block)
- Rollback to previous working version
- Alert user via LuCI notifications
```

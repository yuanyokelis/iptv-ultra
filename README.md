# IPTV Ultra Pro - OpenWrt LuCI Plugin

Automated IPTV source fetching, testing, and optimization system for OpenWrt routers.

## Features

✨ **Core Capabilities:**
- Automatic IPTV source fetching from iptv-org
- Country-based filtering and multi-selection
- FFmpeg-based stream quality testing
- Intelligent channel aggregation and optimization
- Heat-based sorting (popularity, reliability, latency)
- EPG (Electronic Program Guide) support
- Web-based LuCI management interface
- HTTP service for m3u and XML exports
- Scheduled auto-update via cron
- Support for APK and OPKG package systems

## Project Structure

```
iptv-ultra/
├── docs/                          # Documentation
│   ├── ARCHITECTURE.md
│   ├── INSTALLATION.md
│   └── API_REFERENCE.md
│
├── src/
│   ├── backend/                   # Backend services
│   │   ��── iptv-ultra.sh         # Main control script
│   │   ├── iptv-probe.py         # FFmpeg testing engine
│   │   ├── channel-aggregator.py # Channel deduplication
│   │   ├── country-filter.py     # Country-based filtering
│   │   └── epg-sync.py           # EPG synchronization
│   │
│   ├── luci/
│   │   ├── controller/
│   │   │   └── iptv_ultra.lua    # LuCI controller
│   │   ├── model/
│   │   │   └── cbi/
│   │   │       ├── iptv_config.lua      # Configuration page
│   │   │       └── iptv_status.lua      # Status/monitoring page
│   │   └── view/
│   │       ├── status.htm
│   │       └── settings.htm
│   │
│   ├── config/
│   │   └── iptv-ultra             # UCI config template
│   │
│   └── init/
│       └── iptv-ultra             # Init.d service script
│
├── package/
│   ├── Makefile                   # Build configuration
│   ├── PKG_BUILD_LINUX_X86.sh     # Build script
│   └── ipk_package/               # IPK package templates
│
├── tests/
│   ├── test_probe.py
│   ├── test_aggregator.py
│   └── test_filter.py
│
├── .github/
│   └── workflows/
│       ├── build.yml              # CI/CD build pipeline
│       └── release.yml            # Release automation
│
├── .gitignore
├── LICENSE
└── README.md
```

## Quick Start

### Installation via APK (OpenWrt 24+)

```bash
apk add luci-app-iptv-ultra
```

### Installation via OPKG (Legacy)

```bash
opkg install luci-app-iptv-ultra.ipk
```

### First Run

1. Access LuCI: `http://router-ip/cgi-bin/luci/`
2. Navigate to: **Services → IPTV Ultra Pro**
3. Select countries and click **Update Sources**
4. Configure output options
5. Access generated playlists at:
   - `http://router-ip/iptv/best.m3u`
   - `http://router-ip/iptv/hd.m3u`
   - `http://router-ip/iptv/clean.m3u`

## Configuration

### Basic UCI Config

```lua
config iptv_ultra 'main'
    option enabled '1'
    option update_time '03:00'
    list countries 'CN'
    list countries 'HK'
    option sort_by 'popularity'
    option min_quality '60'
```

## Performance Scoring

- **1080p/4K**: +30 points
- **720p**: +15 points
- **Startup <2s**: +20 points
- **Stable/No errors**: +20 points
- **Buffering/Stutter**: -40 points
- **Audio-only stream**: -80 points
- **Black screen**: -100 points

**Minimum threshold**: 60/100

## Supported Countries

- CN (China), HK (Hong Kong), TW (Taiwan)
- US (USA), CA (Canada), MX (Mexico)
- JP (Japan), KR (South Korea), IN (India)
- GB (UK), DE (Germany), FR (France)
- And 180+ more...

## API Endpoints

```
GET  /iptv/best.m3u        # Best quality list
GET  /iptv/hd.m3u          # HD quality list
GET  /iptv/clean.m3u       # Clean filtered list
GET  /iptv/epg.xml         # EPG data
GET  /iptv/status          # JSON status
POST /iptv/update          # Trigger manual update
```

## Development

### Build from source

```bash
git clone https://github.com/yuanyokelis/iptv-ultra.git
cd iptv-ultra
make -C package/
```

### Running tests

```bash
python3 -m pytest tests/
```

## License

MIT License - See LICENSE file

## Credits

- IPTV sources: [iptv-org](https://github.com/iptv-org/iptv)
- EPG data: [iptv-org EPG](https://github.com/iptv-org/epg)
- OpenWrt LuCI framework

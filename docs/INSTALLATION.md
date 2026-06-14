# IPTV Ultra Pro - Installation Guide

## Prerequisites

### System Requirements
- OpenWrt 19.07 or later
- 512MB RAM minimum (1GB recommended)
- 100MB free storage
- FFmpeg installed
- Python 3.7+ (for backend)
- LuCI installed

### Supported Platforms
- x86_64 (PC/VM)
- ARM (Raspberry Pi, Orange Pi)
- MIPS (Legacy routers)
- ARM64 (Modern routers)

## Installation Methods

### Method 1: APK Package (OpenWrt 24+)

#### Step 1: Add Repository
```bash
echo 'src/gz iptv-ultra https://github.com/yuanyokelis/iptv-ultra/releases/download/latest/' >> /etc/opkg/customfeeds.conf
```

#### Step 2: Update Package List
```bash
apk update
```

#### Step 3: Install Package
```bash
apk add luci-app-iptv-ultra
```

#### Step 4: Restart Services
```bash
/etc/init.d/iptv-ultra restart
/etc/init.d/uhttpd restart
```

### Method 2: OPKG Package (Legacy OpenWrt)

#### Step 1: Download IPK
```bash
cd /tmp
wget https://github.com/yuanyokelis/iptv-ultra/releases/download/latest/luci-app-iptv-ultra.ipk
```

#### Step 2: Install
```bash
opkg install /tmp/luci-app-iptv-ultra.ipk
```

#### Step 3: Install Dependencies
```bash
opkg install luci ffmpeg python3 python3-pip
pip install requests pyyaml
```

#### Step 4: Enable Service
```bash
service iptv-ultra enable
service iptv-ultra start
```

### Method 3: Manual Installation

#### Step 1: Clone Repository
```bash
git clone https://github.com/yuanyokelis/iptv-ultra.git
cd iptv-ultra
```

#### Step 2: Install Dependencies
```bash
opkg install ffmpeg python3 python3-pip luci-base luci-app-firewall
pip install requests pyyaml
```

#### Step 3: Copy Files
```bash
# Backend scripts
cp src/backend/* /usr/bin/
chmod +x /usr/bin/iptv-*

# LuCI files
mkdir -p /usr/lib/lua/luci/{controller,model/cbi}
cp src/luci/controller/* /usr/lib/lua/luci/controller/
cp src/luci/model/cbi/* /usr/lib/lua/luci/model/cbi/

# Configuration
cp src/config/iptv-ultra /etc/config/
chmod 644 /etc/config/iptv-ultra

# Init script
cp src/init/iptv-ultra /etc/init.d/
chmod 755 /etc/init.d/iptv-ultra

# Data directories
mkdir -p /var/lib/iptv/{cache,output,logs}
chmod 755 /var/lib/iptv/*
```

#### Step 4: Enable Cron Task
```bash
echo '0 3 * * * /usr/bin/iptv-ultra update' | crontab -
service cron restart
```

#### Step 5: Start Service
```bash
/etc/init.d/iptv-ultra enable
/etc/init.d/iptv-ultra start
```

## Post-Installation Configuration

### Step 1: Access LuCI Dashboard
```
http://router-ip/cgi-bin/luci/
```

### Step 2: Navigate to IPTV Ultra Pro
```
Services → IPTV Ultra Pro
```

### Step 3: Configure Settings

1. **Enable Plugin**: Check "Enable IPTV Ultra Pro"

2. **Select Countries**:
   - Check desired countries (e.g., CN, HK, TW)
   - Multi-select supported

3. **Quality Settings**:
   - Minimum Score: 60 (default)
   - Adjust from 0-100 based on network

4. **Sort Method**:
   - Popularity (default)
   - Latency (lowest first)
   - Resolution (highest first)

5. **Output Options**:
   - ☑ Generate best.m3u
   - ☑ Generate hd.m3u
   - ☑ Generate clean.m3u
   - ☑ Generate epg.xml

6. **Schedule**:
   - Update Time: 03:00 (default)
   - Update Frequency: Daily

7. **Save & Apply**

### Step 4: Trigger Initial Update

```bash
# Via LuCI: Click "Update Sources" button

# Or via CLI:
/usr/bin/iptv-ultra update
```

### Step 5: Verify Installation

```bash
# Check service status
service iptv-ultra status

# Verify output files exist
ls -lh /var/lib/iptv/output/

# Test HTTP access
curl http://localhost/iptv/best.m3u | head -20
```

## Configuration Files

### UCI Configuration (/etc/config/iptv-ultra)

```lua
config iptv_ultra 'main'
    option enabled '1'
    option update_time '03:00'
    option min_quality '60'
    option sort_by 'popularity'
    list countries 'CN'
    list countries 'HK'
    list countries 'TW'
    option output_best '1'
    option output_hd '1'
    option output_clean '1'
    option output_epg '1'

config advanced 'settings'
    option thread_count '30'
    option probe_timeout '5'
    option cache_ttl '86400'
    option log_level 'info'
    option enable_stats '1'
```

### Log Location

```bash
# Service logs
tail -f /var/log/iptv-ultra.log

# Real-time monitoring
tail -f /var/lib/iptv/logs/*
```

## Firewall Configuration

### Allow HTTP Access

```bash
uci set firewall.@rule[-1]=rule
uci set firewall.@rule[-1].name='Allow IPTV HTTP'
uci set firewall.@rule[-1].src='lan'
uci set firewall.@rule[-1].dest_port='80'
uci set firewall.@rule[-1].proto='tcp'
uci set firewall.@rule[-1].target='ACCEPT'
uci commit firewall
service firewall restart
```

## Troubleshooting

### Issue: LuCI interface not showing plugin

**Solution**:
```bash
# Rebuild LuCI cache
rm -rf /tmp/luci-*
service uhttpd restart
```

### Issue: No channels generated

**Solution**:
```bash
# Check manual update
/usr/bin/iptv-ultra update -v

# Verify internet connectivity
ping iptv-org.github.io

# Check FFmpeg installation
which ffmpeg
ffmpeg -version
```

### Issue: HTTP 404 on m3u files

**Solution**:
```bash
# Verify output directory
ls -la /var/lib/iptv/output/

# Check uhttpd configuration
grep -r 'iptv' /etc/config/uhttpd

# Restart HTTP server
service uhttpd restart
```

### Issue: High CPU usage

**Solution**:
```bash
# Reduce concurrent threads
uci set iptv-ultra.settings.thread_count='15'
uci commit iptv-ultra

# Or disable stats collection
uci set iptv-ultra.settings.enable_stats='0'
uci commit iptv-ultra
```

### Issue: Streams not working

**Solution**:
```bash
# Increase minimum quality threshold
uci set iptv-ultra.main.min_quality='50'
uci commit iptv-ultra

# Re-run update
/usr/bin/iptv-ultra update

# Test individual stream
/usr/bin/iptv-ultra test 'http://stream-url'
```

## Uninstallation

### Via APK
```bash
apk del luci-app-iptv-ultra
```

### Via OPKG
```bash
opkg remove luci-app-iptv-ultra
```

### Manual Cleanup
```bash
# Remove files
rm -f /usr/bin/iptv-*
rm -rf /usr/lib/lua/luci/controller/iptv_ultra.lua
rm -rf /usr/lib/lua/luci/model/cbi/iptv_*
rm -f /etc/init.d/iptv-ultra

# Remove data
rm -rf /var/lib/iptv/

# Remove config
rm -f /etc/config/iptv-ultra

# Remove cron job
crontab -e  # Remove iptv-ultra line
```

## Next Steps

1. **Configure in LuCI**: Visit Services → IPTV Ultra Pro
2. **Select countries**: Choose desired regions
3. **Start first update**: Click "Update Sources"
4. **Add to device**: Subscribe `http://router-ip/iptv/best.m3u` in TVBox

## Support

For issues and questions:
- GitHub Issues: https://github.com/yuanyokelis/iptv-ultra/issues
- Wiki: https://github.com/yuanyokelis/iptv-ultra/wiki

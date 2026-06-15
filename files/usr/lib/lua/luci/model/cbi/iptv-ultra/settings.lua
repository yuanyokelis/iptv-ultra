local m, s, o
local sys = require "luci.sys"
local fs = require "nixio.fs"
local ip = sys.exec("uci get network.lan.ipaddr 2>/dev/null | tr -d '\\n'")
if ip == "" then ip = "192.168.1.1" end

-- Read runtime status from status file
local function read_status()
    local data = {
        total_channels = "0",
        success_rate = "0%",
        failed_today = "0",
        avg_latency = "0ms",
        last_update = "Never"
    }
    if fs.access("/tmp/iptv-ultra-status.json") then
        local content = fs.readfile("/tmp/iptv-ultra-status.json") or "{}"
        local ok, decoded = pcall(function()
            local json = require "luci.jsonc"
            return json.parse(content)
        end)
        if ok and decoded then
            for k, v in pairs(decoded) do
                if type(v) == "string" or type(v) == "number" then
                    data[k] = tostring(v)
                end
            end
        end
    end
    return data
end

local function count_channels_in_file(filename)
    local path = "/www/iptv/" .. filename
    if fs.access(path) then
        local content = fs.readfile(path) or ""
        local count = 0
        for _ in content:gmatch("#EXTINF") do
            count = count + 1
        end
        return tostring(count)
    end
    return "0"
end

m = Map("iptv-ultra", "IPTV Ultra Pro",
    _("自动抓取 iptv-org 开源直播源，基于 ffmpeg 多线程测速并进行智能聚合、自动清理、评分排序，生成最佳直播源列表供 TVBox / 影视仓订阅使用。"))

-- ─── Disabled Warning ───────────────────────────────────────────────────────

if not fs.access("/www/iptv/best.m3u") then
    s = m:section(NamedSection, "global", "global")
    s.anonymous = true
    o = s:option(DummyValue, "_nowarn", "")
    o.value = _("⚠️ 尚未生成播放列表，请选择国家后点击「一键更新并测速」")
    o.template = "cbi/error"
end

-- ═══════════════════════════════════════════════════════════════════════════
-- 📊 状态面板
-- ═══════════════════════════════════════════════════════════════════════════

s = m:section(NamedSection, "global", "global", _("📊 运行状态"))
s.anonymous = true
s.addremove = false

local status = read_status()

-- Read counts from actual files
local best_count = count_channels_in_file("best.m3u")
local hd_count = count_channels_in_file("hd.m3u")
local clean_count = count_channels_in_file("clean.m3u")

-- Row 1: channel counts
o = s:option(DummyValue, "_best_count", _("🥇 最优源 (Best)"))
o.value = best_count .. " channels"

o = s:option(DummyValue, "_hd_count", _("🎥 高清源 (HD)"))
o.value = hd_count .. " channels"

o = s:option(DummyValue, "_clean_count", _("📋 全部源 (Clean)"))
o.value = clean_count .. " channels"

-- Row 2: quality metrics
o = s:option(DummyValue, "_success_rate", _("✅ 成功率"))
o.value = status.success_rate or "0%"

o = s:option(DummyValue, "_failed_today", _("❌ 今日失败"))
o.value = status.failed_today or "0"

o = s:option(DummyValue, "_avg_latency", _("⏱️ 平均延迟"))
o.value = status.avg_latency or "0ms"

-- Row 3: last update
o = s:option(DummyValue, "_last_update", _("🕐 最后更新"))
o.value = status.last_update or "Never"

-- ═══════════════════════════════════════════════════════════════════════════
-- ⚙️ 快捷控制 (操作按钮)
-- ═══════════════════════════════════════════════════════════════════════════

s = m:section(NamedSection, "global", "global", _("⚙️ 快捷操作"))
s.anonymous = true

-- Update button
o = s:option(Button, "_update_btn")
o.title = _("🔄 一键更新并测速")
o.inputtitle = _("开始更新")
o.inputstyle = "apply"
function o.write(self, section)
    sys.exec("/usr/bin/iptv-ultra update >/tmp/iptv-ultra-update.log 2>&1 &")
    luci.http.redirect(luci.dispatcher.build_url("admin/services/iptv-ultra"))
end

-- Clear button
o = s:option(Button, "_clear_btn")
o.title = _("🧹 清除缓存与输出")
o.inputtitle = _("清除")
o.inputstyle = "reset"
function o.write(self, section)
    sys.exec("/usr/bin/iptv-ultra clear")
    luci.http.redirect(luci.dispatcher.build_url("admin/services/iptv-ultra"))
end

-- Regen button
o = s:option(Button, "_regen_btn")
o.title = _("🔄 从缓存重新生成")
o.inputtitle = _("重新生成")
o.inputstyle = "apply"
function o.write(self, section)
    sys.exec("/usr/bin/iptv-ultra regen >/dev/null 2>&1 &")
    luci.http.redirect(luci.dispatcher.build_url("admin/services/iptv-ultra"))
end

-- ═══════════════════════════════════════════════════════════════════════════
-- 🌍 基础配置
-- ═══════════════════════════════════════════════════════════════════════════

s = m:section(NamedSection, "global", "global", _("🌍 基础设置"))
s.anonymous = true

o = s:option(Flag, "enabled", _("启用自动抓取与定时任务"))
o.default = "1"
o.rmempty = false

o = s:option(MultiValue, "countries", _("国家/地区过滤 (多选)"))
o:value("cn", "🇨🇳 CN - 中国")
o:value("hk", "🇭🇰 HK - 香港")
o:value("tw", "🇹🇼 TW - 台湾")
o:value("us", "🇺🇸 US - 美国")
o:value("jp", "🇯🇵 JP - 日本")
o:value("kr", "🇰🇷 KR - 韩国")
o:value("gb", "🇬🇧 GB - 英国")
o:value("de", "🇩🇪 DE - 德国")
o:value("fr", "🇫🇷 FR - 法国")
o:value("ca", "🇨🇦 CA - 加拿大")
o:value("au", "🇦🇺 AU - 澳大利亚")
o:value("in", "🇮🇳 IN - 印度")
o:value("ru", "🇷🇺 RU - 俄罗斯")
o:value("sg", "🇸🇬 SG - 新加坡")
o:value("my", "🇲🇾 MY - 马来西亚")
o:value("th", "🇹🇭 TH - 泰国")
o:value("ph", "🇵🇭 PH - 菲律宾")
o:value("vn", "🇻🇳 VN - 越南")
o:value("it", "🇮🇹 IT - 意大利")
o:value("es", "🇪🇸 ES - 西班牙")
o:value("nl", "🇳🇱 NL - 荷兰")
o:value("se", "🇸🇪 SE - 瑞典")
o:value("no", "🇳🇴 NO - 挪威")
o:value("dk", "🇩🇰 DK - 丹麦")
o:value("fi", "🇫🇮 FI - 芬兰")
o:value("pl", "🇵🇱 PL - 波兰")
o:value("br", "🇧🇷 BR - 巴西")
o:value("ar", "🇦🇷 AR - 阿根廷")
o:value("mx", "🇲🇽 MX - 墨西哥")
o:value("za", "🇿🇦 ZA - 南非")
o.widget = "checkbox"
o.size = 30

o = s:option(ListValue, "sort_by", _("排序方式"))
o:value("hot", _("🔥 热度优先（综合评分 + 成功率 + 低延迟）"))
o:value("latency", _("⚡ 极速优先（延迟最低）"))
o:value("resolution", _("📺 画质优先（分辨率最高）"))
o.default = "hot"

o = s:option(Value, "max_threads", _("并发测速线程数"))
o.default = "30"
o.datatype = "range(1,100)"
o.description = _("更多线程 = 更快测速，但会增加 CPU 负载。OpenWrt 建议 20-50。")

o = s:option(Value, "min_score", _("最低评分过滤 (0-100)"))
o.default = "60"
o.datatype = "range(0,100)"
o.description = _("低于此评分的频道将被过滤。建议 60。")

o = s:option(Value, "update_time", _("每日定时更新 (Cron 表达式)"))
o.default = "0 3 * * *"
o.description = _("格式: 分 时 日 月 周  |  例: 0 3 * * * = 每天凌晨3点")

-- ═══════════════════════════════════════════════════════════════════════════
-- 📡 订阅地址输出面板
-- ═══════════════════════════════════════════════════════════════════════════

s = m:section(NamedSection, "global", "global", _("📡 订阅地址 (TVBox / 影视仓 直接填入)"))
s.anonymous = true
s.description = _("将以下地址填入 TVBox 或 影视仓 的「直播订阅」即可使用。")

o = s:option(DummyValue, "_best_url")
o.title = _("🥇 最优综合源")
o.value = "http://" .. ip .. "/iptv/best.m3u"
o.description = _("按热度排序，已过滤低分频道，推荐首选。")

o = s:option(DummyValue, "_hd_url")
o.title = _("🎥 高清源 (720p+)")
o.value = "http://" .. ip .. "/iptv/hd.m3u"
o.description = _("仅包含 720p / 1080p / 4K 高清频道。")

o = s:option(DummyValue, "_clean_url")
o.title = _("📋 完整列表")
o.value = "http://" .. ip .. "/iptv/clean.m3u"
o.description = _("全部可用频道，未做分辨率过滤。")

o = s:option(DummyValue, "_epg_url")
o.title = _("📅 EPG 节目单")
o.value = "http://" .. ip .. "/iptv/epg.xml"
o.description = _("电子节目指南，需播放器支持。")

return m

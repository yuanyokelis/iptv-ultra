local m, s, o
local sys = require "luci.sys"
local fs = require "nixio.fs"

m = Map("iptv-ultra", "IPTV Ultra Pro", _("自动抓取优质开源 IPTV 直播源，配合 ffmpeg 引擎多线程测速去重，生成最优质稳定的专属 M3U 直播列表。"))

-- 📊 状态面板部分
s = m:section(TypedSection, "status", _("当前运行状态"))
s.anonymous = true
s.template  = "cbi/tblsection"

local total = s:option(DummyValue, "total_channels", _("有效频道总数"))
local rate  = s:option(DummyValue, "success_rate", _("测速通过率"))
local fail  = s:option(DummyValue, "failed_today", _("今日过滤无效源"))

-- ⚙️ 操作控制按钮
s = m:section(NamedSection, "global", "iptv-ultra", _("快捷控制"))
s.anonymous = true

local btn_update = s:option(Button, "_update", _("手动刷新"))
btn_update.inputtitle = _("一键更新并测速")
btn_update.inputstyle = "apply"
function btn_update.write(self, section)
    sys.exec("/usr/bin/iptv-ultra update &")
end

local btn_clear = s:option(Button, "_clear", _("清理无效源"))
btn_clear.inputtitle = _("清除缓存数据")
btn_clear.inputstyle = "reset"
function btn_clear.write(self, section)
    sys.exec("/usr/bin/iptv-ultra clear_cache")
end

-- 🌍 配置主要选项
s = m:section(NamedSection, "global", "global", _("基础设置"))
s.anonymous = true

o = s:option(Flag, "enabled", _("启用自动抓取测速"))
o.default = "1"

o = s:option(MultiValue, "countries", _("国家/地区过滤 (多选)"))
o:value("cn", "CN - 中国")
o:value("hk", "HK - 香港")
o:value("tw", "TW - 台湾")
o:value("us", "US - 美国")
o:value("jp", "JP - 日本")
o:value("kr", "KR - 韩国")
o.widget = "checkbox"

o = s:option(ListValue, "sort_by", _("优化排序权重"))
o:value("hot", _("综合评分（算法优化最高）"))
o:value("latency", _("极速优先（延迟最低）"))
o:value("resolution", _("画质优先（分辨率最高）"))

o = s:option(Value, "max_threads", _("并发测速线程数"))
o.default = "30"
o.datatype = "integer"

o = s:option(Value, "update_time", _("每日定时更新 Cron"))
o.default = "0 3 * * *"

-- 📡 输出地址面板
s = m:section(NamedSection, "global", "global", _("系统输出订阅地址 (TVBox/影视仓 直接填入)"))
s.anonymous = true

local ip = sys.exec("uci get network.lan.ipaddr | tr -d '\n'")
if ip == "" then ip = "1192.168.1.1" end

o = s:option(DummyValue, "_best", _("最优源（高分特选）"))
o.value = "http://" .. ip .. "/iptv/best.m3u"

o = s:option(DummyValue, "_hd", _("高清源（仅 1080p/4K）"))
o.value = "http://" .. ip .. "/iptv/hd.m3u"

o = s:option(DummyValue, "_clean", _("洗白源（去重总列表）"))
o.value = "http://" .. ip .. "/iptv/clean.m3u"

o = s:option(DummyValue, "_epg", _("匹配 EPG 节目单"))
o.value = "http://" .. ip .. "/iptv/epg.xml"

return m
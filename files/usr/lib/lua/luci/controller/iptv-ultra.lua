module("luci.controller.iptv-ultra", package.seeall)

function index()
    if not nixio.fs.access("/etc/config/iptv-ultra") then
        return
    end

    -- 注册 Services -> IPTV Ultra Pro 菜单
    entry({"admin", "services", "iptv-ultra"}, cbi("iptv-ultra/settings"), _("IPTV Ultra Pro"), 60).dependent = true
    -- 注册后台操作 API 接口
    entry({"admin", "services", "iptv-ultra", "action"}, call("action_handler")).dependent = true
end

function action_handler()
    local http = require "luci.http"
    local sys  = require "luci.sys"
    local query = http.formvalue("do")
    
    if query == "update" then
        sys.exec("/usr/bin/iptv-ultra update &")
        http.write("json={\"status\":\"processing\"}")
    elseif query == "clear" then
        sys.exec("/usr/bin/iptv-ultra clear_cache")
        http.write("json={\"status\":\"cleared\"}")
    else
        http.write("json={\"status\":\"unknown\"}")
    end
end
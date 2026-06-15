module("luci.controller.iptv-ultra", package.seeall)

function index()
    if not nixio.fs.access("/etc/config/iptv-ultra") then
        return
    end

    -- Services -> IPTV Ultra Pro (with status dashboard)
    entry({"admin", "services", "iptv-ultra"},
        cbi("iptv-ultra/settings"),
        _("IPTV Ultra Pro"), 60).dependent = true

    -- Ajax JSON status endpoint (for dynamic refresh)
    entry({"admin", "services", "iptv-ultra", "status_json"},
        call("ajax_status"), nil).leaf = true

    -- API action handler (update, clear, regen)
    entry({"admin", "services", "iptv-ultra", "action"},
        call("action_handler"), nil).leaf = true
end

function ajax_status()
    local http = require "luci.http"
    local fs = require "nixio.fs"
    local json = require "luci.jsonc" or require "luci.json"

    http.prepare_content("application/json")

    local status_data
    if fs.access("/tmp/iptv-ultra-status.json") then
        status_data = fs.readfile("/tmp/iptv-ultra-status.json")
    else
        status_data = '{"status":"no_data","total_channels":0,"success_rate":"0%","failed_today":0,"avg_latency":"0ms"}'
    end

    http.write(status_data)
end

function action_handler()
    local http = require "luci.http"
    local sys = require "luci.sys"
    local action = http.formvalue("do")

    if action == "update" then
        local countries = http.formvalue("countries")
        local sort_by = http.formvalue("sort_by") or "hot"
        local threads = http.formvalue("threads") or "30"

        local cmd = "/usr/bin/iptv-ultra update"
        if countries and countries ~= "" then
            cmd = cmd .. " -c " .. countries
        end
        if sort_by then
            cmd = cmd .. " -s " .. sort_by
        end
        cmd = cmd .. " -t " .. threads
        sys.exec(cmd .. " >/tmp/iptv-ultra-update.log 2>&1 &")
        http.write('{"status":"processing","message":"Update started in background"}')

    elseif action == "update_async_check" then
        local sysinfo = require "luci.sys"
        local running = sysinfo.process.info("iptv-probe.py")
        if running and #running > 0 then
            http.write('{"status":"running"}')
        else
            local fs = require "nixio.fs"
            local ok = false
            local msg = ""
            if fs.access("/tmp/iptv-ultra-status.json") then
                ok = true
            end
            if ok then
                http.write('{"status":"done"}')
            else
                http.write('{"status":"unknown"}')
            end
        end

    elseif action == "clear" then
        sys.exec("/usr/bin/iptv-ultra clear")
        http.write('{"status":"cleared","message":"Cache cleared"}')

    elseif action == "regen" then
        sys.exec("/usr/bin/iptv-ultra regen >/dev/null 2>&1 &")
        http.write('{"status":"processing","message":"Regenerating output"}')

    elseif action == "list_channels" then
        local fs = require "nixio.fs"
        local www_path = "/www/iptv/"
        local list_type = http.formvalue("type") or "best"
        local file_path = www_path .. list_type .. ".m3u"

        http.prepare_content("application/json")
        if fs.access(file_path) then
            local content = fs.readfile(file_path) or ""
            local channels = {}
            for line in content:gmatch("[^\r\n]+") do
                local name = line:match('IPTV Ultra%]*,([^,]+)')
                if name then
                    local res = line:match('resolution="([^"]+)"') or "unknown"
                    local score = line:match('score="([^"]+)"') or "0"
                    table.insert(channels, {
                        name = name,
                        resolution = res,
                        score = tonumber(score) or 0
                    })
                end
            end
            local data = {
                channels = channels,
                total = #channels
            }
            http.write_json(data)
        else
            http.write_json({channels = {}, total = 0})
        end

    elseif action == "save_countries" then
        local countries_param = http.formvalue("countries")
        if countries_param and countries_param ~= "" then
            -- Save to UCI
            local sys = require "luci.sys"
            -- Clear existing
            sys.exec("uci delete iptv-ultra.@global[0].countries 2>/dev/null; uci commit iptv-ultra")
            for cc in countries_param:gmatch("%S+") do
                if cc ~= "" then
                    sys.exec("uci add_list iptv-ultra.@global[0].countries='" .. cc:lower() .. "'")
                end
            end
            sys.exec("uci commit iptv-ultra")
        end
        http.write('{"status":"saved"}')

    else
        http.write('{"status":"unknown","message":"Unknown action: ' .. (action or "nil") .. '"}')
    end
end

ngx.req.read_body()

local redis = require "resty.redis"
local cjson = require "cjson"

local red = redis:new()
red:set_timeout(1000)

local mode = "full"
local ok, err = red:connect("redis", 6379)
if not ok then
    ngx.log(ngx.WARN, "LUA: Redis connection failed: ", err)
else
    local redis_mode, mode_err = red:get("waf:mode")
    if redis_mode and redis_mode ~= ngx.null then
        mode = redis_mode
    end
end

if mode == "off" then
    ngx.log(ngx.INFO, "LUA: WAF Mode is OFF (Bypass). Passing through.")
    return
end

local request_body = ngx.req.get_body_data() or ""
local uri_args = ngx.req.get_uri_args()
local check_strings = {}

if request_body ~= "" then
    table.insert(check_strings, request_body)
end

if uri_args and next(uri_args) ~= nil then
    for key, val in pairs(uri_args) do
        if type(val) == "table" then
            for _, v in ipairs(val) do
                table.insert(check_strings, key .. "=" .. v)
            end
        else
            table.insert(check_strings, key .. "=" .. val)
        end
    end
end

local combined_input = table.concat(check_strings, " ")

if mode == "full" and ok and combined_input ~= "" then
    local is_exact = red:sismember("waf:rules:exact_payloads", combined_input)
    if is_exact == 1 then
        ngx.log(ngx.INFO, "BLOCK: Stage 1 Exact Payload Match: ", combined_input)
        ngx.header.content_type = "text/html"
        ngx.status = ngx.HTTP_FORBIDDEN
        ngx.say([[
            <!DOCTYPE html>
            <html>
            <head><title>403 Forbidden | WireFall WAF Security</title></head>
            <body style="background:#090d16; color:#f8fafc; font-family:sans-serif; display:flex; justify-content:center; align-items:center; height:100vh; margin:0;">
                <div style="background:#0f172a; border:1px solid #ef4444; border-radius:12px; padding:2rem; text-align:center; max-width:500px;">
                    <h2 style="color:#ef4444; margin-top:0;">🛡️ 403 Access Denied</h2>
                    <p style="color:#94a3b8;">This request was blocked by <b>WireFall Stage 1 Fast-Path Rule</b> (Redis Memory Lookup &lt; 1ms).</p>
                    <div style="background:#030509; border:1px solid #1e293b; color:#f97316; font-family:monospace; padding:0.75rem; border-radius:6px; font-size:0.85rem; word-break:break-all;">]] .. combined_input .. [[</div>
                </div>
            </body>
            </html>
        ]])
        return ngx.exit(ngx.HTTP_FORBIDDEN)
    end

    local rules, err = red:smembers("waf:rules:regex")
    if rules then
        for _, rule in ipairs(rules) do
            local clean_rule = rule:gsub("^%(%?i%)", "")
            local pcall_ok, matched = pcall(function()
                return ngx.re.find(combined_input, clean_rule, "ijo") ~= nil
            end)
            if pcall_ok and matched then
                ngx.log(ngx.INFO, "BLOCK: Stage 1 Regex Match: ", rule)
                ngx.header.content_type = "text/html"
                ngx.status = ngx.HTTP_FORBIDDEN
                ngx.say([[
                    <!DOCTYPE html>
                    <html>
                    <head><title>403 Forbidden | WireFall WAF Security</title></head>
                    <body style="background:#090d16; color:#f8fafc; font-family:sans-serif; display:flex; justify-content:center; align-items:center; height:100vh; margin:0;">
                        <div style="background:#0f172a; border:1px solid #ef4444; border-radius:12px; padding:2rem; text-align:center; max-width:500px;">
                            <h2 style="color:#ef4444; margin-top:0;">🛡️ 403 Access Denied</h2>
                            <p style="color:#94a3b8;">Blocked by <b>WireFall Stage 1 Static Regex WAF Rule</b> (&lt; 1ms).</p>
                            <div style="background:#030509; border:1px solid #1e293b; color:#f97316; font-family:monospace; padding:0.75rem; border-radius:6px; font-size:0.85rem; word-break:break-all;">]] .. rule .. [[</div>
                        </div>
                    </body>
                    </html>
                ]])
                return ngx.exit(ngx.HTTP_FORBIDDEN)
            end
        end
    end
end

local request_body_str = request_body
if uri_args and next(uri_args) ~= nil then
    local args_parts = {}
    for key, val in pairs(uri_args) do
        if type(val) == "table" then
            for _, v in ipairs(val) do
                table.insert(args_parts, key .. "=" .. v)
            end
        else
            table.insert(args_parts, key .. "=" .. val)
        end
    end
    request_body_str = table.concat(args_parts, "&")
end

local transformer_data = {
    method = ngx.req.get_method(),
    path = ngx.var.uri,
    protocol = ngx.var.server_protocol,
    request_body = request_body_str
}

local res = ngx.location.capture("/analyze_internal", {
    method = ngx.HTTP_POST,
    body = cjson.encode(transformer_data)
})

if res and res.status == 200 then
    local report = cjson.decode(res.body)
    if report and report.allow == false then
        ngx.header.content_type = "text/html"
        ngx.status = ngx.HTTP_FORBIDDEN
        ngx.say([[
            <!DOCTYPE html>
            <html>
            <head><title>403 Forbidden | WireFall WAF Security</title></head>
            <body style="background:#090d16; color:#f8fafc; font-family:sans-serif; display:flex; justify-content:center; align-items:center; height:100vh; margin:0;">
                <div style="background:#0f172a; border:1px solid #ef4444; border-radius:12px; padding:2rem; text-align:center; max-width:500px;">
                    <h2 style="color:#ef4444; margin-top:0;">🛡️ 403 Access Denied</h2>
                    <p style="color:#94a3b8;">Blocked by <b>WireFall Stage 2 DistilBERT Anomaly Model</b>.</p>
                    <p style="color:#cbd5e1; font-size:0.9rem;">]] .. (report.reason or "Malicious payload detected") .. [[</p>
                </div>
            </body>
            </html>
        ]])
        return ngx.exit(ngx.HTTP_FORBIDDEN)
    end
end

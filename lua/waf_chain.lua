ngx.req.read_body()

-- ===================================================================
-- STAGE 1: REGEX CHECK AGAINST LOCAL REDIS
-- ===================================================================
local redis = require "resty.redis"
local cjson = require "cjson"

local red = redis:new()
red:set_timeout(1000)

-- Connect to local Redis
local ok, err = red:connect("127.0.0.1", 6379)
if not ok then
    ngx.log(ngx.ERR, "LUA: Failed to connect to local Redis: ", err)
    return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
end

-- Collect all input to check
local request_body = ngx.req.get_body_data() or ""
local uri_args = ngx.req.get_uri_args()
local check_strings = {}

-- Add request body if exists
if request_body ~= "" then
    table.insert(check_strings, request_body)
end

-- Add URI arguments if exist
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

-- Combine everything into one string to check
local combined_input = table.concat(check_strings, " ")

-- Check rules against combined input
local rules, err = red:smembers("waf:rules:regex")
if rules then
    ngx.log(ngx.INFO, "LUA: Loaded ", #rules, " rules from Redis")
    for _, rule in ipairs(rules) do
        if ngx.re.find(combined_input, rule, "ijo") then
            ngx.log(ngx.INFO, "BLOCK: Stage 1 blocked by regex rule: ", rule)
            ngx.log(ngx.INFO, "BLOCK: Matched input: ", combined_input)
            return ngx.exit(ngx.HTTP_FORBIDDEN)
        end
    end
end
ngx.log(ngx.INFO, "PASS: Stage 1 (Regex) passed.")

-- ===================================================================
-- STAGE 2: TRANSFORMER MODEL CHECK
-- ===================================================================
local http = require "resty.http"

-- Build request_body string in the format your transformer expects
local request_body_str = request_body

-- If there are URI arguments, format them as key=value pairs
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

-- Format data according to transformer model's expected schema
local transformer_data = {
    method = ngx.req.get_method(),
    path = ngx.var.uri,
    protocol = ngx.var.server_protocol,
    request_body = request_body_str
}

ngx.log(ngx.INFO, "LUA: Sending to transformer: ", cjson.encode(transformer_data))

local httpc = http:new()
local res, err = httpc:request_uri("http://127.0.0.1:8001/analyze", {
    method = "POST",
    body = cjson.encode(transformer_data),
    headers = { ["Content-Type"] = "application/json" }
})

if not res then
    ngx.log(ngx.ERR, "LUA: Failed to connect to analyzer: ", err)
    return ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
end

ngx.log(ngx.INFO, "LUA: Transformer response: ", res.body)

local report, err = cjson.decode(res.body)
if not report then
    ngx.log(ngx.ERR, "LUA: Failed to decode analyzer response: ", err)
    return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
end

if report.allow == false then
    ngx.log(ngx.INFO, "BLOCK: Stage 2 blocked by transformer model")
    return ngx.exit(ngx.HTTP_FORBIDDEN)
end

ngx.log(ngx.INFO, "PASS: Stage 2 (Transformer) passed. Proxying to backend.")

-- ✅ CRITICAL: Don't return anything here
-- Let nginx continue with proxy_pass directive

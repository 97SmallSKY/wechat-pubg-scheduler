const defaultConfig = {enabled: false, time: "23:00", group: "", players: []};
const clock = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", minute: "2-digit", hourCycle: "h23",
});

function shanghai(now) {
  const parts = Object.fromEntries(clock.formatToParts(now).map(({type, value}) => [type, value]));
  return { day: [parts.year, parts.month, parts.day].join("-"), time: parts.hour + ":" + parts.minute };
}

function validateConfig(input) {
  if (!input || typeof input.enabled !== "boolean" ||
      typeof input.time !== "string" || !/^([01][0-9]|2[0-3]):[0-5][0-9]$/.test(input.time) ||
      typeof input.group !== "string" || input.group.length > 80 ||
      !Array.isArray(input.players) || input.players.length > 10) {
    return "请填写有效的北京时间、群名和至多十位玩家。";
  }
  const names = new Set();
  for (const player of input.players) {
    if (!player || typeof player.steam !== "string" || !/^[A-Za-z0-9_.-]{1,32}$/.test(player.steam) ||
        typeof player.wechat !== "string" || player.wechat.length > 64 ||
        names.has(player.steam.toLowerCase())) {
      return "Steam 昵称须唯一，仅用字母、数字、下划线、点或连字符。";
    }
    names.add(player.steam.toLowerCase());
  }
  if (input.enabled && !input.players.length) return "启用前至少填写一位 Steam 玩家。";
  return "";
}

async function jsonBody(request, limit) {
  if (!request.headers.get("content-type")?.startsWith("application/json")) return null;
  const text = await request.text();
  if (text.length > limit) return null;
  try { return JSON.parse(text); }
  catch (error) { if (error instanceof SyntaxError) return null; throw error; }
}

const reply = (value, status = 200) => Response.json(value, {
  status, headers: {"cache-control": "no-store"},
});

async function handler(request, env, now = new Date(), assets = {}) {
  const {pathname} = new URL(request.url);
  const {method} = request;
  const db = env.DB;
  const dayClock = shanghai(now);

  if (pathname.startsWith("/api/runner/")) {
    // Sites dispatch requires owner access. This credential separates AWS from browser actions.
    if (!env.RUNNER_TOKEN || request.headers.get("authorization") !== "Bearer " + env.RUNNER_TOKEN) {
      return reply({error: "Runner authorization required."}, 401);
    }
    if (method === "POST" && pathname === "/api/runner/claim") {
      await db.batch([
        db.prepare("INSERT OR REPLACE INTO runner VALUES (1, datetime('now'))"),
        db.prepare(`UPDATE runs SET status='failed', finished_at=datetime('now'), result=?
                    WHERE status='running' AND started_at < datetime('now','-15 minutes')`)
          .bind(JSON.stringify({error: "AWS 未在 15 分钟内返回结果。"})),
        db.prepare(`INSERT OR IGNORE INTO runs (scheduled_day, report_day, config, status)
                    SELECT ?, ?, config, 'queued' FROM settings WHERE id=1
                    AND json_extract(config,'$.enabled')=1 AND json_extract(config,'$.time')=?`)
          .bind(dayClock.day, dayClock.day, dayClock.time),
      ]);
      const job = await db.prepare(`UPDATE runs SET status='running', started_at=datetime('now')
        WHERE id=(SELECT id FROM runs WHERE status='queued' ORDER BY id LIMIT 1)
        AND NOT EXISTS (SELECT 1 FROM runs WHERE status='running')
        RETURNING id,report_day,config`).first();
      return reply({job: job ? {...job, config: JSON.parse(job.config)} : null});
    }
    if (method === "POST" && pathname === "/api/runner/result") {
      const data = await jsonBody(request, 60000);
      if (!Number.isInteger(data?.id) || !["previewed","failed"].includes(data?.status) ||
          !data?.result || typeof data.result !== "object") return reply({error: "Invalid result."}, 400);
      const updated = await db.prepare(`UPDATE runs SET status=?, result=?, finished_at=datetime('now')
        WHERE id=? AND status='running' RETURNING id`)
        .bind(data.status, JSON.stringify(data.result), data.id).first();
      return updated ? reply({id: updated.id}) : reply({error: "Run is no longer active."}, 409);
    }
    return reply({error: "Not found."}, 404);
  }

  if (!request.headers.get("oai-authenticated-user-id")) {
    return pathname === "/" ? Response.redirect(new URL("/signin-with-chatgpt", request.url))
      : reply({error: "请通过 ChatGPT 登录。"}, 401);
  }
  if (method === "GET" && Object.hasOwn(assets, pathname)) {
    const [type, body] = assets[pathname];
    return new Response(body, {headers: {
      "content-type": type, "cache-control": "no-store",
      "content-security-policy": "default-src 'self'; object-src 'none'; base-uri 'none'",
      "x-content-type-options": "nosniff",
    }});
  }
  if (pathname === "/api/dashboard" && method === "GET") {
    const [config, runs, runner] = await db.batch([
      db.prepare("SELECT config FROM settings WHERE id=1"),
      db.prepare(`SELECT id,scheduled_day,report_day,status,created_at,finished_at,
                        json_extract(config,'$.group') AS target_group,result
                  FROM runs ORDER BY id DESC LIMIT 20`),
      db.prepare("SELECT last_seen, last_seen >= datetime('now','-3 minutes') AS online FROM runner WHERE id=1"),
    ]);
    return reply({
      config: config.results[0] ? JSON.parse(config.results[0].config) : defaultConfig,
      runs: runs.results.map(run => ({...run, result: JSON.parse(run.result)})),
      runner: runner.results[0] || null,
    });
  }
  if (pathname === "/api/config" && method === "PUT") {
    const input = await jsonBody(request, 8192);
    const error = validateConfig(input);
    if (error) return reply({error}, 400);
    const config = {
      enabled: input.enabled, time: input.time, group: input.group.trim(),
      players: input.players.map(({steam, wechat}) => ({steam, wechat: wechat.trim()})),
    };
    await db.prepare("INSERT OR REPLACE INTO settings (id,config) VALUES (1,?)").bind(JSON.stringify(config)).run();
    return reply({config});
  }
  if (pathname === "/api/preview" && method === "POST") {
    if (!await jsonBody(request, 128)) return reply({error: "请从配置页提交。"}, 400);
    const run = await db.prepare(`INSERT INTO runs (report_day,config,status)
      SELECT ?,config,'queued' FROM settings WHERE id=1 AND json_array_length(config,'$.players') > 0
      AND NOT EXISTS (SELECT 1 FROM runs WHERE scheduled_day IS NULL AND status IN ('queued','running'))
      RETURNING id`).bind(dayClock.day).first();
    return run ? reply(run, 201) : reply({error: "请先保存玩家名单，或等待上一条预览完成。"}, 409);
  }
  return reply({error: "页面不存在。"}, 404);
}

export {handler};

import test from "node:test";
import assert from "node:assert/strict";
import {newDB} from "./d1.mjs";
import {handler} from "../worker/index.mjs";

const runnerToken = "fixture-only";
const time = "2026-06-03T15:00:00Z";
const config = {
  enabled: true, time: "23:00", group: "测试群", players: [{steam: "Sample_Player", wechat: "测试玩家"}],
};

function client(db = newDB()) {
  const env = {DB: db, RUNNER_TOKEN: runnerToken};
  return (path, {method = "GET", body, actor = "owner", at = time} = {}) => {
    const headers = {};
    if (actor === "owner") headers["oai-authenticated-user-id"] = "owner";
    if (actor === "runner") headers.authorization = "Bearer " + runnerToken;
    if (body !== undefined) headers["content-type"] = "application/json";
    return handler(new Request("https://example.test/api/" + path, {
      method, headers, body: body === undefined ? undefined : JSON.stringify(body),
    }), env, new Date(at));
  };
}

test("owner can save validated config; browser and runner permissions are separate", async () => {
  const request = client();
  const dashboard = await (await request("dashboard")).json();
  assert.deepEqual(dashboard.config, {enabled: false, time: "23:00", group: "", players: []});
  assert.equal((await request("dashboard", {actor: "anonymous"})).status, 401);
  assert.equal((await request("dashboard", {actor: "runner"})).status, 401);
  assert.equal((await request("runner/claim", {method: "POST"})).status, 401);
  assert.equal((await request("config", {method: "PUT", body: {...config, time: "25:00"}})).status, 400);
  const duplicate = {...config, players: [...config.players, {steam: "sample_player", wechat: ""}]};
  assert.equal((await request("config", {method: "PUT", body: duplicate})).status, 400);
  assert.equal((await request("config", {method: "PUT", body: config})).status, 200);
  assert.deepEqual((await (await request("dashboard")).json()).config, config);
});

test("scheduled time is Beijing time and claims at most once for a date", async () => {
  const request = client();
  await request("config", {method: "PUT", body: config});
  const claim = async at => (await (await request("runner/claim", {method: "POST", actor: "runner", at})).json()).job;
  assert.equal(await claim("2026-06-03T14:59:59Z"), null);
  const run = await claim(time);
  assert.equal(run.report_day, "2026-06-03");
  assert.deepEqual(run.config, config);
  assert.equal(await claim(time), null);
  const result = {id: run.id, status: "previewed", result: {messages: ["预览"], mentions: []}};
  assert.equal((await request("runner/result", {method: "POST", actor: "runner", body: result})).status, 200);
  assert.equal((await request("runner/result", {method: "POST", actor: "runner", body: result})).status, 409);
  assert.equal(await claim(time), null);
  assert.equal(await claim("2026-06-04T15:01:00Z"), null);
  const dashboard = await (await request("dashboard")).json();
  assert.equal(dashboard.runs.length, 1);
  assert.equal(dashboard.runs[0].status, "previewed");
  assert.equal(dashboard.runner.online, 1);
  assert.equal((await claim("2026-06-05T15:00:00Z")).report_day, "2026-06-05");
});

test("manual preview uses saved settings and can run while the daily schedule is paused", async () => {
  const request = client();
  const submit = () => request("preview", {method: "POST", body: {}, at: "2026-06-03T16:00:00Z"});
  assert.equal((await submit()).status, 409);
  await request("config", {method: "PUT", body: {...config, enabled: false}});
  assert.equal((await submit()).status, 201);
  assert.equal((await submit()).status, 409);
  await request("config", {method: "PUT", body: {...config, enabled: false, group: "改名"}});
  const {job} = await (await request("runner/claim", {method: "POST", actor: "runner"})).json();
  assert.equal(job.report_day, "2026-06-04");
  assert.equal(job.config.group, "测试群");
  const failure = {id: job.id, status: "failed", result: {error: "PUBG 查询失败（429）"}};
  assert.equal((await request("runner/result", {method: "POST", actor: "runner", body: failure})).status, 200);
  assert.equal((await submit()).status, 201);
});

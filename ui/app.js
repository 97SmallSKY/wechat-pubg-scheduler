const $ = id => document.getElementById(id);
let dirty = false;
let loaded = false;
let activity = "";

async function api(path, method = "GET", data) {
  const response = await fetch("/api/" + path, {
    method,
    ...(data === undefined ? {} : {
      headers: {"content-type": "application/json"}, body: JSON.stringify(data),
    }),
  });
  if (response.status === 401 || response.redirected) throw new Error("请刷新页面后重新登录。");
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || "请求失败，请重试。");
  return body;
}

function notice(message, failed = false) {
  $("feedback").textContent = message;
  $("feedback").classList.toggle("error", failed);
}

function syncRows() {
  const size = $("players").childElementCount;
  $("add").disabled = size >= 10;
  $("empty-players").hidden = size > 0;
  $("player-labels").hidden = size === 0;
}

function addRow(player = {steam: "", wechat: ""}) {
  const row = document.createElement("div");
  row.className = "player-row";
  for (const [field, label, max] of [["steam", "Steam 游戏昵称", 32], ["wechat", "微信成员昵称", 64]]) {
    const input = document.createElement("input");
    input.name = field;
    input.setAttribute("aria-label", label);
    input.maxLength = max;
    input.placeholder = label;
    input.value = player[field];
    input.required = field === "steam";
    row.append(input);
  }
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "remove";
  remove.setAttribute("aria-label", "移除玩家");
  remove.textContent = "×";
  remove.onclick = () => { row.remove(); dirty = true; syncRows(); };
  row.append(remove);
  $("players").append(row);
  syncRows();
  return row.querySelector("input");
}

function showSaved(config) {
  $("saved-time").textContent = config.time;
  $("schedule-status").textContent = config.enabled ? "每日预览已启用" : "每日预览已暂停";
}

function showRuns(runs) {
  const snapshot = JSON.stringify(runs);
  if (snapshot === activity) return;
  activity = snapshot;
  const opened = new Set([...$("runs").querySelectorAll("details[open]")].map(el => el.dataset.id));
  $("runs").replaceChildren(...runs.map(run => {
    const card = document.createElement("details");
    card.dataset.id = run.id;
    card.open = opened.has(String(run.id));
    const label = document.createElement("summary");
    label.textContent = run.report_day + (run.scheduled_day ? " · 每日" : " · 手动");
    const state = document.createElement("span");
    state.className = "run-status " + run.status;
    state.textContent = ({queued: "排队中", running: "查询中", previewed: "预览已生成", failed: "失败"})[run.status];
    label.append(state);
    card.append(label);
    const target = document.createElement("p");
    target.className = "muted";
    target.textContent = "目标群：" + (run.target_group || "待配置");
    card.append(target);
    if (run.result?.error) {
      const error = document.createElement("p");
      error.className = "run-error";
      error.textContent = run.result.error;
      card.append(error);
    }
    if (run.result?.messages) {
      const mentions = document.createElement("p");
      mentions.className = "muted";
      mentions.textContent = "拟提及：" + (run.result.mentions.join("、") || "无");
      card.append(mentions);
      for (const message of run.result.messages) {
        const text = document.createElement("pre");
        text.textContent = message;
        card.append(text);
      }
    }
    return card;
  }));
  $("empty-runs").hidden = runs.length > 0;
}

async function refresh(interactive = false) {
  try {
    const {config, runs, runner} = await api("dashboard");
    if (!loaded) {
      $("time").value = config.time;
      $("enabled").checked = config.enabled;
      $("group").value = config.group;
      config.players.forEach(addRow);
      syncRows();
      $("fields").disabled = false;
      loaded = true;
    }
    showSaved(config);
    showRuns(runs);
    $("worker-dot").classList.toggle("online", Boolean(runner?.online));
    $("worker-status").textContent = runner?.online ? "AWS 执行器在线"
      : runner ? "AWS 执行器暂未响应" : "AWS 执行器尚未连接";
  } catch (error) {
    if (interactive || !loaded) notice(error.message, true);
  }
}

$("add").onclick = () => { dirty = true; addRow().focus(); };
$("refresh").onclick = () => refresh(true);
$("config-form").oninput = () => { dirty = true; };
$("config-form").onsubmit = async event => {
  event.preventDefault();
  const config = {
    enabled: $("enabled").checked,
    time: $("time").value,
    group: $("group").value,
    players: [...$("players").children].map(row => ({
      steam: row.querySelector('[name="steam"]').value.trim(),
      wechat: row.querySelector('[name="wechat"]').value.trim(),
    })),
  };
  $("fields").disabled = true;
  try {
    const saved = await api("config", "PUT", config);
    dirty = false;
    showSaved(saved.config);
    notice("已保存。");
  } catch (error) { notice(error.message, true); }
  finally { $("fields").disabled = false; }
};
$("preview").onclick = async () => {
  if (dirty) { notice("请先保存当前修改。", true); return; }
  $("preview").disabled = true;
  try {
    await api("preview", "POST", {});
    notice("已排队，请在运行记录中查看结果。");
    await refresh();
  } catch (error) { notice(error.message, true); }
  finally { $("preview").disabled = false; }
};

refresh();
setInterval(refresh, 12000);

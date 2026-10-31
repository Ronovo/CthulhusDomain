// Display only: the game itself runs in Python (webapp.py). This keeps the save in localStorage,
// sends it to the server with the player's clicks, and shows what comes back.
(() => {
    const SAVE_PREFIX = "dead-but-dreaming:save:";
    const TICK_MS = 250;
    const urls = document.body.dataset;
    const $ = (id) => document.getElementById(id);

    // localStorage can be missing or full; the game then runs without keeping anything in this browser.
    const storage = {
        get(key) {
            try {
                return localStorage.getItem(key);
            } catch {
                return null;
            }
        },
        getJson(key) {
            try {
                return JSON.parse(storage.get(key));
            } catch {
                return null;
            }
        },
        set(key, value) {
            try {
                localStorage.setItem(key, typeof value === "string" ? value : JSON.stringify(value));
            } catch {
            }
        },
        remove(key) {
            try {
                localStorage.removeItem(key);
            } catch {
            }
        },
        keys() {
            try {
                return Object.keys(localStorage);
            } catch {
                return [];
            }
        },
    };

    const readSave = (name) => storage.getJson(SAVE_PREFIX + name);
    const writeSave = (save) => storage.set(SAVE_PREFIX + save.player_name, save);

    function forgetLocalSave(name) {
        storage.remove(SAVE_PREFIX + name);
        const owners = readOwners();
        delete owners[name];
        storage.set(OWNERS_KEY, owners);
    }

    // Deleted worlds wait here until the account has them, so a delete made while the server can't be
    // reached still happens.
    const DELETES_KEY = "dead-but-dreaming:pending-deletes";

    function readDeletes() {
        const deletes = storage.getJson(DELETES_KEY);
        return Array.isArray(deletes) ? deletes : [];
    }

    function deleteSave(name) {
        const local = readSave(name);
        forgetLocalSave(name);
        if (local && local.world_id) storage.set(DELETES_KEY, [...readDeletes(), local.world_id]);
        if (account) syncAccount().catch(console.error);
    }

    function confirmDelete(name, onDeleted) {
        askConfirm(`Delete ${name}? This can't be undone.`, () => {
            deleteSave(name);
            onDeleted();
        });
    }

    // Which account each save here came from, so on a shared browser one account's saves are never
    // handed to the next account that logs in. A save made while logged out has no owner and joins
    // whichever account logs in next.
    const OWNERS_KEY = "dead-but-dreaming:save-owners";
    const RECORD_OWNER_KEY = "dead-but-dreaming:record-owner";

    function readOwners() {
        const owners = storage.getJson(OWNERS_KEY);
        return owners && typeof owners === "object" && !Array.isArray(owners) ? owners : {};
    }

    const listSaves = () => storage.keys()
        .filter((key) => key.startsWith(SAVE_PREFIX))
        .map((key) => key.slice(SAVE_PREFIX.length))
        .sort();

    async function request(url, body, timeoutMs = 0) {
        const options = body === undefined ? {} : {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        };
        if (timeoutMs) options.signal = AbortSignal.timeout(timeoutMs);
        const response = await fetch(url, options);
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw Object.assign(new Error(data.error || `${url} returned ${response.status}`), { status: response.status });
        }
        return response.json();
    }

    function show(screen) {
        for (const section of document.querySelectorAll(".screen")) section.hidden = section.id !== screen;
        $("main-menu-button").hidden = screen === "main-menu";
    }

    function el(tag, className, text = "") {
        const node = document.createElement(tag);
        node.className = className;
        node.textContent = text;
        return node;
    }

    const formatNumber = (value) => value.toLocaleString("en-US");

    function setText(node, text) {
        if (node.textContent !== text) node.textContent = text;
    }

    function setClass(node, className) {
        if (node.className !== className) node.className = className;
    }

    // Style

    const STYLE_KEY = "dead-but-dreaming:style";
    const stylePicker = $("style-picker");

    function hasStyle(style) {
        return [...stylePicker.options].some((option) => option.value === style);
    }

    function applyStyle(style) {
        document.documentElement.dataset.style = style;
        stylePicker.value = style;
    }

    const savedStyle = storage.get(STYLE_KEY);
    if (savedStyle && hasStyle(savedStyle)) applyStyle(savedStyle);
    stylePicker.addEventListener("change", () => {
        applyStyle(stylePicker.value);
        storage.set(STYLE_KEY, stylePicker.value);
    });

    // Menus

    let onConfirm = null;

    function askConfirm(message, onYes) {
        $("confirm-message").textContent = message;
        onConfirm = onYes;
        $("confirm").hidden = false;
    }

    function confirmName() {
        const name = $("name-input").value.trim();
        if (!name) {
            $("name-error").textContent = "Please enter a name";
        } else if (readSave(name)) {
            askConfirm("Save game already exists. Overwrite?", () => newGame(name));
        } else {
            newGame(name);
        }
    }

    async function newGame(name) {
        try {
            const data = await request(urls.newGameUrl, {
                name, difficulty: $("difficulty").value, mode: document.querySelector('input[name="mode"]:checked').value,
            });
            startGame(data.save);
        } catch (error) {
            show("name-entry");
            $("name-error").textContent = error.message;
        }
    }

    // Achievements and devours belong to the player, not to one save, so they survive deleting a world.
    // The server signs the record and the browser sends it back with every request; a logged-in account
    // keeps a copy too.
    const RECORD_KEY = "dead-but-dreaming:record";

    function readRecord() {
        const record = storage.getJson(RECORD_KEY);
        return record && Array.isArray(record.achievements) ? record : null;
    }

    const writeRecord = (record) => storage.set(RECORD_KEY, record);

    function readAchievements() {
        const record = readRecord();
        return record ? record.achievements : [];
    }

    // One difficulty group at a time, or every group with none pressed; pressing a group again clears it.
    let groupFilter = "";

    function filterAchievements() {
        const state = $("state-filter").value;
        const mode = $("mode-filter").value;
        let shown = 0;
        for (const group of document.querySelectorAll(".achievement-group")) {
            const items = group.querySelectorAll(".achievement");
            let visible = 0;
            let earned = 0;
            for (const item of items) {
                const isEarned = item.classList.contains("earned");
                earned += isEarned;
                const show = (!groupFilter || groupFilter === group.dataset.group)
                    && (!state || (state === "earned") === isEarned)
                    && (!mode || !item.dataset.mode || item.dataset.mode === mode);
                item.hidden = !show;
                visible += show;
            }
            setText(group.querySelector(".group-count"), `${earned} / ${items.length}`);
            group.hidden = visible === 0;
            shown += visible;
        }
        $("no-achievements").hidden = shown > 0;
    }

    function markEarnedAchievements() {
        const earned = new Set(readAchievements());
        for (const item of document.querySelectorAll("[data-achievement]")) {
            item.classList.toggle("earned", earned.has(item.dataset.achievement));
        }
        filterAchievements();
    }

    for (const button of document.querySelectorAll(".filter-button")) {
        button.addEventListener("click", () => {
            groupFilter = groupFilter === button.dataset.group ? "" : button.dataset.group;
            for (const other of document.querySelectorAll(".filter-button")) {
                other.setAttribute("aria-pressed", String(other.dataset.group === groupFilter));
            }
            filterAchievements();
        });
    }
    for (const id of ["state-filter", "mode-filter"]) $(id).addEventListener("change", filterAchievements);

    function showAchievements() {
        markEarnedAchievements();
        $("achievements-back").textContent = save ? "Back to Game" : "Back to Menu";
        show("achievements");
    }

    function showToast(achievement) {
        const toast = el("div", "toast");
        const close = el("button", "toast-close", "×");
        close.type = "button";
        close.setAttribute("aria-label", "Close");
        toast.append(close, el("span", "medal"), el("span", "toast-title", "Achievement unlocked"),
            el("span", "toast-name", achievement.name));
        $("toasts").append(toast);
        const timeout = setTimeout(() => toast.remove(), 5000);
        close.addEventListener("click", () => {
            clearTimeout(timeout);
            toast.remove();
        });
    }

    function showLoadList() {
        const names = listSaves();
        $("no-saves").hidden = names.length > 0;
        $("saves").replaceChildren(...names.map((name) => {
            const row = el("div", "save-row");
            const load = el("button", "menu-button", name);
            const remove = el("button", "delete-button", "Delete");
            load.type = remove.type = "button";
            load.addEventListener("click", () => {
                const loaded = readSave(name);
                if (loaded) {
                    startGame(loaded);
                } else {
                    show("main-menu");
                    $("menu-error").textContent = `${name} can't be read. Delete it from Load Game.`;
                }
            });
            remove.addEventListener("click", () => confirmDelete(name, showLoadList));
            row.append(load, remove);
            return row;
        }));
        show("load-list");
    }

    $("new-game").addEventListener("click", () => {
        $("name-input").value = "";
        $("name-error").textContent = "";
        show("name-entry");
        $("name-input").focus();
    });
    $("load-game").addEventListener("click", showLoadList);
    $("show-achievements").addEventListener("click", showAchievements);

    async function showStats() {
        try {
            const data = await request(urls.statsUrl);
            $("stats-rows").replaceChildren(...data.rows.map((row) => {
                const tr = el("tr", "");
                tr.append(el("th", "", row.difficulty), el("td", "number", formatNumber(row.sanity)),
                    el("td", "number", formatNumber(row.worlds)));
                return tr;
            }));
            setText($("stats-sanity"), formatNumber(data.total.sanity));
            setText($("stats-worlds"), formatNumber(data.total.worlds));
            $("no-stats").hidden = data.rows.length > 0;
            $("stats-table").hidden = data.rows.length === 0;
            show("stats");
        } catch (error) {
            $("menu-error").textContent = error.message;
        }
    }

    $("show-stats").addEventListener("click", showStats);
    $("random-name").addEventListener("click", async () => {
        try {
            $("name-input").value = (await request(urls.randomNameUrl)).name;
        } catch (error) {
            $("name-error").textContent = error.message;
        }
    });
    $("name-form").addEventListener("submit", (event) => {
        event.preventDefault();
        confirmName();
    });
    for (const button of document.querySelectorAll(".back")) {
        button.addEventListener("click", () => show("main-menu"));
    }
    $("footer-achievements").addEventListener("click", showAchievements);
    const backToPlay = () => show(save ? "game" : "main-menu");
    $("achievements-back").addEventListener("click", backToPlay);

    // Account: optional. Logging in merges this browser's progress with the account's, and while
    // logged in the server also keeps every save in the account.

    let account = null;

    function setAccount(username) {
        account = username;
        $("account-name").textContent = username || "";
        $("account-name").hidden = !username;
        $("login-button").hidden = Boolean(username);
        $("portfolio-button").hidden = Boolean(username) || !urls.portfolioLoginUrl;
        $("logout-button").hidden = !username;
        $("show-stats").hidden = !username;
    }

    async function syncAccount() {
        const owners = readOwners();
        const saves = {};
        for (const name of listSaves()) {
            if (owners[name] && owners[name] !== account) {
                forgetLocalSave(name);
                continue;
            }
            const local = readSave(name);
            if (local) saves[name] = local;
        }
        const recordOwner = storage.get(RECORD_OWNER_KEY);
        if (recordOwner && recordOwner !== account) storage.remove(RECORD_KEY);
        const deletes = readDeletes();
        const merged = await request(urls.syncUrl, { saves, deleted: deletes, record: readRecord() });
        storage.set(DELETES_KEY, readDeletes().filter((id) => !deletes.includes(id)));
        const deleted = new Set(merged.deleted);
        for (const name of listSaves()) {
            const local = readSave(name);
            if (local && deleted.has(local.world_id)) forgetLocalSave(name);
        }
        const synced = readOwners();
        for (const remote of Object.values(merged.saves)) {
            writeSave(remote);
            synced[remote.player_name] = account;
        }
        storage.set(OWNERS_KEY, synced);
        writeRecord(merged.record);
        storage.set(RECORD_OWNER_KEY, account);
    }

    async function finishLogin(data) {
        setAccount(data.username);
        await syncAccount();
        backToPlay();
    }

    async function submitLogin(url, extra = {}) {
        $("login-error").textContent = "";
        try {
            const data = await request(url, {
                username: $("login-username").value, password: $("login-password").value, ...extra,
            });
            $("login-password").value = "";
            $("login-answer").value = "";
            await finishLogin(data);
        } catch (error) {
            $("login-error").textContent = error.message;
        }
    }

    // The first portfolio login here: link an account the player already has, or make a new one.
    function showAccountLink(name) {
        $("account-link-name").textContent = name;
        $("account-link-username").value = name;
        $("account-link-error").textContent = "";
        show("account-link");
        $("account-link-password").focus();
    }

    async function chooseLinkedAccount(url, body) {
        $("account-link-error").textContent = "";
        try {
            const data = await request(url, body);
            $("account-link-password").value = "";
            await finishLogin(data);
        } catch (error) {
            $("account-link-error").textContent = error.message;
        }
    }

    $("account-link-form").addEventListener("submit", (event) => {
        event.preventDefault();
        chooseLinkedAccount(urls.portfolioLinkUrl, {
            username: $("account-link-username").value, password: $("account-link-password").value,
        });
    });
    $("account-link-new").addEventListener("click", () => chooseLinkedAccount(urls.portfolioNewUrl, {}));
    $("account-link-cancel").addEventListener("click", async () => {
        await request(urls.logoutUrl, {}).catch(console.error);
        show("main-menu");
    });

    // Names the portfolio account this browser is logged in to, when the portfolio says who that is.
    if (urls.portfolioUrl) {
        fetch(`${urls.portfolioUrl}/sso/me`, { credentials: "include", signal: AbortSignal.timeout(5000) })
            .then((response) => (response.ok ? response.json() : {}))
            .then((data) => {
                if (data.username) $("portfolio-button").textContent = `Log In as ${data.username}`;
            })
            .catch(() => {});
    }

    // Reset takes two steps: the username brings up its security question, then the answer and a new
    // password change it.
    function showResetStep(question) {
        $("reset-question").textContent = question || "";
        for (const id of ["reset-question", "reset-answer", "reset-password"]) $(id).hidden = !question;
        $("reset-username").readOnly = Boolean(question);
        $("reset-submit").textContent = question ? "Reset Password" : "Next";
    }

    $("forgot-password").addEventListener("click", () => {
        $("reset-error").textContent = "";
        $("reset-username").value = $("login-username").value;
        showResetStep(null);
        show("reset");
        $("reset-username").focus();
    });
    $("reset-form").addEventListener("submit", async (event) => {
        event.preventDefault();
        $("reset-error").textContent = "";
        try {
            if ($("reset-answer").hidden) {
                const data = await request(urls.resetQuestionUrl, { username: $("reset-username").value });
                showResetStep(data.question);
                $("reset-answer").focus();
                return;
            }
            await request(urls.resetPasswordUrl, {
                username: $("reset-username").value, answer: $("reset-answer").value,
                password: $("reset-password").value,
            });
            $("reset-answer").value = "";
            $("reset-password").value = "";
            $("login-username").value = $("reset-username").value;
            $("login-error").textContent = "Password changed. Log in with your new password.";
            show("login");
        } catch (error) {
            $("reset-error").textContent = error.message;
        }
    });
    $("reset-back").addEventListener("click", () => show("login"));

    $("login-warning").hidden = location.protocol === "https:";
    $("login-button").addEventListener("click", () => {
        $("login-error").textContent = "";
        show("login");
        $("login-username").focus();
    });
    $("portfolio-button").addEventListener("click", () => {
        location.href = urls.portfolioLoginUrl;
    });
    $("login-form").addEventListener("submit", (event) => {
        event.preventDefault();
        submitLogin(urls.loginUrl);
    });
    $("register").addEventListener("click", () => submitLogin(urls.registerUrl, {
        question: $("login-question").value, answer: $("login-answer").value,
    }));
    $("login-back").addEventListener("click", backToPlay);
    $("logout-button").addEventListener("click", async () => {
        await request(urls.logoutUrl, {}).catch(console.error);
        setAccount(null);
    });
    request(urls.accountUrl)
        .then((data) => {
            setAccount(data.username);
            if (data.portfolio_pending) showAccountLink(data.portfolio_pending);
            if (!data.username) return;
            return syncAccount();
        })
        .catch(console.error);
    $("confirm-yes").addEventListener("click", () => {
        $("confirm").hidden = true;
        onConfirm();
    });
    $("confirm-no").addEventListener("click", () => {
        $("confirm").hidden = true;
    });

    // Game

    let save = null;
    let pending = [];
    let busy = false;
    let rows = null;
    let lastView = null;
    let upgradeKey = "";
    let resourceOptions = "";
    let upgradeButtons = {};
    let onEnding = false;
    let timer = null;
    // Bumped when a game stops, so a request still in flight can't write over a deleted save
    let session = 0;
    const BACKUP_MS = 30_000;
    // Updates normally take well under 100 ms; one still waiting after this is stuck, so it is retried.
    const TICK_TIMEOUT_MS = 2000;
    let lastBackup = 0;

    // A clicked button stays marked as pressed until the request carrying that click comes back.
    function act(type, target = "", button = null) {
        if (button) button.dataset.pressed = "";
        pending.push({ type, target, button });
        tick();
    }

    async function tick() {
        if (busy || !save || document.hidden) return;
        busy = true;
        const mySession = session;
        const actions = pending;
        pending = [];
        const backup = Boolean(account) && Date.now() - lastBackup >= BACKUP_MS;
        let retryNow = false;
        let resend = false;
        const record = readRecord();
        try {
            const data = await request(urls.playUrl, {
                save,
                actions: actions.map(({ type, target }) => ({ type, target })),
                record,
                backup,
            }, TICK_TIMEOUT_MS);
            if (mySession !== session) return;
            if (backup) lastBackup = Date.now();
            save = data.save;
            writeSave(save);
            // Another tab may have written a newer record meanwhile, so a record this tick didn't change
            // isn't written back over it.
            if (!record || data.record.signature !== record.signature) writeRecord(data.record);
            render(data.view, new Set(actions.filter((action) => action.type === "resource").map((action) => action.target)));
            if (data.new_achievements.length) {
                if (!$("achievements").hidden) markEarnedAchievements();
                data.new_achievements.forEach(showToast);
            }
        } catch (error) {
            console.error(error);
            // A stalled or dropped connection, or a gateway error while the server restarts, not an answer from
            // the game: the clicks go out again.
            // The server works from the save sent with each request, so resending can't apply them twice.
            const timedOut = error.name === "TimeoutError";
            const restarting = [502, 503, 504].includes(error.status);
            resend = mySession === session && (timedOut || restarting || error instanceof TypeError);
            if (resend) {
                pending = actions.concat(pending);
                retryNow = timedOut;
            } else if (mySession === session) {
                // The server answered with an error, so retrying the same save would only fail again.
                stopGame();
                show("main-menu");
                $("menu-error").textContent = error.message;
            }
        } finally {
            if (mySession === session) busy = false;
            if (!resend) {
                for (const action of actions) {
                    if (action.button) delete action.button.dataset.pressed;
                }
            }
        }
        if (retryNow || (pending.length && !resend)) tick();
    }

    function startGame(loaded) {
        $("menu-error").textContent = "";
        save = loaded;
        lastBackup = Date.now();
        document.title = `Dead But Dreaming - ${save.player_name}`;
        const nameStyle = save.player_name.toLowerCase();
        applyStyle(hasStyle(nameStyle) ? nameStyle : "cthulhu");
        show("game");
        tick();
        timer = setInterval(tick, TICK_MS);
    }

    function stopGame() {
        clearInterval(timer);
        session += 1;
        save = null;
        pending = [];
        busy = false;
        rows = null;
        lastView = null;
        upgradeKey = "";
        upgradeButtons = {};
        resourceOptions = "";
        onEnding = false;
        document.title = "Dead But Dreaming";
    }

    $("main-menu-button").addEventListener("click", () => {
        if (save) stopGame();
        show("main-menu");
    });
    document.addEventListener("visibilitychange", tick);
    // sendBeacon is delivered even while the page is closing, so the account gets the final save.
    window.addEventListener("pagehide", () => {
        if (!account || !save) return;
        const body = JSON.stringify({
            saves: { [save.player_name]: save }, record: readRecord(), reply: false,
        });
        navigator.sendBeacon(urls.syncUrl, new Blob([body], { type: "application/json" }));
    });
    // Taps on one resource closer together than this are dropped, which keeps a hammered button to about
    // the server's cap of three taps per tick.
    const TAP_MS = 80;
    $("game").addEventListener("click", (event) => {
        const button = event.target.closest("[data-action]");
        if (!button) return;
        if (button.dataset.action === "resource") {
            const row = rows[button.dataset.target];
            if (Date.now() - row.lastTap < TAP_MS) return;
            row.lastTap = Date.now();
        }
        act(button.dataset.action, button.dataset.target, button);
    });
    $("new-world").addEventListener("click", () => act("reset"));
    $("endless").addEventListener("click", () => act("endless"));
    $("delete-world").addEventListener("click", () => {
        confirmDelete(save.player_name, () => {
            stopGame();
            show("main-menu");
        });
    });
    for (const id of ["type-filter", "resource-filter"]) {
        $(id).addEventListener("change", () => {
            if (lastView) renderUpgrades(lastView);
        });
    }

    function buildRows(resources) {
        rows = {};
        $("resources").replaceChildren(...resources.map((resource) => {
            const row = el("div", "resource-row");
            const button = el("button", "resource");
            const detail = el("span", "resource-detail number");
            const fill = el("span", "progress-fill");
            const progress = el("span", "progress");
            const manager = el("button", "manager");
            const managerCost = el("span", "manager-cost number");
            button.type = manager.type = "button";
            button.dataset.action = "resource";
            manager.dataset.action = "manager";
            button.dataset.target = manager.dataset.target = resource.key;
            progress.append(fill);
            button.append(el("span", "resource-name", resource.name), detail, progress);
            manager.append(el("span", "manager-name", resource.manager_name), managerCost);
            row.append(button, manager);
            rows[resource.key] = { button, detail, fill, manager, managerCost, barKey: "", lastProgress: 0, lastTap: 0 };
            return row;
        }));
    }

    // The server only reports progress a few times a second, so a running bar is a CSS animation
    // lasting one cycle, started at the reported progress. It restarts only when the cycle changes
    // (a speed upgrade, a manager, or a new click) or a tap moved it, so it doesn't jump between updates.
    function renderBar(row, resource, tapped) {
        let key = "idle";
        if (resource.unlocked && resource.processing) {
            key = resource.solid_bar ? "solid" : `run ${resource.cycle_seconds} ${resource.has_manager}`;
        }
        const clickedAgain = !resource.has_manager && resource.progress < row.lastProgress;
        row.lastProgress = resource.progress;
        if (key === row.barKey && !clickedAgain && !tapped) return;
        row.barKey = key;

        const fill = row.fill;
        fill.style.animation = "none";
        if (key === "idle" || key === "solid") {
            fill.style.transform = key === "solid" ? "scaleX(1)" : "scaleX(0)";
            return;
        }
        fill.style.transform = "";
        void fill.offsetWidth;
        const seconds = resource.cycle_seconds;
        const repeat = resource.has_manager ? "infinite" : "1";
        fill.style.animation = `fill-bar ${seconds}s linear ${-resource.progress * seconds}s ${repeat} forwards`;
    }

    function syncResourceFilter(resources) {
        const unlocked = resources.filter((resource) => resource.unlocked);
        const key = unlocked.map((resource) => resource.key).join(",");
        if (key === resourceOptions) return;
        resourceOptions = key;
        const select = $("resource-filter");
        const current = select.value;
        select.replaceChildren(
            new Option("All resources", ""),
            ...unlocked.map((resource) => new Option(resource.name, resource.key)),
        );
        select.value = unlocked.some((resource) => resource.key === current) ? current : "";
    }

    function upgradeItem(upgrade) {
        const button = el("button", "upgrade-button");
        const top = el("span", "upgrade-top");
        button.type = "button";
        button.dataset.action = "upgrade";
        button.dataset.target = upgrade.id;
        top.append(el("span", "upgrade-name", upgrade.name), el("span", "number", formatNumber(upgrade.cost)));
        button.append(top, el("span", "upgrade-detail", upgrade.description));
        upgradeButtons[upgrade.id] = button;
        return button;
    }

    function placeChildren(container, nodes) {
        const keep = new Set(nodes);
        for (const child of [...container.children]) {
            if (!keep.has(child)) child.remove();
        }
        nodes.forEach((node, index) => {
            if (container.children[index] !== node) container.insertBefore(node, container.children[index] || null);
        });
    }

    function renderUpgrades(view) {
        syncResourceFilter(view.resources);
        const type = $("type-filter").value;
        const resource = $("resource-filter").value;
        const shown = view.upgrades.filter((upgrade) =>
            (!type || upgrade.type === type) && (!resource || upgrade.resource === resource));

        // Buttons that stay on the list are kept, not rebuilt, so a click that is halfway done when a
        // purchase changes the list still lands.
        const key = [type, resource, ...shown.map((upgrade) => upgrade.id)].join(",");
        if (key !== upgradeKey) {
            upgradeKey = key;
            const shownIds = new Set(shown.map((upgrade) => upgrade.id));
            for (const id of Object.keys(upgradeButtons)) {
                if (!shownIds.has(id)) delete upgradeButtons[id];
            }
            for (const group of ["speed", "production"]) {
                const items = shown.filter((upgrade) => upgrade.type === group);
                const section = $(`${group}-upgrades`);
                section.hidden = items.length === 0;
                placeChildren(section.querySelector(".upgrade-items"),
                    items.map((upgrade) => upgradeButtons[upgrade.id] || upgradeItem(upgrade)));
            }
            $("no-upgrades").hidden = shown.length > 0;
        }
        for (const upgrade of shown) {
            setClass(upgradeButtons[upgrade.id], `upgrade-button ${upgrade.affordable ? "affordable" : "unaffordable"}`);
        }
    }

    function render(view, tapped = new Set()) {
        setText($("player-name"), `Great Old One: ${view.player_name}`);
        setText($("sanity"), formatNumber(view.sanity));
        setText($("difficulty-label"), `Difficulty: ${view.difficulty} in ${view.mode}`);
        setText($("dream-time"), `Time Since Dream Began: ${view.dream_time}`);
        setText($("worlds-devoured"), `Worlds Devoured: ${formatNumber(view.worlds_devoured)}`);
        $("devoured-label").hidden = !view.endless;
        if (view.endless) setText($("devoured-label"), `World devoured in ${view.devoured_time}`);

        if (view.ending !== onEnding) {
            onEnding = view.ending;
            show(onEnding ? "ending" : "game");
        }
        if (view.ending) {
            setText($("ending-time"), view.devoured_time);
            setText($("ending-difficulty"), view.difficulty_name);
            setText($("ending-mode"), view.mode);
            setText($("ending-worlds"), formatNumber(view.worlds_devoured));
        }

        if (!rows) buildRows(view.resources);
        for (const resource of view.resources) {
            const row = rows[resource.key];
            if (resource.unlocked) {
                setClass(row.button, "resource unlocked");
                setText(row.detail, `${formatNumber(resource.rate)} Sanity`);
                row.manager.hidden = false;
                const managerState = resource.has_manager ? "hired" : resource.can_hire ? "affordable" : "unaffordable";
                setClass(row.manager, `manager ${managerState}`);
                setText(row.managerCost, resource.has_manager ? "Hired" : formatNumber(resource.manager_cost));
            } else {
                setClass(row.button, `resource locked ${resource.can_unlock ? "affordable" : "unaffordable"}`);
                setText(row.detail, `Unlock: ${formatNumber(resource.unlock_cost)}`);
                row.manager.hidden = true;
            }
            renderBar(row, resource, view.clicker && tapped.has(resource.key));
        }

        lastView = view;
        renderUpgrades(view);
    }
})();

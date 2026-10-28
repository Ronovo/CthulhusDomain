// Display only: the game itself runs in Python (webapp.py). This keeps the save in localStorage,
// sends it to the server with the player's clicks, and shows what comes back.
(() => {
    const SAVE_PREFIX = "cthulhus-dominion:save:";
    const TICK_MS = 250;
    const urls = document.body.dataset;
    const $ = (id) => document.getElementById(id);

    function readSave(name) {
        try {
            const raw = localStorage.getItem(SAVE_PREFIX + name);
            return raw ? JSON.parse(raw) : null;
        } catch {
            return null;
        }
    }

    function writeSave(save) {
        try {
            localStorage.setItem(SAVE_PREFIX + save.player_name, JSON.stringify(save));
        } catch {
        }
    }

    function deleteSave(name) {
        try {
            localStorage.removeItem(SAVE_PREFIX + name);
        } catch {
        }
        if (account) request(urls.deleteSaveUrl, { name }).catch(console.error);
    }

    function listSaves() {
        try {
            return Object.keys(localStorage)
                .filter((key) => key.startsWith(SAVE_PREFIX))
                .map((key) => key.slice(SAVE_PREFIX.length))
                .sort();
        } catch {
            return [];
        }
    }

    async function request(url, body) {
        const options = body === undefined ? {} : {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        };
        const response = await fetch(url, options);
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.error || `${url} returned ${response.status}`);
        }
        return response.json();
    }

    function show(screen) {
        for (const section of document.querySelectorAll(".screen")) section.hidden = section.id !== screen;
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

    const STYLE_KEY = "cthulhus-dominion:style";
    const stylePicker = $("style-picker");

    function hasStyle(style) {
        return [...stylePicker.options].some((option) => option.value === style);
    }

    function applyStyle(style) {
        document.documentElement.dataset.style = style;
        stylePicker.value = style;
    }

    try {
        const saved = localStorage.getItem(STYLE_KEY);
        if (saved && hasStyle(saved)) applyStyle(saved);
    } catch {
    }
    stylePicker.addEventListener("change", () => {
        applyStyle(stylePicker.value);
        try {
            localStorage.setItem(STYLE_KEY, stylePicker.value);
        } catch {
        }
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
        const data = await request(urls.newGameUrl, { name, difficulty: $("difficulty").value });
        startGame(data.save);
    }

    // Achievements and the devour tally belong to this browser, not to one save, so they survive
    // deleting a world.
    const ACHIEVEMENTS_KEY = "cthulhus-dominion:achievements";
    const DEVOURED_KEY = "cthulhus-dominion:devoured";

    function readDevoured() {
        try {
            const devoured = JSON.parse(localStorage.getItem(DEVOURED_KEY));
            return devoured && typeof devoured === "object" && !Array.isArray(devoured) ? devoured : {};
        } catch {
            return {};
        }
    }

    function writeDevoured(devoured) {
        try {
            localStorage.setItem(DEVOURED_KEY, JSON.stringify(devoured));
        } catch {
        }
    }

    function readAchievements() {
        try {
            const earned = JSON.parse(localStorage.getItem(ACHIEVEMENTS_KEY));
            return Array.isArray(earned) ? earned : [];
        } catch {
            return [];
        }
    }

    function addAchievements(ids) {
        try {
            localStorage.setItem(ACHIEVEMENTS_KEY, JSON.stringify([...new Set([...readAchievements(), ...ids])]));
        } catch {
        }
    }

    function markEarnedAchievements() {
        const earned = new Set(readAchievements());
        for (const item of document.querySelectorAll("[data-achievement]")) {
            item.classList.toggle("earned", earned.has(item.dataset.achievement));
        }
    }

    function showAchievements() {
        markEarnedAchievements();
        $("achievements-back").textContent = save ? "Back to Game" : "Back to Menu";
        show("achievements");
    }

    function showToast(achievement) {
        const toast = el("div", "toast");
        toast.append(el("span", "toast-title", "Achievement unlocked"), el("span", "toast-name", achievement.name));
        $("toasts").append(toast);
        setTimeout(() => toast.remove(), 5000);
    }

    function showLoadList() {
        const names = listSaves();
        $("no-saves").hidden = names.length > 0;
        $("saves").replaceChildren(...names.map((name) => {
            const row = el("div", "save-row");
            const load = el("button", "menu-button", name);
            const remove = el("button", "delete-button", "Delete");
            load.type = remove.type = "button";
            load.addEventListener("click", () => startGame(readSave(name)));
            remove.addEventListener("click", () => askConfirm(`Delete ${name}? This can't be undone.`, () => {
                deleteSave(name);
                showLoadList();
            }));
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
    $("random-name").addEventListener("click", async () => {
        $("name-input").value = (await request(urls.randomNameUrl)).name;
    });
    $("name-form").addEventListener("submit", (event) => {
        event.preventDefault();
        confirmName();
    });
    for (const button of document.querySelectorAll(".back")) {
        button.addEventListener("click", () => show("main-menu"));
    }
    $("footer-achievements").addEventListener("click", showAchievements);
    $("achievements-back").addEventListener("click", () => show(save ? "game" : "main-menu"));

    // Account: optional. Logging in merges this browser's progress with the account's, and while
    // logged in the server also keeps every save in the account.

    let account = null;

    function setAccount(username) {
        account = username;
        $("account-name").textContent = username || "";
        $("account-name").hidden = !username;
        $("login-button").hidden = Boolean(username);
        $("logout-button").hidden = !username;
    }

    async function syncAccount() {
        const saves = {};
        for (const name of listSaves()) {
            const local = readSave(name);
            if (local) saves[name] = local;
        }
        const merged = await request(urls.syncUrl, {
            saves, achievements: readAchievements(), devoured: readDevoured(),
        });
        Object.values(merged.saves).forEach(writeSave);
        addAchievements(merged.achievements);
        writeDevoured(merged.devoured);
    }

    async function submitLogin(url) {
        $("login-error").textContent = "";
        try {
            const data = await request(url, {
                username: $("login-username").value, password: $("login-password").value,
            });
            $("login-password").value = "";
            setAccount(data.username);
            await syncAccount();
            show(save ? "game" : "main-menu");
        } catch (error) {
            $("login-error").textContent = error.message;
        }
    }

    $("login-warning").hidden = location.protocol === "https:";
    $("login-button").addEventListener("click", () => {
        $("login-error").textContent = "";
        show("login");
        $("login-username").focus();
    });
    $("login-form").addEventListener("submit", (event) => {
        event.preventDefault();
        submitLogin(urls.loginUrl);
    });
    $("register").addEventListener("click", () => submitLogin(urls.registerUrl));
    $("login-back").addEventListener("click", () => show(save ? "game" : "main-menu"));
    $("logout-button").addEventListener("click", async () => {
        await request(urls.logoutUrl, {}).catch(console.error);
        setAccount(null);
    });
    request(urls.accountUrl)
        .then((data) => {
            if (!data.username) return;
            setAccount(data.username);
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

    function act(type, target = "") {
        pending.push({ type, target });
        tick();
    }

    async function tick() {
        if (busy || !save || document.hidden) return;
        busy = true;
        const mySession = session;
        const actions = pending;
        pending = [];
        try {
            const data = await request(urls.playUrl, {
                save, actions, achievements: readAchievements(), devoured: readDevoured(),
            });
            if (mySession !== session) return;
            save = data.save;
            writeSave(save);
            writeDevoured(data.devoured);
            render(data.view);
            if (data.new_achievements.length) {
                addAchievements(data.new_achievements.map((achievement) => achievement.id));
                if (!$("achievements").hidden) markEarnedAchievements();
                data.new_achievements.forEach(showToast);
            }
        } catch (error) {
            console.error(error);
        } finally {
            if (mySession === session) busy = false;
        }
        if (pending.length) tick();
    }

    function startGame(loaded) {
        save = loaded;
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
        resourceOptions = "";
        onEnding = false;
        document.title = "Dead But Dreaming";
    }

    document.addEventListener("visibilitychange", tick);
    $("game").addEventListener("click", (event) => {
        const button = event.target.closest("[data-action]");
        if (button) act(button.dataset.action, button.dataset.target);
    });
    $("new-world").addEventListener("click", () => act("reset"));
    $("endless").addEventListener("click", () => act("endless"));
    $("delete-world").addEventListener("click", () => {
        const name = save.player_name;
        askConfirm(`Delete ${name}? This can't be undone.`, () => {
            stopGame();
            deleteSave(name);
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
            rows[resource.key] = { button, detail, fill, manager, managerCost, barKey: "", lastProgress: 0 };
            return row;
        }));
    }

    // The server only reports progress a few times a second, so a running bar is a CSS animation
    // lasting one cycle, started at the reported progress. It restarts only when the cycle changes
    // (a speed upgrade, a manager, or a new click), so it doesn't jump between updates.
    function renderBar(row, resource) {
        let key = "idle";
        if (resource.unlocked && resource.processing) {
            key = resource.solid_bar ? "solid" : `run ${resource.cycle_seconds} ${resource.has_manager}`;
        }
        const clickedAgain = !resource.has_manager && resource.progress < row.lastProgress;
        row.lastProgress = resource.progress;
        if (key === row.barKey && !clickedAgain) return;
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

    function renderUpgrades(view) {
        syncResourceFilter(view.resources);
        const type = $("type-filter").value;
        const resource = $("resource-filter").value;
        const shown = view.upgrades.filter((upgrade) =>
            (!type || upgrade.type === type) && (!resource || upgrade.resource === resource));

        const key = [type, resource, ...shown.map((upgrade) => upgrade.id)].join(",");
        if (key !== upgradeKey) {
            upgradeKey = key;
            upgradeButtons = {};
            for (const group of ["speed", "production"]) {
                const items = shown.filter((upgrade) => upgrade.type === group);
                const section = $(`${group}-upgrades`);
                section.hidden = items.length === 0;
                section.querySelector(".upgrade-items").replaceChildren(...items.map(upgradeItem));
            }
            $("no-upgrades").hidden = shown.length > 0;
        }
        for (const upgrade of shown) {
            setClass(upgradeButtons[upgrade.id], `upgrade-button ${upgrade.affordable ? "affordable" : "unaffordable"}`);
        }
    }

    function render(view) {
        setText($("player-name"), `Great Old One: ${view.player_name}`);
        setText($("sanity"), `Sanity: ${formatNumber(view.sanity)}`);
        setText($("difficulty-label"), `Difficulty: ${view.difficulty}`);
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
            renderBar(row, resource);
        }

        lastView = view;
        renderUpgrades(view);
    }
})();

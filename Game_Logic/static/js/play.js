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
        if (!response.ok) throw new Error(`${url} returned ${response.status}`);
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

    function act(type, target = "") {
        pending.push({ type, target });
        tick();
    }

    async function tick() {
        if (busy || !save || document.hidden) return;
        busy = true;
        const actions = pending;
        pending = [];
        try {
            const data = await request(urls.playUrl, { save, actions });
            save = data.save;
            writeSave(save);
            render(data.view);
        } catch (error) {
            console.error(error);
        } finally {
            busy = false;
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
        setInterval(tick, TICK_MS);
        document.addEventListener("visibilitychange", tick);
    }

    $("game").addEventListener("click", (event) => {
        const button = event.target.closest("[data-action]");
        if (button) act(button.dataset.action, button.dataset.target);
    });
    $("world-end-yes").addEventListener("click", () => {
        $("world-end").hidden = true;
        act("reset");
    });
    $("world-end-no").addEventListener("click", () => {
        $("world-end").hidden = true;
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
        if (view.world_end) $("world-end").hidden = false;
    }
})();

const state = {
    username: localStorage.getItem("luculentUser"),
    documents: [],
    currentDocument: null,
    currentPart: null,
    currentWord: null,
    shownAt: null
};

const byId = id => document.getElementById(id);

async function api(url, options = {}) {
    const response = await fetch(url, options);
    const text = await response.text();
    const data = text ? JSON.parse(text) : null;
    if (!response.ok) {
        throw new Error(data?.error || `${response.status} ${response.statusText}`);
    }
    return data;
}

function jsonOptions(method, body) {
    return {
        method,
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(body)
    };
}

function setView(name) {
    for (const view of document.querySelectorAll(".view")) {
        view.hidden = view.id !== `${name}-view`;
    }
    for (const button of document.querySelectorAll(".nav-button")) {
        button.classList.toggle("active", button.dataset.view === name);
    }
    if (name === "dashboard") loadDashboard();
    if (name === "study") loadStudyWord();
}

async function loadUsers() {
    const {users} = await api("/users");
    const list = byId("user-list");
    list.replaceChildren();
    for (const user of users) {
        const button = document.createElement("button");
        button.className = "user-button";
        button.textContent = user.username;
        button.addEventListener("click", () => selectUser(user.username));
        list.append(button);
    }
    if (users.length === 0) {
        const message = document.createElement("p");
        message.className = "muted";
        message.textContent = "No readers yet.";
        list.append(message);
    }
    return users;
}

function selectUser(username) {
    state.username = username;
    localStorage.setItem("luculentUser", username);
    byId("user-screen").hidden = true;
    byId("application").hidden = false;
    byId("switch-user").textContent = username;
    byId("welcome-heading").textContent = `Welcome back, ${username}`;
    setView("dashboard");
}

async function loadDashboard() {
    if (!state.username) return;
    const list = byId("document-list");
    list.innerHTML = '<p class="muted">Loading documents and readability…</p>';
    try {
        const query = new URLSearchParams({username: state.username});
        const [due, documents] = await Promise.all([
            api(`/due-count?${query}`),
            api(`/documents?${query}`)
        ]);
        byId("due-count").textContent = due.due_count;
        byId("study-due-count").textContent = due.due_count;
        state.documents = documents.documents;
        renderDocuments();
    } catch (error) {
        byId("document-list").textContent = error.message;
    }
}

function renderDocuments() {
    const list = byId("document-list");
    list.replaceChildren();
    if (state.documents.length === 0) {
        const empty = document.createElement("div");
        empty.className = "empty-state";
        empty.innerHTML = "<h3>Your library is empty</h3><p>Import a Korean text file or article to begin.</p>";
        list.append(empty);
        return;
    }
    for (const documentItem of state.documents) {
        const card = document.createElement("details");
        card.className = "document-card";
        const summary = document.createElement("summary");
        summary.textContent = `${documentItem.title} · ${documentItem.parts.length} parts`;
        card.append(summary);
        const actions = document.createElement("div");
        actions.className = "document-actions";
        const remove = document.createElement("button");
        remove.className = "text-button danger";
        remove.textContent = "Delete document";
        remove.addEventListener("click", () => deleteDocument(documentItem));
        actions.append(remove);
        card.append(actions);
        const parts = document.createElement("div");
        parts.className = "part-list";
        documentItem.parts.forEach((part, index) => {
            const row = document.createElement("div");
            row.className = "part-row";
            const number = document.createElement("strong");
            number.textContent = index + 1;
            const text = document.createElement("button");
            text.className = "part-preview";
            text.textContent = preview(part.text);
            text.addEventListener("click", () => openPart(documentItem, part));
            const readability = document.createElement("span");
            const readabilityBand = getReadabilityBand(part.readability);
            readability.className = `readability ${readabilityBand.className}`;
            readability.textContent = `${Math.round(part.readability * 100)}%`;
            readability.title = readabilityBand.description;
            row.append(number, text, readability);
            if (part.active) {
                const status = document.createElement("span");
                status.className = "active-badge";
                status.textContent = "Active";
                row.append(status);
            } else {
                const activate = document.createElement("button");
                activate.className = "activate-part";
                activate.textContent = "Activate";
                activate.addEventListener("click", () => {
                    activatePartFromDashboard(part, activate);
                });
                row.append(activate);
            }
            parts.append(row);
        });
        card.append(parts);
        list.append(card);
    }
}

function getReadabilityBand(readability) {
    if (readability >= 0.98) {
        return {
            className: "readability-excellent",
            description: "98%+: comfortable unassisted reading"
        };
    }
    if (readability >= 0.95) {
        return {
            className: "readability-good",
            description: "95–97%: assisted reading with occasional difficulty"
        };
    }
    if (readability >= 0.90) {
        return {
            className: "readability-challenging",
            description: "90–94%: challenging reading"
        };
    }
    if (readability >= 0.80) {
        return {
            className: "readability-difficult",
            description: "80–89%: difficult reading"
        };
    }
    return {
        className: "readability-very-difficult",
        description: "Below 80%: very difficult reading"
    };
}

async function activatePartFromDashboard(part, button) {
    button.disabled = true;
    button.textContent = "Activating…";
    try {
        await api(
            `/doc-parts/${part.id}/activate`,
            jsonOptions("POST", {username: state.username})
        );
        await loadDashboard();
    } catch (error) {
        button.disabled = false;
        button.textContent = "Activate";
        byId("import-status").textContent = error.message;
    }
}

async function deleteDocument(documentItem) {
    if (!window.confirm(`Delete “${documentItem.title}” from your library?`)) return;
    try {
        await api(
            `/documents/${documentItem.id}`,
            jsonOptions("DELETE", {username: state.username})
        );
        state.documents = state.documents.filter(item => item.id !== documentItem.id);
        renderDocuments();
        await loadDashboard();
    } catch (error) {
        byId("import-status").textContent = error.message;
    }
}

function preview(text) {
    return text.length > 110 ? `${text.slice(0, 110)}…` : text;
}

async function openPart(documentItem, part) {
    state.currentDocument = documentItem;
    state.currentPart = part;
    byId("previous-part").disabled = true;
    byId("next-part").disabled = true;
    const query = new URLSearchParams({username: state.username});
    byId("reader-title").textContent = documentItem.title;
    byId("reader-position").textContent = `Part ${part.position + 1} of ${documentItem.parts.length}`;
    byId("activate-reading").textContent = "Loading…";
    byId("activate-reading").disabled = true;
    byId("reader-loading-title").textContent = "Preparing this reading";
    byId("reader-loading-message").textContent = "Analyzing the text against your vocabulary…";
    byId("reader-loading").hidden = false;
    byId("reader-text").hidden = true;
    setView("reader");
    try {
        const data = await api(`/doc-parts/${part.id}?${query}`);
        state.currentPart = data.doc_part;
        byId("activate-reading").textContent = part.active ? "Active reading" : "Make active";
        byId("activate-reading").disabled = part.active;
        renderMarkedText(data.doc_part.marked_text);
        byId("reader-loading").hidden = true;
        byId("reader-text").hidden = false;
        updateReaderNavigation();
    } catch (error) {
        byId("reader-loading-title").textContent = "Could not prepare this reading";
        byId("reader-loading-message").textContent = error.message;
        updateReaderNavigation();
    }
}

function updateReaderNavigation() {
    const index = state.currentDocument.parts.findIndex(
        part => part.id === state.currentPart.id
    );
    byId("previous-part").disabled = index <= 0;
    byId("next-part").disabled = index >= state.currentDocument.parts.length - 1;
}

function moveToAdjacentPart(offset) {
    const index = state.currentDocument.parts.findIndex(
        part => part.id === state.currentPart.id
    );
    const part = state.currentDocument.parts[index + offset];
    if (part) openPart(state.currentDocument, part);
}

function renderMarkedText(markedText) {
    const article = byId("reader-text");
    article.replaceChildren();
    markedText.split("**").forEach((text, index) => {
        const node = index % 2 ? document.createElement("strong") : document.createElement("span");
        node.textContent = text;
        article.append(node);
    });
}

async function activateCurrentPart() {
    try {
        await api(
            `/doc-parts/${state.currentPart.id}/activate`,
            jsonOptions("POST", {username: state.username})
        );
        state.currentPart.active = true;
        byId("activate-reading").textContent = "Active reading";
        byId("activate-reading").disabled = true;
        await loadDashboard();
    } catch (error) {
        byId("reader-text").textContent = error.message;
    }
}

async function loadStudyWord() {
    byId("study-status").textContent = "";
    byId("answer").hidden = true;
    byId("rating-row").hidden = true;
    byId("reveal-answer").hidden = false;
    try {
        const query = new URLSearchParams({username: state.username});
        const [{word}, due] = await Promise.all([
            api(`/get-due-word?${query}`),
            api(`/study-due-count?${query}`)
        ]);
        state.currentWord = word;
        state.shownAt = Date.now();
        byId("study-due-count").textContent = due.due_count;
        byId("study-empty").hidden = word !== null;
        byId("study-card").hidden = word === null;
        if (word === null) return;
        byId("study-word").textContent = word.lemma;
        byId("word-meta").textContent = `${word.part_of_speech} · ${word.status}`;
        renderMeanings();
    } catch (error) {
        byId("study-status").textContent = error.message;
    }
}

function renderMeanings() {
    const list = byId("meaning-list");
    list.replaceChildren();
    for (const meaning of state.currentWord.user_meanings) {
        list.append(meaningElement(meaning, true));
    }
    for (const meaning of state.currentWord.meanings) {
        list.append(meaningElement(meaning, false));
    }
    if (!state.currentWord.user_meanings.length && !state.currentWord.meanings.length) {
        const message = document.createElement("p");
        message.className = "muted";
        message.textContent = "No meanings are available yet. Add your own below.";
        list.append(message);
    }
}

function meaningElement(meaning, userOwned) {
    const element = document.createElement("section");
    element.className = `meaning${userOwned ? " user" : ""}`;
    if (userOwned) {
        const header = document.createElement("header");
        const label = document.createElement("strong");
        label.textContent = "Your meaning";
        header.append(label);
        const remove = document.createElement("button");
        remove.className = "text-button";
        remove.textContent = "Delete";
        remove.addEventListener("click", () => deleteMeaning(meaning.id));
        header.append(remove);
        element.append(header);
    }
    if (meaning.gloss) {
        const gloss = document.createElement("p");
        gloss.className = "meaning-gloss";
        gloss.textContent = meaning.gloss;
        element.append(gloss);
    }
    for (const value of [meaning.english_definition, meaning.korean_definition]) {
        if (!value) continue;
        const paragraph = document.createElement("p");
        paragraph.textContent = value;
        element.append(paragraph);
    }
    return element;
}

async function deleteMeaning(id) {
    try {
        await api(`/user-meanings/${id}`, jsonOptions("DELETE", {username: state.username}));
        state.currentWord.user_meanings = state.currentWord.user_meanings.filter(item => item.id !== id);
        renderMeanings();
    } catch (error) {
        byId("study-status").textContent = error.message;
    }
}

async function addMeaning(event) {
    event.preventDefault();
    try {
        const data = await api(
            `/words/${state.currentWord.id}/user-meanings`,
            jsonOptions("POST", {
                username: state.username,
                gloss: byId("gloss").value,
                english_definition: byId("english-definition").value,
                korean_definition: byId("korean-definition").value
            })
        );
        state.currentWord.user_meanings.push(data.user_meaning);
        event.target.reset();
        renderMeanings();
    } catch (error) {
        byId("study-status").textContent = error.message;
    }
}

async function recordResponse(response) {
    const duration = state.shownAt === null ? null : Date.now() - state.shownAt;
    try {
        const data = await api(
            `/words/${state.currentWord.id}/response`,
            jsonOptions("POST", {
                username: state.username,
                response,
                duration_ms: duration
            })
        );
        byId("study-due-count").textContent = data.due_count;
        await loadStudyWord();
    } catch (error) {
        byId("study-status").textContent = error.message;
    }
}

async function importUrl(event) {
    event.preventDefault();
    setImportButtonsDisabled(true);
    try {
        await showImportMessage();
        await api("/documents", jsonOptions("POST", {
            username: state.username,
            url: byId("document-url").value
        }));
        event.target.reset();
        byId("import-status").textContent = "Import complete.";
        await loadDashboard();
    } catch (error) {
        byId("import-status").textContent = error.message;
    } finally {
        setImportButtonsDisabled(false);
    }
}

async function importFile(event) {
    event.preventDefault();
    const data = new FormData();
    data.append("username", state.username);
    data.append("file", byId("document-file").files[0]);
    setImportButtonsDisabled(true);
    try {
        await showImportMessage();
        await api("/documents", {method: "POST", body: data});
        event.target.reset();
        byId("import-status").textContent = "Import complete.";
        await loadDashboard();
    } catch (error) {
        byId("import-status").textContent = error.message;
    } finally {
        setImportButtonsDisabled(false);
    }
}

function setImportButtonsDisabled(disabled) {
    for (const button of document.querySelectorAll(".import-panel button[type=submit]")) {
        button.disabled = disabled;
    }
}

async function showImportMessage() {
    byId("import-status").textContent = "Checking the Korean dictionary…";
    const status = await api("/lexicon-status");
    byId("import-status").textContent = status.installed
        ? "Importing and analyzing the document…"
        : "Downloading and installing the Korean Basic Dictionary. The first import may take several minutes…";
}

byId("create-user-form").addEventListener("submit", async event => {
    event.preventDefault();
    try {
        const data = await api("/users", jsonOptions("POST", {
            username: byId("new-username").value
        }));
        selectUser(data.user.username);
    } catch (error) {
        alert(error.message);
    }
});
byId("switch-user").addEventListener("click", () => {
    state.username = null;
    localStorage.removeItem("luculentUser");
    byId("application").hidden = true;
    byId("user-screen").hidden = false;
    loadUsers();
});
byId("brand").addEventListener("click", () => setView("dashboard"));
for (const button of document.querySelectorAll(".nav-button")) {
    button.addEventListener("click", () => setView(button.dataset.view));
}
byId("study-now").addEventListener("click", () => setView("study"));
byId("refresh-dashboard").addEventListener("click", loadDashboard);
byId("reader-back").addEventListener("click", () => setView("dashboard"));
byId("previous-part").addEventListener("click", () => moveToAdjacentPart(-1));
byId("next-part").addEventListener("click", () => moveToAdjacentPart(1));
byId("activate-reading").addEventListener("click", activateCurrentPart);
byId("reveal-answer").addEventListener("click", () => {
    byId("answer").hidden = false;
    byId("rating-row").hidden = false;
    byId("reveal-answer").hidden = true;
});
byId("meaning-form").addEventListener("submit", addMeaning);
for (const button of document.querySelectorAll("[data-response]")) {
    button.addEventListener("click", () => recordResponse(button.dataset.response));
}
byId("url-form").addEventListener("submit", importUrl);
byId("file-form").addEventListener("submit", importFile);

loadUsers().then(users => {
    if (state.username && users.some(user => user.username === state.username)) {
        selectUser(state.username);
    } else {
        state.username = null;
        localStorage.removeItem("luculentUser");
    }
});

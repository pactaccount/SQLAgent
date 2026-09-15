// --- 3D Background (Three.js) ---
const init3D = () => {
    const container = document.getElementById('canvas-container');
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
    camera.position.z = 50;

    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(renderer.domElement);

    const geometry = new THREE.BufferGeometry();
    const particlesCount = 700;
    const posArray = new Float32Array(particlesCount * 3);

    for(let i = 0; i < particlesCount * 3; i++) {
        posArray[i] = (Math.random() - 0.5) * 150;
    }
    geometry.setAttribute('position', new THREE.BufferAttribute(posArray, 3));

    const material = new THREE.PointsMaterial({
        size: 0.3, color: 0x6366f1, transparent: true, opacity: 0.6, blending: THREE.AdditiveBlending
    });

    const particlesMesh = new THREE.Points(geometry, material);
    scene.add(particlesMesh);

    let mouseX = 0; let mouseY = 0;
    document.addEventListener('mousemove', (event) => {
        mouseX = event.clientX / window.innerWidth - 0.5;
        mouseY = event.clientY / window.innerHeight - 0.5;
    });

    const clock = new THREE.Clock();
    const animate = () => {
        requestAnimationFrame(animate);
        const elapsedTime = clock.getElapsedTime();
        particlesMesh.rotation.y = elapsedTime * 0.05 + mouseX * 0.05;
        particlesMesh.rotation.x = elapsedTime * 0.02 + mouseY * 0.05;
        renderer.render(scene, camera);
    }
    animate();

    window.addEventListener('resize', () => {
        camera.aspect = window.innerWidth / window.innerHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(window.innerWidth, window.innerHeight);
    });
};
init3D();

// --- Splitter Logic ---
let isResizing = false;
let currentSplitter = null;
let startX, startY, startWidth, startHeight, prevNode, nextNode;

const initSplitters = () => {
    const splitters = [
        { id: 'split-1', type: 'vertical', prev: 'left-sidebar' },
        { id: 'split-2', type: 'horizontal', prev: 'sql-panel' },
        { id: 'split-3', type: 'vertical', prev: 'center-workspace', next: 'right-sidebar' }
    ];

    splitters.forEach(s => {
        const el = document.getElementById(s.id);
        if (!el) return;
        el.addEventListener('mousedown', (e) => {
            isResizing = true;
            currentSplitter = s;
            startX = e.clientX;
            startY = e.clientY;
            prevNode = document.getElementById(s.prev);
            if (s.next) nextNode = document.getElementById(s.next);
            
            if (s.type === 'vertical') {
                if (s.id === 'split-3' && s.next) {
                    startWidth = nextNode.getBoundingClientRect().width;
                } else {
                    startWidth = prevNode.getBoundingClientRect().width;
                }
            } else {
                startHeight = prevNode.getBoundingClientRect().height;
            }
            
            el.classList.add('dragging');
            document.body.style.cursor = s.type === 'vertical' ? 'col-resize' : 'row-resize';
        });
    });

    document.addEventListener('mousemove', (e) => {
        if (!isResizing || !currentSplitter) return;
        
        if (currentSplitter.type === 'vertical') {
            const dx = e.clientX - startX;
            if (currentSplitter.id === 'split-3') {
                let newWidth = startWidth - dx; // Moving left increases right sidebar width
                newWidth = Math.max(200, Math.min(newWidth, window.innerWidth - 300));
                nextNode.style.width = `${newWidth}px`;
                nextNode.style.minWidth = `${newWidth}px`;
            } else {
                let newWidth = startWidth + dx;
                newWidth = Math.max(150, Math.min(newWidth, window.innerWidth - 300));
                prevNode.style.width = `${newWidth}px`;
                prevNode.style.minWidth = `${newWidth}px`;
            }
        } else {
            const dy = e.clientY - startY;
            let newHeight = startHeight + dy;
            newHeight = Math.max(100, Math.min(newHeight, window.innerHeight - 150));
            prevNode.style.height = `${newHeight}px`;
            prevNode.style.flex = `0 0 ${newHeight}px`;
        }
    });

    document.addEventListener('mouseup', () => {
        if (isResizing) {
            isResizing = false;
            document.querySelectorAll('.splitter-vertical, .splitter-horizontal').forEach(el => el.classList.remove('dragging'));
            document.body.style.cursor = 'default';
        }
    });
};
initSplitters();

// --- Sidebar Toggles ---
window.toggleSidebar = (id) => {
    const el = document.getElementById(id);
    if (el) {
        el.classList.toggle('collapsed');
        if (id === 'left-sidebar') {
            const split = document.getElementById('split-1');
            if (split) split.style.display = el.classList.contains('collapsed') ? 'none' : 'block';
        } else if (id === 'right-sidebar') {
            const split = document.getElementById('split-3');
            if (split) split.style.display = el.classList.contains('collapsed') ? 'none' : 'block';
        }
    }
};

window.toggleBottomPanel = () => {
    const el = document.getElementById('data-panel');
    const splitter = document.getElementById('split-2');
    if (el) {
        el.classList.toggle('collapsed');
        if (splitter) {
            splitter.style.display = el.classList.contains('collapsed') ? 'none' : 'block';
        }
    }
};

// --- Session (Tabs) Management ---
let sessionCount = 0;
let activeSessionId = null;

const createNewSession = () => {
    sessionCount++;
    const id = `session-${sessionCount}`;
    
    // Chat Container
    const chatDiv = document.createElement('div');
    chatDiv.id = `chat-${id}`;
    chatDiv.style.display = 'none';
    chatDiv.classList.add('session-chat');
    chatDiv.innerHTML = `<div class="message system-msg"><div class="avatar">N</div><div class="bubble"><p>Hello. This is Tab ${sessionCount}. Ask a question.</p></div></div>`;
    document.getElementById('chat-container').appendChild(chatDiv);
    
    // SQL Viewer
    const sqlPre = document.createElement('pre');
    sqlPre.id = `sql-${id}`;
    sqlPre.style.display = 'none';
    sqlPre.innerHTML = `<code id="code-${id}"></code>`;
    document.getElementById('sql-content-container').appendChild(sqlPre);
    
    // Data Container
    const dataContainer = document.createElement('div');
    dataContainer.id = `data-${id}`;
    dataContainer.style.display = 'none';
    
    // Chart Canvas
    const canvas = document.createElement('canvas');
    canvas.id = `chart-${id}`;
    canvas.style.display = 'none';
    canvas.style.maxHeight = '300px';
    canvas.style.marginBottom = '20px';
    dataContainer.appendChild(canvas);
    
    // Data Table
    const dataTable = document.createElement('table');
    dataTable.id = `table-${id}`;
    dataTable.style.width = '100%';
    dataTable.innerHTML = `<thead id="thead-${id}"></thead><tbody id="tbody-${id}"></tbody>`;
    dataContainer.appendChild(dataTable);
    
    document.getElementById('data-content-container').appendChild(dataContainer);
    
    // Tab Button
    const tabBtn = document.createElement('div');
    tabBtn.className = 'tab';
    tabBtn.id = `tab-${id}`;
    tabBtn.innerHTML = `Tab ${sessionCount} <span class="tab-close" onclick="closeSession('${id}', event)">&times;</span>`;
    tabBtn.onclick = () => switchSession(id);
    
    const tabBar = document.getElementById('tab-bar');
    const addBtn = document.getElementById('tab-add-btn');
    tabBar.insertBefore(tabBtn, addBtn);
    
    switchSession(id);
};

window.switchSession = (id) => {
    if (activeSessionId) {
        const oldTab = document.getElementById(`tab-${activeSessionId}`);
        if (oldTab) oldTab.classList.remove('active');
        const oc = document.getElementById(`chat-${activeSessionId}`);
        if (oc) oc.style.display = 'none';
        const os = document.getElementById(`sql-${activeSessionId}`);
        if (os) os.style.display = 'none';
        const od = document.getElementById(`data-${activeSessionId}`);
        if (od) od.style.display = 'none';
    }
    
    activeSessionId = id;
    
    document.getElementById(`tab-${id}`).classList.add('active');
    document.getElementById(`chat-${id}`).style.display = 'block';
    document.getElementById(`sql-${id}`).style.display = 'block';
    document.getElementById(`data-${id}`).style.display = 'block';
    
    // Update Headers to show which tab is active
    const tabName = document.getElementById(`tab-${id}`).innerText.replace('×', '').trim();
    const chatTitle = document.getElementById('chat-header-title');
    const dataTitle = document.getElementById('data-header-title');
    if (chatTitle) chatTitle.innerText = `CHAT - ${tabName}`;
    if (dataTitle) dataTitle.innerText = `OUTPUT - ${tabName}`;
    
    // Scroll chat
    const chatScroll = document.getElementById('chat-container');
    chatScroll.scrollTop = chatScroll.scrollHeight;
};

window.closeSession = (id, e) => {
    e.stopPropagation();
    if (document.querySelectorAll('.tab:not(.tab-add)').length <= 1) return; // Prevent closing last tab
    
    document.getElementById(`tab-${id}`).remove();
    document.getElementById(`chat-${id}`).remove();
    document.getElementById(`sql-${id}`).remove();
    document.getElementById(`data-${id}`).remove();
    
    if (activeSessionId === id) {
        // Switch to the first available tab
        const firstTabId = document.querySelector('.tab:not(.tab-add)').id.replace('tab-', '');
        switchSession(firstTabId);
    }
};

// Initialize the Tab Bar add button and first session
document.getElementById('tab-bar').innerHTML = `<div class="tab-add" id="tab-add-btn" onclick="createNewSession()" title="New Chat Session">+</div>`;
createNewSession();

// Helpers to get active nodes
const getActiveChat = () => document.getElementById(`chat-${activeSessionId}`);
const getActiveCode = () => document.getElementById(`code-${activeSessionId}`);
const getActiveTHead = () => document.getElementById(`thead-${activeSessionId}`);
const getActiveTBody = () => document.getElementById(`tbody-${activeSessionId}`);


// --- Settings & State Management ---
let currentTenant = localStorage.getItem('tenant_id') || '';
let currentDbUri = localStorage.getItem('db_uri') || '';
let currentDbType = localStorage.getItem('db_type') || 'sqlite';

const updateConnectionStatus = () => {
    const ind = document.getElementById('connection-indicator');
    const txt = document.getElementById('connection-text');
    
    if (currentTenant && currentDbUri) {
        if (ind) {
            ind.style.background = 'var(--success)';
            ind.style.boxShadow = '0 0 8px var(--success)';
        }
        if (txt) txt.innerText = 'Connected: ' + currentTenant;
    } else {
        if (ind) {
            ind.style.background = 'var(--error)';
            ind.style.boxShadow = '0 0 8px var(--error)';
        }
        if (txt) txt.innerText = 'Disconnected';
    }
};

const toggleDbFields = () => {
    const type = document.getElementById('db-type-select').value;
    document.querySelectorAll('.db-fields-group').forEach(el => el.style.display = 'none');
    
    if (type === 'sqlite') {
        document.getElementById('fields-sqlite').style.display = 'block';
    } else if (type === 'postgresql' || type === 'mysql') {
        document.getElementById('fields-standard').style.display = 'block';
    } else if (type === 'snowflake') {
        document.getElementById('fields-snowflake').style.display = 'block';
    }
};

const openSettings = () => {
    document.getElementById('settings-modal').style.display = 'flex';
    document.getElementById('tenant-id-input').value = currentTenant;
    document.getElementById('db-type-select').value = currentDbType;
    toggleDbFields();
    
    // Attempt to pre-fill if it's sqlite
    if (currentDbType === 'sqlite' && currentDbUri.startsWith('sqlite:///')) {
        document.getElementById('sqlite-path').value = currentDbUri.replace('sqlite:///', '');
    }
};

const closeSettings = () => {
    document.getElementById('settings-modal').style.display = 'none';
};

const saveSettings = async () => {
    let t = document.getElementById('tenant-id-input').value.trim();
    if (!t) t = 'default_tenant'; // Default if omitted

    const type = document.getElementById('db-type-select').value;
    let uri = '';
    
    if (type === 'sqlite') {
        const path = document.getElementById('sqlite-path').value.trim();
        if (!path) return alert('File path required (Please upload a file or enter a path)');
        if (path.startsWith('sqlite:///')) {
            uri = path;
        } else {
            uri = `sqlite:///${path}`;
        }
    } else if (type === 'postgresql' || type === 'mysql') {
        const host = document.getElementById('std-host').value.trim();
        const port = document.getElementById('std-port').value.trim();
        const user = document.getElementById('std-user').value.trim();
        const pass = document.getElementById('std-pass').value.trim();
        const db = document.getElementById('std-dbname').value.trim();
        
        if (!host || !db || !user || !pass) return alert('Host, Username, Password, and Database are strictly required.');
        
        const portStr = port ? `:${port}` : (type === 'postgresql' ? ':5432' : ':3306');
        uri = `${type}://${user}:${pass}@${host}${portStr}/${db}`;
    } else if (type === 'snowflake') {
        let account = document.getElementById('sf-account').value.trim();
        // Auto-sanitize the account field in case they paste the full URL
        account = account.replace(/^https?:\/\//, '').replace(/\.snowflakecomputing\.com.*$/, '').replace(/\/$/, '');
        
        const user = document.getElementById('sf-user').value.trim();
        const pass = document.getElementById('sf-pass').value.trim();
        const db = document.getElementById('sf-dbname').value.trim();
        const schema = document.getElementById('sf-schema').value.trim();
        const wh = document.getElementById('sf-warehouse').value.trim();
        
        if (!account || !db || !wh || !user || !pass) return alert('Account, Username, Password, DB, and Warehouse are strictly required.');
        
        const schemaStr = schema ? `/${schema}` : '';
        uri = `snowflake://${user}:${pass}@${account}/${db}${schemaStr}?warehouse=${wh}`;
    }

    closeSettings();
    const id = showTypingIndicator("Connecting to database and extracting schema...");
    
    try {
        const res = await fetch('/connect', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ tenant_id: t, db_uri: uri })
        });
        const data = await res.json();
        removeElement(id);
        
        if (data.success) {
            currentTenant = t;
            currentDbUri = uri;
            currentDbType = type;
            localStorage.setItem('tenant_id', t);
            localStorage.setItem('db_uri', uri);
            localStorage.setItem('db_type', type);
            updateConnectionStatus();
            appendMessage('system', `Database (${type}) successfully connected! Schemas indexed into Qdrant. You can now query your data.`);
            fetchSchemaTree();
        } else {
            appendMessage('system', 'Failed to connect: ' + JSON.stringify(data));
        }
    } catch(err) {
        removeElement(id);
        appendMessage('system', 'Error connecting to database.');
    }
};

window.uploadSQLiteFile = async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    
    const formData = new FormData();
    formData.append("file", file);
    
    const statusText = document.getElementById('upload-status');
    statusText.style.display = 'block';
    statusText.innerText = 'Uploading...';
    
    try {
        const res = await fetch('/upload_db', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        if (data.success) {
            document.getElementById('sqlite-path-group').style.display = 'block';
            document.getElementById('sqlite-path').value = data.db_uri;
            statusText.innerText = 'Upload Successful! You can now click Save.';
            statusText.style.color = '#22c55e';
        } else {
            statusText.innerText = 'Upload failed: ' + data.detail;
            statusText.style.color = 'var(--error)';
        }
    } catch (err) {
        statusText.innerText = 'Upload Error: ' + err.message;
        statusText.style.color = 'var(--error)';
    }
};

// --- Theme Toggling ---
function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
}

const savedTheme = localStorage.getItem('theme');
if (savedTheme) {
    document.documentElement.setAttribute('data-theme', savedTheme);
}

// --- Chat Logic ---
const appendMessage = (sender, text, meta = null) => {
    const msgDiv = document.createElement('div');
    msgDiv.classList.add('message', sender === 'user' ? 'user-msg' : 'system-msg');

    const avatar = document.createElement('div');
    avatar.classList.add('avatar');
    avatar.innerText = sender === 'user' ? 'U' : 'N';

    const bubble = document.createElement('div');
    bubble.classList.add('bubble');
    
    const paragraphs = text.split('\n').filter(p => p.trim() !== '');
    paragraphs.forEach(pText => {
        const p = document.createElement('p');
        p.innerText = pText;
        bubble.appendChild(p);
    });

    if (sender === 'system' && meta) {
        const metaBox = document.createElement('div');
        metaBox.classList.add('metadata-box');
        let metaHtml = '';
        if (meta.cached) metaHtml += `<strong>[CACHE HIT]</strong> Result served from semantic cache.<br/>`;
        if (meta.error_traces && meta.error_traces.length > 0) {
            metaHtml += `<strong>Self-Healing Triggered (${meta.error_traces.length} retries):</strong><br/>`;
            meta.error_traces.forEach((err, idx) => {
                metaHtml += `<span class="error-trace">Attempt ${idx + 1} Failed: ${err}</span>`;
            });
        }
        if (metaHtml !== '') {
             metaBox.innerHTML = metaHtml;
             bubble.appendChild(metaBox);
        }
        
        if (meta.requires_approval) {
            const approvalBox = document.createElement('div');
            approvalBox.style.marginTop = '15px';
            approvalBox.style.display = 'flex';
            approvalBox.style.gap = '10px';
            
            const btnApprove = document.createElement('button');
            btnApprove.innerText = 'Approve';
            btnApprove.style.cssText = 'background: #22c55e; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer;';
            
            const btnReject = document.createElement('button');
            btnReject.innerText = 'Reject';
            btnReject.style.cssText = 'background: #ef4444; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer;';
            
            btnReject.onclick = () => {
                approvalBox.innerHTML = '<span style="color: #ef4444;">Query aborted by user.</span>';
            };
            
            btnApprove.onclick = async () => {
                btnApprove.disabled = true;
                btnReject.disabled = true;
                btnApprove.innerText = 'Executing...';
                try {
                    const res = await fetch('/execute_approved', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            sql: meta.sql_query,
                            tenant_id: currentTenant,
                            db_uri: currentDbUri
                        })
                    });
                    const data = await res.json();
                    if (data.success) {
                        approvalBox.innerHTML = '<span style="color: #22c55e;">Query executed successfully!</span>';
                        renderTable(data.result);
                    } else {
                        approvalBox.innerHTML = `<span style="color: #ef4444;">Error: ${data.error}</span>`;
                    }
                } catch(err) {
                    approvalBox.innerHTML = `<span style="color: #ef4444;">Request Error: ${err.message}</span>`;
                }
            };
            
            approvalBox.appendChild(btnApprove);
            approvalBox.appendChild(btnReject);
            bubble.appendChild(approvalBox);
        }
    }

    msgDiv.appendChild(avatar);
    msgDiv.appendChild(bubble);
    
    const activeChat = getActiveChat();
    activeChat.appendChild(msgDiv);
    
    const container = document.getElementById('chat-container');
    container.scrollTop = container.scrollHeight;
};

const showTypingIndicator = (msg = "Nexus is analyzing...") => {
    const id = 'typing-' + Date.now();
    const msgDiv = document.createElement('div');
    msgDiv.id = id;
    msgDiv.classList.add('message', 'system-msg', 'typing-indicator');
    msgDiv.innerText = msg;
    
    const activeChat = getActiveChat();
    activeChat.appendChild(msgDiv);
    
    const container = document.getElementById('chat-container');
    container.scrollTop = container.scrollHeight;
    return id;
};

const removeElement = (id) => {
    const el = document.getElementById(id);
    if (el) el.remove();
};

document.getElementById('chat-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const inputField = document.getElementById('user-input');
    const query = inputField.value.trim();
    if (!query) return;

    if (!currentDbUri || !currentTenant) {
        return alert("Please connect a database first.");
    }

    appendMessage('user', query);
    inputField.value = '';

    const id = showTypingIndicator();

    try {
        const res = await fetch('/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                query: query,
                tenant_id: currentTenant,
                db_uri: currentDbUri
            })
        });
        
        removeElement(id);
        const data = await res.json();
        
        if (res.status === 200) {
            appendMessage('system', data.simple_answer, data);
            const activeCode = getActiveCode();
            if (activeCode) {
                activeCode.innerText = data.sql_query;
                if (typeof hljs !== 'undefined') {
                    try {
                        hljs.highlightElement(activeCode);
                    } catch(e) {
                        console.log("Highlighting error (ignored):", e);
                    }
                }
            }
            renderTable(data.execution_result);
        } else {
            appendMessage('system', 'Error: ' + JSON.stringify(data));
        }
    } catch(err) {
        removeElement(id);
        appendMessage('system', 'System Error: ' + err.message);
    }
});

const renderTable = (rows) => {
    const activeTHead = getActiveTHead();
    const activeTBody = getActiveTBody();
    if (!activeTHead || !activeTBody) return;
    
    activeTHead.innerHTML = '';
    activeTBody.innerHTML = '';
    
    if (!rows || rows.length === 0) {
        document.getElementById('row-count').innerText = '(0 rows)';
        return;
    }

    document.getElementById('row-count').innerText = `(${rows.length} rows)`;

    // headers
    const headers = Object.keys(rows[0]);
    const trHead = document.createElement('tr');
    headers.forEach(h => {
        const th = document.createElement('th');
        th.innerText = h;
        trHead.appendChild(th);
    });
    activeTHead.appendChild(trHead);

    // rows
    rows.forEach(r => {
        const tr = document.createElement('tr');
        headers.forEach(h => {
            const td = document.createElement('td');
            td.innerText = r[h] !== null ? r[h] : 'NULL';
            tr.appendChild(td);
        });
        activeTBody.appendChild(tr);
    });
    
    // --- Data Visualization (Chart.js) Logic ---
    const canvas = document.getElementById(`chart-${activeSessionId}`);
    if (!canvas) return;
    
    // Destroy previous chart instance if it exists
    if (window[`myChart_${activeSessionId}`]) {
        window[`myChart_${activeSessionId}`].destroy();
        window[`myChart_${activeSessionId}`] = null;
    }
    
    canvas.style.display = 'none'; // hide by default
    
    // Auto-chart logic: exactly 2 columns, one is numeric
    if (headers.length === 2 && rows.length > 0) {
        let labelCol = null;
        let dataCol = null;
        
        // Find which column is numeric
        if (typeof rows[0][headers[0]] === 'number' && typeof rows[0][headers[1]] !== 'number') {
            dataCol = headers[0];
            labelCol = headers[1];
        } else if (typeof rows[0][headers[1]] === 'number' && typeof rows[0][headers[0]] !== 'number') {
            dataCol = headers[1];
            labelCol = headers[0];
        } else if (typeof rows[0][headers[0]] === 'number' && typeof rows[0][headers[1]] === 'number') {
            // Both numeric, just pick the first as label
            labelCol = headers[0];
            dataCol = headers[1];
        }
        
        if (labelCol && dataCol) {
            canvas.style.display = 'block';
            
            const labels = rows.map(r => r[labelCol]);
            const data = rows.map(r => r[dataCol]);
            
            // Set up chart with Cursor-like dark theme colors
            const ctx = canvas.getContext('2d');
            window[`myChart_${activeSessionId}`] = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{
                        label: dataCol,
                        data: data,
                        backgroundColor: 'rgba(99, 102, 241, 0.7)',
                        borderColor: 'rgba(99, 102, 241, 1)',
                        borderWidth: 1,
                        borderRadius: 4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { labels: { color: '#a1a1aa' } }
                    },
                    scales: {
                        x: { ticks: { color: '#a1a1aa' }, grid: { color: 'rgba(255,255,255,0.05)' } },
                        y: { ticks: { color: '#a1a1aa' }, grid: { color: 'rgba(255,255,255,0.05)' } }
                    }
                }
            });
        }
    }
};

// --- Schema Explorer Tree ---
async function fetchSchemaTree() {
    const treeRoot = document.getElementById('schema-tree');
    if (!currentDbUri) return;
    
    treeRoot.innerHTML = '<li style="padding: 15px; color: var(--text-muted); text-align: center;">Loading schema...</li>';
    
    try {
        const res = await fetch('/schema', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ tenant_id: currentTenant, db_uri: currentDbUri })
        });
        const data = await res.json();
        renderSchemaTree(data.tables || data);
    } catch(err) {
        treeRoot.innerHTML = '<li style="padding: 15px; color: var(--error); text-align: center;">Failed to load schema</li>';
    }
}

function renderSchemaTree(schemaObj) {
    const treeRoot = document.getElementById('schema-tree');
    treeRoot.innerHTML = '';
    
    if (Array.isArray(schemaObj)) {
        if (schemaObj.length === 0) {
            treeRoot.innerHTML = '<li style="padding: 15px; color: var(--text-muted); text-align: center;">No tables found.</li>';
            return;
        }
        
        schemaObj.forEach(table => {
            const li = document.createElement('li');
            
            const nodeDiv = document.createElement('div');
            nodeDiv.className = 'tree-node';
            nodeDiv.innerHTML = `<span class="tree-node-icon">📁</span> <span>${table.name}</span>`;
            
            const ul = document.createElement('ul');
            ul.className = 'tree-nested';
            
            if (table.columns) {
                table.columns.forEach(col => {
                    const colLi = document.createElement('li');
                    colLi.className = 'tree-col-node';
                    colLi.innerHTML = `<span>${col.name}</span> <span class="tree-col-type">${col.type}</span>`;
                    ul.appendChild(colLi);
                });
            }
            
            nodeDiv.onclick = () => {
                ul.classList.toggle('tree-active');
                const icon = nodeDiv.querySelector('.tree-node-icon');
                icon.innerText = ul.classList.contains('tree-active') ? '📂' : '📁';
            };
            
            li.appendChild(nodeDiv);
            li.appendChild(ul);
            treeRoot.appendChild(li);
        });
        return;
    }
    
    if (!schemaObj || Object.keys(schemaObj).length === 0) {
         treeRoot.innerHTML = '<li style="padding: 15px; color: var(--text-muted); text-align: center;">No tables found.</li>';
         return;
    }
    
    Object.keys(schemaObj).forEach(tableName => {
        const columns = schemaObj[tableName];
        
        const tableLi = document.createElement('li');
        tableLi.className = 'tree-item';
        
        const tableHeader = document.createElement('div');
        tableHeader.className = 'tree-header';
        tableHeader.innerHTML = `
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="3" y1="9" x2="21" y2="9"></line><line x1="9" y1="21" x2="9" y2="9"></line></svg>
            ${tableName}
        `;
        
        const colsUl = document.createElement('ul');
        colsUl.className = 'tree-children';
        colsUl.style.display = 'none';
        
        if (Array.isArray(columns)) {
            columns.forEach(col => {
                const colLi = document.createElement('li');
                colLi.className = 'tree-item tree-column';
                colLi.innerHTML = `
                    <div class="col-name">${col.name}</div>
                    <div class="col-type">${col.type}</div>
                `;
                colsUl.appendChild(colLi);
            });
        }
        
        tableHeader.onclick = () => {
            tableHeader.classList.toggle('open');
            colsUl.style.display = colsUl.style.display === 'none' ? 'block' : 'none';
        };
        
        tableLi.appendChild(tableHeader);
        tableLi.appendChild(colsUl);
        treeRoot.appendChild(tableLi);
    });
}

// Initial hydration
updateConnectionStatus();
toggleDbFields();
if (currentDbUri) {
    fetchSchemaTree();
}

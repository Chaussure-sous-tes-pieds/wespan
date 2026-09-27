// WE Span helper (KWin script)
//  1. garde la fenêtre cachée de Wallpaper Engine à l'endroit demandé par le service (hors écran)
//  2. calcule, pour chaque écran, ce que recouvrent les fenêtres (maximisées, plein écran, %)
//     et l'envoie au service, qui décide de mettre le fond en pause (image figée).

const SERVICE = "org.wespan.Daemon", PATH = "/Daemon", IFACE = "org.wespan.Daemon";
const GRID_X = 48, GRID_Y = 27;          // points d'échantillonnage par écran

let target = null;                        // {title, x, y, w, h}
const canvases = new Set();               // fenêtres de Wallpaper Engine (2 pendant un changement de fond)
let lastReport = "";
const hooked = new Set();

// --- minuteries et signaux ---------------------------------------------------------------

const reportTimer = new QTimer();
reportTimer.singleShot = true;
reportTimer.interval = 150;
reportTimer.timeout.connect(function () { report(false); });

const placeTimer = new QTimer();
placeTimer.singleShot = true;
placeTimer.interval = 300;
placeTimer.timeout.connect(function () { placeCanvas(); });

// battement : le service peut redémarrer, la cible changer, la fenêtre réapparaître
const heartbeat = new QTimer();
heartbeat.interval = 5000;
heartbeat.timeout.connect(function () {
    fetchTarget();
    report(true);
    for (const c of canvases) reportCanvas(c);
});
heartbeat.start();


function call(method, args, cb) {
    const a = [SERVICE, PATH, IFACE, method].concat(args || []);
    if (cb) a.push(cb);
    callDBus.apply(null, a);
}

function fetchTarget() {
    call("WindowTarget", [], function (json) {
        try { target = JSON.parse(json); } catch (e) { target = null; }
        findCanvas();
    });
}

function isCanvas(w) {
    return target && w && !w.deleted && typeof w.caption === "string" && w.caption.indexOf(target.title) === 0;
}

function reportCanvas(w) {
    call("ReportWindow", [String(w.internalId).replace(/[{}]/g, ""), w.pid, w.caption]);
}

function place(w) {
    if (!target || !w || w.deleted) return;
    const g = w.frameGeometry;
    if (g.x !== target.x || g.y !== target.y || g.width !== target.w || g.height !== target.h)
        w.frameGeometry = { x: target.x, y: target.y, width: target.w, height: target.h };
}

function placeCanvas() {
    for (const c of canvases) place(c);
}

function adoptCanvas(w) {
    if (canvases.has(w)) return;
    canvases.add(w);
    place(w);
    w.frameGeometryChanged.connect(function () { if (canvases.has(w)) placeTimer.start(); });
    reportCanvas(w);
}

function findCanvas() {
    if (!target) return;
    for (const c of Array.from(canvases)) if (c.deleted || !isCanvas(c)) canvases.delete(c);
    for (const w of workspace.windowList()) if (isCanvas(w)) adoptCanvas(w);
    placeCanvas();
}

// --- occultation -------------------------------------------------------------------------

function onCurrentDesktop(w, output) {
    if (w.onAllDesktops) return true;
    let cur = workspace.currentDesktop;
    if (typeof workspace.currentDesktopForScreen === "function") {
        try { cur = workspace.currentDesktopForScreen(output) || cur; } catch (e) { }
    }
    for (const d of w.desktops) if (d === cur || (d.id && cur && d.id === cur.id)) return true;
    return false;
}

function inCurrentActivity(w) {
    const acts = w.activities;
    return !acts || acts.length === 0 || acts.indexOf(workspace.currentActivity) !== -1;
}

function counts(w) {
    return w && !w.deleted && !isCanvas(w) && !w.minimized && !w.hidden &&
        (w.normalWindow || w.dialog) && !w.desktopWindow && !w.dock;
}

function compute() {
    const screens = [];
    const wins = workspace.windowList().filter(counts);
    for (const o of workspace.screens) {
        const g = o.geometry;
        const vis = wins.filter(w => onCurrentDesktop(w, o) && inCurrentActivity(w));
        let maximized = false, fullscreen = false;
        const rects = [];
        for (const w of vis) {
            const f = w.frameGeometry;
            if (f.x >= g.x + g.width || f.y >= g.y + g.height || f.x + f.width <= g.x || f.y + f.height <= g.y) continue;
            rects.push(f);
            const onThis = w.output && w.output.name === o.name;
            if (onThis && w.fullScreen) fullscreen = true;
            if (onThis && w.maximizeMode === 3) maximized = true;
        }
        let covered = 0;
        for (let iy = 0; iy < GRID_Y; iy++) {
            const y = g.y + (iy + 0.5) * g.height / GRID_Y;
            for (let ix = 0; ix < GRID_X; ix++) {
                const x = g.x + (ix + 0.5) * g.width / GRID_X;
                for (const f of rects) {
                    if (x >= f.x && x < f.x + f.width && y >= f.y && y < f.y + f.height) { covered++; break; }
                }
            }
        }
        screens.push({
            name: o.name, x: g.x, y: g.y, w: g.width, h: g.height,
            cover: Math.round(covered * 1000 / (GRID_X * GRID_Y)) / 10,
            maximized: maximized, fullscreen: fullscreen
        });
    }
    return screens;
}

function report(force) {
    const json = JSON.stringify(compute());
    if (!force && json === lastReport) return;
    lastReport = json;
    call("ReportScreens", [json]);
}

function schedule() { reportTimer.start(); }

function hook(w) {
    if (hooked.has(w)) return;
    hooked.add(w);
    const sigs = ["frameGeometryChanged", "minimizedChanged", "fullScreenChanged", "maximizedChanged",
                  "desktopsChanged", "activitiesChanged", "outputChanged", "hiddenChanged"];
    for (const s of sigs) if (w[s]) w[s].connect(schedule);
    if (w.captionChanged) w.captionChanged.connect(function () { if (isCanvas(w)) adoptCanvas(w); });
    if (isCanvas(w)) adoptCanvas(w);
}

workspace.windowAdded.connect(function (w) { hook(w); schedule(); });
workspace.windowRemoved.connect(function (w) {
    hooked.delete(w);
    canvases.delete(w);
    schedule();
});
workspace.currentDesktopChanged.connect(schedule);
workspace.currentActivityChanged.connect(schedule);
workspace.screensChanged.connect(function () { schedule(); placeTimer.start(); });

for (const w of workspace.windowList()) hook(w);
fetchTarget();
schedule();

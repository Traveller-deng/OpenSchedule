/*__BAKED_BLOCK__*/
/*__DDL_BLOCK__*/
/*__TASKS_BLOCK__*/
/*__LINKS_BLOCK__*/

/* =====================================================================
   本地增补（localStorage）
   ===================================================================== */
const LS_KEY = "openSchedule.v5";
const LS_LEGACY = "everydaySchedule.v5";
/* 改名前存在浏览器里的数据迁移过来，避免本地改动看起来"丢了" */
try{
  if(!localStorage.getItem(LS_KEY) && localStorage.getItem(LS_LEGACY))
    localStorage.setItem(LS_KEY, localStorage.getItem(LS_LEGACY));
  if(!localStorage.getItem(LS_KEY + "_ui") && localStorage.getItem(LS_LEGACY + "_ui"))
    localStorage.setItem(LS_KEY + "_ui", localStorage.getItem(LS_LEGACY + "_ui"));
}catch(e){}
/* 本地服务地址存在时（http），DDL 直接从 data/todo.md 读，见 serve.py */
const BUILT = (typeof BUILT_AT === "undefined") ? "" : BUILT_AT;
/* 构建时注入的前端代码指纹：跟服务端对不上 = 浏览器里跑的是旧代码 → 自动刷新 */
const BUILD = (typeof BUILD_ID === "undefined") ? "" : BUILD_ID;
const emptyEdits = ()=>({adds:{}, ovr:{}, hides:{}, sections:{}, ddlDone:{}, tasksDone:{}, planDone:{},
                          ddl:{ovr:{}, add:[], del:[]}, links:{ovr:{}, add:[], del:[]},
                          plan:{ovr:{}, add:[], del:[]}});
let edits = emptyEdits();
try{ edits = Object.assign(edits, JSON.parse(localStorage.getItem(LS_KEY)) || {}); }catch(e){ edits = emptyEdits(); }
if(!edits.ddl) edits.ddl = {ovr:{}, add:[], del:[]};
if(!edits.links) edits.links = {ovr:{}, add:[], del:[]};
if(!edits.plan) edits.plan = {ovr:{}, add:[], del:[]};
let editsSyncOn = syncEligible(), editsSuppress = false, lastEditsMtime = null;
function saveEdits(){
  localStorage.setItem(LS_KEY, JSON.stringify(edits));
  if(editsSyncOn && !editsSuppress)          /* 回写服务端，agent/CLI 才能看到页面上的改动 */
    fetch("/api/edits", {method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify(edits)})
      .then(r=>r.ok ? r.json() : null)
      .then(s=>{ if(s && s.mtime) lastEditsMtime = s.mtime; })
      .catch(()=>{});
}
let ui = {lc:false, rc:true, tab:"ddl", lw:292, rw:344, draftH:210, draft:"", chatH:250};
try{ Object.assign(ui, JSON.parse(localStorage.getItem(LS_KEY+"_ui")||"{}")); }catch(e){}

const TYPE = {
  study:{c:"k-study", label:"学习", v:"var(--study)"},
  life:{c:"k-life", label:"生活", v:"var(--life)"},
  research:{c:"k-research", label:"科研", v:"var(--research)"},
  rest:{c:"k-rest", label:"缓冲", v:"var(--rest)"}
};
/* 老数据里的 8 种类型统一映射到 4 种，不改动 data/ 里的原始值 */
const TYPE_ALIAS = {class:"study", must:"study", gold:"research", push:"research",
                    meet:"research", red:"research", life:"life", rest:"rest"};
function typeKey(t){ const k = TYPE_ALIAS[t] || t; return TYPE[k] ? k : "rest"; }
function typeMeta(t){ return TYPE[typeKey(t)]; }
const WEEK = ["周日","周一","周二","周三","周四","周五","周六"];
const pad = n => String(n).padStart(2,"0");
const key = d => d.getFullYear()+"-"+pad(d.getMonth()+1)+"-"+pad(d.getDate());
const parseKey = k => { const p=k.split("-").map(Number); return new Date(p[0],p[1]-1,p[2]); };
const esc = s => String(s==null?"":s).replace(/[&<>"]/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

const TODAY = new Date();
let sel = key(TODAY);
let view = new Date(TODAY.getFullYear(), TODAY.getMonth(), 1);
let modalMode = "add", modalAnchor = "__head__", modalId = null;
let secMode = null;

/* ---------------- time ---------------- */
function toMin(t){
  if(!t) return null;
  const m = /^\s*(\d{1,2})\s*[:：]\s*(\d{1,2})\s*$/.exec(String(t));
  return m ? (+m[1])*60 + (+m[2]) : null;
}
function durMin(d){
  if(!d) return 0;
  const s = String(d).replace(/\s/g,"").toLowerCase();
  let m;
  if((m = s.match(/^(\d+)h(\d+)$/))) return (+m[1])*60 + (+m[2]);
  if((m = s.match(/^(\d+(?:\.\d+)?)h$/))) return Math.round(parseFloat(m[1])*60);
  if((m = s.match(/^(\d+)h(\d+)min$/))) return (+m[1])*60 + (+m[2]);
  if((m = s.match(/^(\d+)min$/))) return (+m[1]);
  if((m = s.match(/^(\d+)m$/))) return (+m[1]);
  if((m = s.match(/^(\d+(?:\.\d+)?)$/))) return Math.round(parseFloat(m[1])*60);
  return 0;
}

/* ---------------- data ---------------- */
function bakedItems(k){
  const plan = BAKED[k];
  return ((plan && plan.items) || []).map((it,i)=>Object.assign({}, it, {id:"b"+i, src:"baked"}));
}
function norm(it){
  const c = Object.assign({}, it);
  if(!c.links) c.links = c.link ? [{url:c.link, label:c.linkLabel||"资料", kind:"资料"}] : [];
  return c;
}
function withOvr(k, it){
  const o = (edits.ovr[k]||{})[it.id];
  if(!o) return norm(it);
  const c = Object.assign({}, it);
  ["t","d","title","type","detail","out"].forEach(f=>{ if(o[f]!==undefined) c[f]=o[f]; });
  if(o.list!==undefined) c.list = o.list;
  if(o.links!==undefined) c.links = o.links;
  c.edited = true;
  return norm(c);
}
function buildList(k){
  const hides = new Set(edits.hides[k]||[]);
  let list = bakedItems(k).filter(x=>!hides.has(x.id)).map(x=>withOvr(k,x));
  const adds = (edits.adds[k]||[]).map(x=>norm(Object.assign({}, x, {src:"user"})));
  adds.forEach(a=>{
    if(!a.after || a.after==="__tail__"){ list.push(a); return; }
    const i = list.findIndex(x=>x.id===a.after);
    if(i>=0) list.splice(i+1,0,a); else list.push(a);
  });
  list.sort(byStart);   /* 按开始时间自动排序；同一时刻保持原有先后 */
  return list;
}
/* 排序：时间早的在前；没有时间的排最后。sort 稳定，同刻按原顺序。 */
function byStart(a,b){
  const sa=toMin(a.t), sb=toMin(b.t);
  if(sa===sb) return 0;
  if(sa===null) return 1;
  if(sb===null) return -1;
  return sa-sb;
}
function daySections(k){
  const plan = BAKED[k] || {};
  const ovr = (edits.sections[k]||{});
  const tasks = ovr.tasks !== undefined ? ovr.tasks : (plan.tasks||[]);
  return {tasks:tasks, edited: ovr.tasks!==undefined};
}
function taskText(t){ return typeof t==="string" ? t : (t.t||""); }
function taskDone(k, txt){ const m = (edits.tasksDone||{})[k]; return !!(m && m[txt]); }
function toggleTask(k, txt){
  if(!edits.tasksDone) edits.tasksDone = {};
  const m = edits.tasksDone[k] || (edits.tasksDone[k] = {});
  if(m[txt]) delete m[txt]; else m[txt] = true;
  saveEdits(); render();
}

/* ---------------- 任务文字 → 资料自动匹配 ----------------
   拿 links.json 的 paths（文件名、显示名、别名）去任务文字里找，
   找到对应文件的，就自动挂一个可点的资料链接。 */
const PATH_LIST = (function(){
  const P = (typeof PATHS === "undefined") ? {} : (PATHS || {});
  const out = [];
  Object.keys(P).forEach(k=>{
    const p = P[k] || {};
    const segs = String(p.path||"").split(/[\\/]+/).filter(Boolean);
    const toks = new Set();
    (p.aliases||[]).forEach(a=>{ const s=String(a||"").trim(); if(s.length>=2) toks.add(s); });
    /* 有别名就以别名为准（别名是人工挑过的关键词），避免显示名切出来的碎片误命中 */
    if(!toks.size){
      [p.label, p.short].forEach(s=>String(s||"").split(/[\s　]+/).forEach(w=>{ if(w && w.length>=2) toks.add(w); }));
    }
    segs.forEach(s=>{ const b=s.replace(/\.[A-Za-z0-9]{1,6}$/,""); if(b.length>=2) toks.add(b); });
    out.push({key:k, path:p.path||"", label:p.short||p.label||k, kind:p.kind||"资料", toks:Array.from(toks)});
  });
  return out;
})();
function matchTaskPaths(txt){
  const t = String(txt||"").toLowerCase();
  if(!t) return [];
  const hits = [];
  PATH_LIST.forEach(p=>{
    let best = 0;
    p.toks.forEach(tok=>{
      const s = String(tok).toLowerCase();
      if(s.length < 2) return;
      if(t.indexOf(s) >= 0 && s.length > best) best = s.length;
    });
    if(best > 0) hits.push({p:p, score:best});
  });
  hits.sort((a,b)=> b.score - a.score || a.p.key.localeCompare(b.p.key));
  return hits.slice(0,4).map(x=>x.p);
}
function sameTarget(a, b){
  const x = String((a && (a.path||a.url)) || "").toLowerCase().replace(/[\\/]+$/,"");
  const y = String((b && (b.path||b.url)) || "").toLowerCase().replace(/[\\/]+$/,"");
  return !!x && x === y;
}
function lnkHtml(l){
  const bd = fileBadge(l);
  return '<a class="lnk" href="'+esc(linkHref(l))+'" target="_blank" rel="noopener">'+
    (bd? '<i class="lkb">'+esc(bd)+'</i>':'')+
    '<span>'+esc(l.label||decodeURIComponent(String(l.url||"").split("/").pop()||"打开"))+'</span></a>';
}
function ddlKey(d){ return (d.date||"")+"::"+(d.task||""); }
/* 未完成且有日期的 DDL 落在哪几天（新增/删除也会实时反映） */
function ddlDates(){
  const s = new Set();
  ddlList().forEach(d=>{ if(d.date && !d.done) s.add(d.date); });
  return s;
}
function dayHas(k){
  if(buildList(k).length > 0) return true;
  const sec = daySections(k);
  return !!(sec.tasks && sec.tasks.length);
}
function conflicts(list){
  const info = {};
  list.forEach(it=>{
    const s = toMin(it.t), d = durMin(it.d);
    if(s==null || d<=0) return;
    info[it.id] = {s:s, e:s+d, with:[]};
  });
  const ids = Object.keys(info);
  ids.forEach(a=>ids.forEach(b=>{
    if(a===b) return;
    const A=info[a], B=info[b];
    if(A.s < B.e && B.s < A.e) A.with.push({id:b, t:(list.find(x=>x.id===b)||{}).t});
  }));
  return info;
}

/* ---------------- calendar ---------------- */
function renderCal(){
  document.getElementById("calTitle").textContent = view.getFullYear()+" 年 "+(view.getMonth()+1)+" 月";
  const tb = document.getElementById("calBody");
  tb.innerHTML = "";
  const first = new Date(view.getFullYear(), view.getMonth(), 1);
  const start = new Date(first); start.setDate(1 - first.getDay());
  const lastDay = new Date(view.getFullYear(), view.getMonth()+1, 0).getDate();
  const cells = Math.ceil((first.getDay() + lastDay) / 7) * 7;
  const tk = key(TODAY), dd = ddlDates();
  for(let i=0;i<cells;i++){
    const d = new Date(start); d.setDate(start.getDate()+i);
    if(i % 7 === 0) tb.appendChild(document.createElement("tr"));
    const td = document.createElement("td");
    const k = key(d);
    const b = document.createElement("button");
    b.className = "dcell";
    if(d.getMonth()!==view.getMonth()) b.classList.add("out");
    if(k===tk) b.classList.add("today");
    if(k===sel) b.classList.add("sel");
    if(dayHas(k)) b.classList.add("has");
    if(dd.has(k)) b.classList.add("dl");
    b.textContent = d.getDate();
    b.title = k + " " + WEEK[d.getDay()] + (dd.has(k)?" · 有 DDL":"");
    b.onclick = ()=>{ sel = k; view = new Date(d.getFullYear(), d.getMonth(), 1); render(); };
    td.appendChild(b); tb.lastChild.appendChild(td);
  }
}

/* ---------------- 竖排日号（收起态）· 歌词式 ----------------
   一列只有数字：滚轮/拖动滑动，中间那一行最清晰（选中日），向两端渐隐。
   滚动停下后自动吸附到最近的一天，并同步中间的时间表。 */
const STRIP_DAYS = 60;
function renderStrip(){
  const base = new Date(TODAY.getFullYear(), TODAY.getMonth(), TODAY.getDate());
  const start = new Date(base); start.setDate(base.getDate()-STRIP_DAYS);
  const dd = ddlDates(), tk = key(TODAY);
  let h = "";
  for(let i=0; i<=STRIP_DAYS*2; i++){
    const d = new Date(start); d.setDate(start.getDate()+i);
    const k = key(d);
    h += '<button class="sitem'+(k===tk?" today":"")+(dayHas(k)?" has":"")+(dd.has(k)?" due":"")+
         '" data-d="'+k+'" title="'+k+' '+WEEK[d.getDay()]+'">'+
         '<span class="dnum">'+d.getDate()+'</span>'+
         '<span class="dwk">'+WEEK[d.getDay()].replace("周","")+'</span></button>';
  }
  const list = document.getElementById("slist");
  list.innerHTML = h;
  list.querySelectorAll(".sitem").forEach(b=>b.onclick = ()=>setSel(b.dataset.d, true));
  sizeStrip();
  paintStrip();
  requestAnimationFrame(()=>{ sizeStrip(); centerOn(sel, false); fadeStrip(); });
}
function sizeStrip(){
  const list = document.getElementById("slist");
  if(!list) return;
  const item = list.querySelector(".sitem");
  const half = list.clientHeight/2 - (item ? item.offsetHeight/2 : 28);
  list.style.paddingTop = list.style.paddingBottom = Math.max(0, Math.round(half)) + "px";
}
function paintStrip(){
  const list = document.getElementById("slist");
  if(!list) return;
  const tk = key(TODAY);
  list.querySelectorAll(".sitem").forEach(b=>{
    b.classList.toggle("sel", b.dataset.d === sel);
    b.classList.toggle("today", b.dataset.d === tk);
  });
  const lab = document.getElementById("smonth");
  if(lab) lab.textContent = (parseKey(sel).getMonth()+1)+" 月";
  fadeStrip();
  placeBar();
}
/* 竖条纵向跟着选中的那天走（取布局位置，不受缩放影响） */
function placeBar(){
  const list = document.getElementById("slist"), strip = document.getElementById("strip");
  if(!list || !strip || !list.clientHeight) return;
  const el = list.querySelector(".sitem.sel");
  if(!el) return;
  /* 对齐「日期数字」本身：用可见矩形算，绕开 transform 造成的 offsetParent 差异 */
  const num = el.querySelector(".dnum") || el;
  const lr = list.getBoundingClientRect(), nr = num.getBoundingClientRect();
  const y = list.offsetTop + (nr.top + nr.height / 2 - lr.top);
  strip.style.setProperty("--bar-y", y.toFixed(1) + "px");
  /* 收起态：让箭头与这条竖线、这个日期三者同高 */
  const box = document.getElementById("left").getBoundingClientRect();
  document.getElementById("left").style.setProperty("--handle-y", (nr.top + nr.height / 2 - box.top).toFixed(1) + "px");
}
/* 按离中线的距离算清晰度：中间 1，两端 0 */
function fadeStrip(){
  const list = document.getElementById("slist");
  if(!list || !list.clientHeight) return;
  const lr = list.getBoundingClientRect();
  const mid = lr.top + lr.height/2, span = lr.height/2 || 1;
  let near = null, nd = Infinity;
  list.querySelectorAll(".sitem").forEach(b=>{
    const r = b.getBoundingClientRect();
    const dist = Math.abs(r.top + r.height/2 - mid);
    b.style.setProperty("--f", (1 - Math.min(1, dist/span)).toFixed(3));
    if(dist < nd){ nd = dist; near = b; }
  });
  /* 月份标签跟着滚动实时更新：跨月时不会只剩 31、1、2 */
  const lab = document.getElementById("smonth");
  if(lab && near){
    const txt = (parseKey(near.dataset.d).getMonth()+1)+" 月";
    if(lab.textContent !== txt) lab.textContent = txt;
  }
  placeBar();
}
function centerOn(k, smooth){
  const list = document.getElementById("slist");
  if(!list || !list.clientHeight) return;
  const el = list.querySelector('.sitem[data-d="'+k+'"]');
  if(!el) return;
  const top = el.offsetTop - (list.clientHeight - el.offsetHeight)/2;
  if(Math.abs(list.scrollTop - top) < 1.5) return;
  list.scrollTo({top: Math.max(0, top), behavior: smooth ? "smooth" : "auto"});
}
/* 选中某天：只重画中间/日历/右栏，不重建竖条（否则滚动会跳） */
function setSel(k, center){
  if(!k) return;
  sel = k;
  const d = parseKey(k);
  view = new Date(d.getFullYear(), d.getMonth(), 1);
  paintStrip();
  renderMain();
  renderCal();
  renderRight();
  if(center) centerOn(k, true);
}
/* 滚动期间每帧刷新渐隐；停手约 150ms 后吸附到最近的一天。
   吸附走定时器而不是只依赖 scroll 事件——滚轮/拖动时 scroll 事件可能很稀疏甚至丢帧。 */
let stripSettle = 0, stripFadeRAF = 0;
function kickStrip(){
  if(!ui.lc) return;
  if(!stripFadeRAF) stripFadeRAF = requestAnimationFrame(()=>{ stripFadeRAF = 0; fadeStrip(); });
  clearTimeout(stripSettle);
  stripSettle = setTimeout(settleStrip, 150);
}
function settleStrip(){
  const list = document.getElementById("slist");
  if(!list || !list.clientHeight) return;
  const lr = list.getBoundingClientRect(), mid = lr.top + lr.height/2;
  let best = null, bd = Infinity;
  list.querySelectorAll(".sitem").forEach(b=>{
    const r = b.getBoundingClientRect();
    const d = Math.abs(r.top + r.height/2 - mid);
    if(d < bd){ bd = d; best = b; }
  });
  if(!best) return;
  if(best.dataset.d !== sel) setSel(best.dataset.d, true);
  else centerOn(best.dataset.d, true);
}
["scroll","wheel","pointerdown","touchstart","mouseup"].forEach(ev=>
  document.getElementById("slist").addEventListener(ev, kickStrip, {passive:true}));
document.getElementById("slist").addEventListener("keydown", e=>{
  if(e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
  e.preventDefault();
  const d = parseKey(sel);
  d.setDate(d.getDate() + (e.key === "ArrowDown" ? 1 : -1));
  setSel(key(d), true);
});
window.addEventListener("resize", ()=>{ if(ui.lc){ sizeStrip(); fadeStrip(); } });

/* ---------------- 右栏：DDL 看板 / 任务安排 / 常用入口 ---------------- */
const TABS = [{id:"ddl", title:"DDL 看板"}, {id:"plan", title:"任务安排"}, {id:"links", title:"常用入口"}];

function ymOf(dateStr){
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(dateStr||""));
  if(!m) return String(dateStr||"");
  const y = +m[1], mo = +m[2], da = +m[3];
  return (y === TODAY.getFullYear()) ? (mo+"."+da) : (y+"."+mo+"."+da);
}
/* file:// 打开时用构建内的副本 + 本机改动；http:// 打开时以 data/todo.md 为准 */
function ddlList(){
  if(SYNC.ok && SYNC.items){
    const list = SYNC.items.map((d,i)=>({id:"s"+i, baseKey:ddlKey(d), key:ddlKey(d),
      date:d.date||"", task:d.task||"", done:!!d.done, ym:ymOf(d.date)}));
    list.sort((a,b)=> String(a.date||"9999").localeCompare(String(b.date||"9999")));
    return list;
  }
  const src = (edits.ddlLoaded && edits.ddlLoaded.items) ? edits.ddlLoaded.items : DDL;
  const ovr = edits.ddl.ovr || {}, del = new Set(edits.ddl.del || []), done = edits.ddlDone || {};
  const list = src.map((d,i)=>{
    const baseKey = ddlKey(d);
    const o = ovr[baseKey] || {};
    const date = o.date !== undefined ? o.date : (d.date||"");
    const task = o.task !== undefined ? o.task : (d.task||"");
    const k = date+"::"+task;
    return {id:"b"+i, baseKey:baseKey, key:k, date:date, task:task,
            done: done[k] !== undefined ? !!done[k] : !!d.done};
  }).filter(x=>!del.has(x.baseKey));
  (edits.ddl.add||[]).forEach(a=>{
    const k = ddlKey(a);
    list.push({id:a.id, baseKey:k, key:k, date:a.date||"", task:a.task||"",
               done: done[k] !== undefined ? !!done[k] : !!a.done, added:true});
  });
  list.forEach(x=>{ x.ym = ymOf(x.date); });
  list.sort((a,b)=> String(a.date||"9999").localeCompare(String(b.date||"9999")));
  return list;
}
function linksList(){
  const ovr = edits.links.ovr || {}, del = new Set(edits.links.del || []);
  const list = LINKS.map((l,i)=>{
    const id = "l"+i, o = ovr[id] || {};
    return {id:id,
      icon : o.icon  !== undefined ? o.icon  : (l.icon||"\u{1F517}"),
      label: o.label !== undefined ? o.label : (l.label||""),
      url  : o.url   !== undefined ? o.url   : (l.url||""),
      path : o.path  !== undefined ? o.path  : (l.path||""),
      mode : o.mode  !== undefined ? o.mode  : (l.mode||"app")};
  }).filter(l=>!del.has(l.id));
  return list.concat(edits.links.add || []);
}

function renderRight(){
  const tabs = document.getElementById("tabs");
  tabs.innerHTML = TABS.map(t=>'<button class="tab'+(t.id===ui.tab?" on":"")+'" data-tab="'+
    t.id+'">'+esc(t.title)+'</button>').join("");
  tabs.querySelectorAll("[data-tab]").forEach(el=>el.onclick = ()=>{
    ui.tab = el.dataset.tab; saveUI(); renderRight();
  });
  const head = document.getElementById("rhead"), body = document.getElementById("rbody");
  if(ui.tab === "links") renderLinks(head, body);
  else if(ui.tab === "plan") renderPlan(head, body);
  else renderDdl(head, body);
}

function renderDdl(head, body){
  const all = ddlList();
  const open = all.filter(x=>!x.done), done = all.filter(x=>x.done);
  head.innerHTML =
    '<h2>DDL 看板 <span class="cnt">'+open.length+' 待办</span></h2>'+
    '<button class="iconbtn" id="ddlAdd" title="新增一条">＋</button>'+

    (P_TODO_URL
      ? '<a class="iconbtn" href="'+esc(linkHref({url:P_TODO_URL, mode:"app"}))+'" target="_blank" rel="noopener" title="打开任务清单">📄</a>'
      : '');
  const row = (x, cls)=>
    '<div class="ddl '+cls+'" data-date="'+esc(x.date)+'" data-id="'+esc(x.id)+'" title="点击跳到该天安排">'+
      '<span class="box" data-toggle="'+esc(x.id)+'"></span>'+
      '<span class="txt"><span class="dt">'+esc(x.ym)+'</span><span class="tk">'+esc(x.task)+'</span></span>'+
      '<span class="acts"><button data-dedit="'+esc(x.id)+'" title="编辑">✎</button>'+
      '<button class="act-del" data-ddel="'+esc(x.id)+'" title="删除">×</button></span>'+
    '</div>';
  let h = '';
  open.forEach(x=>{ h += row(x, x.date===sel ? "cur" : ""); });
  if(!open.length) h += '<p class="rhint">没有待办 DDL 🎉</p>';
  if(done.length){
    h += '<p class="rhint" style="margin-top:14px">已完成</p>';
    done.forEach(x=>{ h += row(x, "done"); });
  }
  body.innerHTML = h;

  document.getElementById("ddlAdd").onclick = ()=>openDdlEditor(null);

  body.querySelectorAll("[data-toggle]").forEach(b=>b.onclick = e=>{
    e.stopPropagation();
    const it = ddlList().find(x=>x.id===b.dataset.toggle);
    if(!it) return;
    if(SYNC.ok){
      syncSave(ddlList().map(x=>({date:x.date, task:x.task, done: x.id===it.id ? !x.done : x.done})));
      return;
    }
    if(!edits.ddlDone) edits.ddlDone = {};
    edits.ddlDone[it.key] = !it.done;
    saveEdits(); render();
  });
  body.querySelectorAll("[data-dedit]").forEach(b=>b.onclick = e=>{
    e.stopPropagation();
    const it = ddlList().find(x=>x.id===b.dataset.dedit);
    if(it) openDdlEditor(it);
  });
  body.querySelectorAll("[data-ddel]").forEach(b=>b.onclick = e=>{
    e.stopPropagation();
    const it = ddlList().find(x=>x.id===b.dataset.ddel);
    if(it) delDdl(it);
  });
  body.querySelectorAll(".ddl").forEach(el=>{
    el.onclick = e=>{
      if(e.target.closest(".acts") || e.target.closest(".box")) return;
      const d = el.dataset.date;
      if(!d) return;
      setSel(d, true);
      document.getElementById("main").scrollIntoView({behavior:"smooth", block:"start"});
    };
  });
}

/* ---------------- 任务安排（tasks.md） ----------------
   没有明确 DDL、靠自己推进的事，和「DDL 看板」并列的一个模块。
   file:// 打开时用构建内的 TASKS + 本地覆盖层；http:// 打开时以 data/tasks.md 为准。 */
function planKey(t){ return (t.group||"")+"::"+(t.text||""); }
function planList(){
  if(SYNC.ok && SYNC.plan){
    return SYNC.plan.map((t,i)=>({id:"p"+i, baseKey:planKey(t), key:planKey(t),
      group:t.group||"", text:t.text||"", done:!!t.done}));
  }
  const ovr = edits.plan.ovr || {}, del = new Set(edits.plan.del || []), done = edits.planDone || {};
  const list = TASKS.map((t,i)=>{
    const baseKey = planKey(t);
    const o = ovr[baseKey] || {};
    const group = o.group !== undefined ? o.group : (t.group||"");
    const text  = o.text  !== undefined ? o.text  : (t.text||"");
    const key = group+"::"+text;
    return {id:"b"+i, baseKey:baseKey, key:key, group:group, text:text,
            done: done[key] !== undefined ? !!done[key] : !!t.done};
  }).filter(x=>!del.has(x.baseKey));
  (edits.plan.add||[]).forEach(a=>{
    const key = planKey(a);
    list.push({id:a.id, baseKey:key, key:key, group:a.group||"", text:a.text||"",
               done: done[key] !== undefined ? !!done[key] : !!a.done, added:true});
  });
  return list;
}
/* 分组聚合：分组顺序 = 首次出现顺序；没有分组的排在最前 */
function planGroups(list){
  const groups = [], byName = {};
  list.forEach(x=>{
    const g = x.group || "";
    if(!byName[g]){ byName[g] = {name:g, items:[]}; groups.push(byName[g]); }
    byName[g].items.push(x);
  });
  return groups;
}
function renderPlan(head, body){
  const all = planList();
  const open = all.filter(x=>!x.done), done = all.filter(x=>x.done);
  head.innerHTML = '<h2>任务安排 <span class="cnt">'+open.length+' 进行中</span></h2>'+
    '<button class="iconbtn" id="plAdd" title="新增一条">＋</button>';
  const row = (x)=>
    '<div class="ddl plan'+(x.done?" done":"")+'" data-id="'+esc(x.id)+'" title="点击标记完成">'+
      '<span class="box" data-ptoggle="'+esc(x.id)+'"></span>'+
      '<span class="txt"><span class="tk">'+esc(x.text)+'</span></span>'+
      '<span class="acts"><button data-pedit="'+esc(x.id)+'" title="编辑">✎</button>'+
      '<button class="act-del" data-pdel="'+esc(x.id)+'" title="删除">×</button></span>'+
    '</div>';
  let h = '';
  if(!all.length){
    h += '<p class="rhint">还没有任务 —— 点右上角 ＋ 添加。<br>没有明确 DDL、靠自己推进的事记在这里。</p>';
  }else{
    planGroups(open).forEach(g=>{
      if(g.name) h += '<div class="pgroup">'+esc(g.name)+'</div>';
      g.items.forEach(x=>{ h += row(x); });
    });
    if(done.length){
      h += '<p class="rhint" style="margin-top:14px">已完成</p>';
      done.forEach(x=>{ h += row(x); });
    }
  }
  body.innerHTML = h;

  document.getElementById("plAdd").onclick = ()=>openPlanEditor(null);

  body.querySelectorAll("[data-ptoggle]").forEach(b=>b.onclick = e=>{
    e.stopPropagation();
    const it = planList().find(x=>x.id===b.dataset.ptoggle);
    if(it) togglePlan(it);
  });
  body.querySelectorAll("[data-pedit]").forEach(b=>b.onclick = e=>{
    e.stopPropagation();
    const it = planList().find(x=>x.id===b.dataset.pedit);
    if(it) openPlanEditor(it);
  });
  body.querySelectorAll("[data-pdel]").forEach(b=>b.onclick = e=>{
    e.stopPropagation();
    const it = planList().find(x=>x.id===b.dataset.pdel);
    if(it) delPlan(it);
  });
  body.querySelectorAll(".ddl.plan").forEach(el=>{
    el.onclick = e=>{
      if(e.target.closest(".acts")) return;
      const it = planList().find(x=>x.id===el.dataset.id);
      if(it) togglePlan(it);
    };
  });
}
function togglePlan(it){
  if(SYNC.ok && SYNC.plan){
    syncSavePlan(planList().map(x=>({group:x.group, text:x.text,
      done: x.id===it.id ? !x.done : x.done})));
    return;
  }
  if(!edits.planDone) edits.planDone = {};
  edits.planDone[it.key] = !it.done;
  saveEdits(); render();
}
function delPlan(it){
  if(!confirm("删除「"+(it.text||"")+"」？")) return;
  if(SYNC.ok && SYNC.plan){
    syncSavePlan(planList().filter(x=>x.id!==it.id).map(x=>({group:x.group, text:x.text, done:x.done})));
    return;
  }
  if(it.added) edits.plan.add = (edits.plan.add||[]).filter(x=>x.id !== it.id);
  else edits.plan.del = (edits.plan.del||[]).concat([it.baseKey]);
  if(edits.planDone) delete edits.planDone[it.key];
  saveEdits(); render();
}

function renderLinks(head, body){
  const list = linksList();
  head.innerHTML = '<h2>常用入口</h2><button class="iconbtn" id="lkAdd" title="新增入口">＋</button>';
  body.innerHTML = list.length ? list.map(l=>
    '<div class="rlink">'+
      '<a class="rl-main" href="'+esc(linkHref(l))+'" target="_blank" rel="noopener">'+
        '<span class="ic">'+esc(l.icon||"\u{1F517}")+'</span>'+
        '<span class="lb">'+esc(l.label||l.url)+'</span></a>'+
      '<span class="acts"><button data-ledit="'+esc(l.id)+'" title="编辑">✎</button>'+
      '<button class="act-del" data-ldel="'+esc(l.id)+'" title="删除">×</button></span>'+
    '</div>').join("")
    : '<p class="rhint">还没有入口，点右上角 ＋ 添加。</p>';
  document.getElementById("lkAdd").onclick = ()=>openLinkEditor(null);
  body.querySelectorAll("[data-ledit]").forEach(b=>b.onclick = e=>{
    e.preventDefault(); e.stopPropagation();
    const it = linksList().find(x=>x.id===b.dataset.ledit);
    if(it) openLinkEditor(it);
  });
  body.querySelectorAll("[data-ldel]").forEach(b=>b.onclick = e=>{
    e.preventDefault(); e.stopPropagation();
    const it = linksList().find(x=>x.id===b.dataset.ldel);
    if(it) delLink(it);
  });
}

/* ---------------- DDL / 入口 编辑 ---------------- */
let ddlEditing = null, linkEditing = null;
function openDdlEditor(it){
  ddlEditing = it || null;
  document.getElementById("dTitle").textContent = it ? "编辑 DDL" : "新增 DDL";
  document.getElementById("dDate").value = it ? it.date : (sel || key(TODAY));
  document.getElementById("dTask").value = it ? it.task : "";
  document.getElementById("dDelete").style.display = it ? "" : "none";
  document.getElementById("maskDdl").classList.add("on");
  setTimeout(()=>document.getElementById("dTask").focus(), 30);
}
function delDdl(it){
  if(!confirm("删除「"+(it.task||"")+"」？")) return;
  if(SYNC.ok){
    syncSave(ddlList().filter(x=>x.id!==it.id).map(x=>({date:x.date, task:x.task, done:x.done})));
    return;
  }
  if(it.added) edits.ddl.add = (edits.ddl.add||[]).filter(x=>x.id !== it.id);
  else edits.ddl.del = (edits.ddl.del||[]).concat([it.baseKey]);
  if(edits.ddlDone) delete edits.ddlDone[it.key];
  saveEdits(); render();
}
document.getElementById("dSave").onclick = ()=>{
  const date = document.getElementById("dDate").value;
  const task = document.getElementById("dTask").value.trim();
  if(!date || !task){ alert("日期和事项都要填。"); return; }
  const it = ddlEditing;
  document.getElementById("maskDdl").classList.remove("on");
  if(SYNC.ok){
    const base = ddlList();
    const list = base.map(x=>({date:x.date, task:x.task, done:x.done}));
    if(!it) list.push({date:date, task:task, done:false});
    else{
      const i = base.findIndex(x=>x.id===it.id);
      if(i >= 0) list[i] = {date:date, task:task, done:base[i].done};
    }
    syncSave(list);
    return;
  }
  if(!it){
    edits.ddl.add.push({id:"d"+Date.now(), date:date, task:task, done:false});
  }else if(it.added){
    const a = (edits.ddl.add||[]).find(x=>x.id===it.id);
    if(a){ a.date = date; a.task = task; }
  }else{
    edits.ddl.ovr[it.baseKey] = {date:date, task:task};
  }
  saveEdits();
  document.getElementById("maskDdl").classList.remove("on");
  render();
};
document.getElementById("dDelete").onclick = ()=>{
  const it = ddlEditing;
  document.getElementById("maskDdl").classList.remove("on");
  if(it) delDdl(it);
};
document.getElementById("dCancel").onclick = ()=>document.getElementById("maskDdl").classList.remove("on");

/* ---------------- 任务安排 编辑 ---------------- */
let planEditing = null;
function openPlanEditor(it){
  planEditing = it || null;
  document.getElementById("pTitle").textContent = it ? "编辑任务" : "新增任务";
  document.getElementById("pText").value = it ? (it.text||"") : "";
  document.getElementById("pGroup").value = it ? (it.group||"") : "";
  document.getElementById("pDelete").style.display = it ? "" : "none";
  document.getElementById("maskPlan").classList.add("on");
  setTimeout(()=>document.getElementById("pText").focus(), 30);
}
document.getElementById("pSave").onclick = ()=>{
  const text = document.getElementById("pText").value.trim();
  const group = document.getElementById("pGroup").value.trim();
  if(!text){ alert("事项要填。"); return; }
  const it = planEditing;
  document.getElementById("maskPlan").classList.remove("on");
  if(SYNC.ok && SYNC.plan){
    const base = planList();
    const list = base.map(x=>({group:x.group, text:x.text, done:x.done}));
    if(!it) list.push({group:group, text:text, done:false});
    else{
      const i = base.findIndex(x=>x.id===it.id);
      if(i >= 0) list[i] = {group:group, text:text, done:base[i].done};
    }
    syncSavePlan(list);
    return;
  }
  if(!it){
    edits.plan.add.push({id:"pl"+Date.now(), group:group, text:text, done:false});
  }else if(it.added){
    const a = (edits.plan.add||[]).find(x=>x.id===it.id);
    if(a){ a.group = group; a.text = text; }
  }else{
    edits.plan.ovr[it.baseKey] = {group:group, text:text};
  }
  saveEdits();
  render();
};
document.getElementById("pDelete").onclick = ()=>{
  const it = planEditing;
  document.getElementById("maskPlan").classList.remove("on");
  if(it) delPlan(it);
};
document.getElementById("pCancel").onclick = ()=>document.getElementById("maskPlan").classList.remove("on");

function openLinkEditor(it){
  linkEditing = it || null;
  document.getElementById("kTitle").textContent = it ? "编辑入口" : "新增入口";
  document.getElementById("kIcon").value = it ? (it.icon||"") : "\u{1F4C4}";
  document.getElementById("kLabel").value = it ? (it.label||"") : "";
  document.getElementById("kUrl").value = it ? (it.url||it.path||"") : "";
  document.getElementById("kMode").value = it ? (it.mode||"app") : "app";
  document.getElementById("kDelete").style.display = it ? "" : "none";
  document.getElementById("maskLink").classList.add("on");
  setTimeout(()=>document.getElementById("kLabel").focus(), 30);
}
function delLink(it){
  if(!confirm("删除「"+(it.label||it.url)+"」？")) return;
  if(String(it.id).indexOf("l") === 0 && !(edits.links.add||[]).some(a=>a.id===it.id))
    edits.links.del = (edits.links.del||[]).concat([it.id]);
  else edits.links.add = (edits.links.add||[]).filter(a=>a.id!==it.id);
  saveEdits(); render();
}
document.getElementById("kSave").onclick = ()=>{
  const obj = {
    icon: document.getElementById("kIcon").value.trim() || "\u{1F517}",
    label: document.getElementById("kLabel").value.trim(),
    url: document.getElementById("kUrl").value.trim(),
    path: "", mode: document.getElementById("kMode").value
  };
  if(!obj.label || !obj.url){ alert("名称和路径都要填。"); return; }
  const it = linkEditing;
  if(!it){
    edits.links.add.push(Object.assign({id:"lk"+Date.now()}, obj));
  }else if(String(it.id).indexOf("lk") === 0){
    const a = (edits.links.add||[]).find(x=>x.id===it.id);
    if(a) Object.assign(a, obj);
  }else{
    edits.links.ovr[it.id] = obj;
  }
  saveEdits();
  document.getElementById("maskLink").classList.remove("on");
  render();
};
document.getElementById("kDelete").onclick = ()=>{
  const it = linkEditing;
  document.getElementById("maskLink").classList.remove("on");
  if(it) delLink(it);
};
document.getElementById("kCancel").onclick = ()=>document.getElementById("maskLink").classList.remove("on");

/* ---------------- todo.md 同步 ----------------
   serve.py 在 127.0.0.1 上提供 /api/todo：GET 读文件、POST 写文件。
   用 http 打开时以 data/todo.md 为唯一真源；直接双击 HTML（file://）时退化为构建内副本。 */
let SYNC = {ok:false, items:null, plan:null};
function syncEligible(){ return /^https?:$/.test(location.protocol); }
function parseTodoMd(text){
  const out = [];
  String(text||"").split(/\r?\n/).forEach(line=>{
    const m = /^\s*-\s*\[( |x|X)\]\s*(.+?)\s*$/.exec(line);
    if(!m) return;
    const done = m[1].toLowerCase() === "x";
    const rest = m[2];
    let mm = /^(\d{4})\.(\d{1,2})\.(\d{1,2})\s+(.*)$/.exec(rest), y, mo, da, task;
    if(mm){ y = +mm[1]; mo = +mm[2]; da = +mm[3]; task = mm[4]; }
    else{
      mm = /^(\d{1,2})\.(\d{1,2})\s+(.*)$/.exec(rest);
      if(!mm) return;
      y = TODAY.getFullYear(); mo = +mm[1]; da = +mm[2]; task = mm[3];
    }
    out.push({date:y+"-"+pad(mo)+"-"+pad(da), task:task, done:done});
  });
  return out;
}
function todoMdText(list){
  return list.map(d=>"- ["+(d.done?"x":" ")+"] "+ymOf(d.date)+" "+d.task).join("\n") + "\n";
}
function syncLoad(){
  if(!syncEligible()) return;
  fetch("/api/todo", {cache:"no-store"})
    .then(r=>{ if(!r.ok) throw new Error("bad"); return r.text(); })
    .then(txt=>{ lastTodoText = txt; SYNC.ok = true; SYNC.items = parseTodoMd(txt); render(); })
    .catch(()=>{ SYNC.ok = false; });
}
function syncSave(items){
  if(!SYNC.ok) return false;
  fetch("/api/todo", {method:"POST", headers:{"Content-Type":"text/plain; charset=utf-8"}, body: todoMdText(items)})
    .then(r=>{ if(!r.ok) throw new Error("bad"); return r.text(); })
    .then(txt=>{ lastTodoText = txt; SYNC.items = parseTodoMd(txt); render(); })
    .catch(()=>{ alert("写入 todo.md 失败，检查 serve.py 是否还在运行。"); render(); });
  return true;
}
/* ---------------- tasks.md 同步（任务安排） ----------------
   serve.py 提供 /api/tasks：GET 读 data/tasks.md、POST 写回。
   http:// 打开时以文件为唯一真源；file:// 打开时退化为构建内副本 + 本地覆盖层。 */
function parseTasksMd(text){
  const out = [];
  let group = "";
  String(text||"").split(/\r?\n/).forEach(line=>{
    const s = line.trim();
    if(!s) return;
    if(/^##\s+/.test(s)){ group = s.replace(/^##\s+/,"").trim(); return; }
    if(/^#/.test(s)) return;
    const m = /^-\s*\[( |x|X)\]\s*(.+?)\s*$/.exec(s);
    if(!m) return;
    out.push({group:group, text:m[2], done:m[1].toLowerCase()==="x"});
  });
  return out;
}
function tasksMdText(list){
  const out = ["# 任务安排 · 没有明确 DDL、靠自己推进的事", ""];
  let cur = null;
  list.forEach(t=>{
    const g = t.group || "";
    if(g !== cur){ cur = g; if(g) out.push("## " + g, ""); }
    out.push("- [" + (t.done?"x":" ") + "] " + t.text);
  });
  return out.join("\n") + "\n";
}
function syncLoadPlan(){
  if(!syncEligible()) return;
  fetch("/api/tasks", {cache:"no-store"})
    .then(r=>{ if(!r.ok) throw new Error("bad"); return r.text(); })
    .then(txt=>{ lastPlanText = txt; SYNC.ok = true; SYNC.plan = parseTasksMd(txt); render(); })
    .catch(()=>{});                       /* 没有 tasks.md 就用构建内副本 */
}
function syncSavePlan(items){
  if(!SYNC.ok) return false;
  fetch("/api/tasks", {method:"POST", headers:{"Content-Type":"text/plain; charset=utf-8"}, body: tasksMdText(items)})
    .then(r=>{ if(!r.ok) throw new Error("bad"); return r.text(); })
    .then(txt=>{ lastPlanText = txt; SYNC.plan = parseTasksMd(txt); render(); })
    .catch(()=>{ alert("写入 tasks.md 失败，检查 serve.py 是否还在运行。"); render(); });
  return true;
}
/* ---------------- 外部编辑自动感知 ----------------
   agent 等外部工具直接改 data/ 文件时（serve 模式）：
   - todo.md / tasks.md 变了 → 4 秒内自动并入页面（正在编辑则挂起，结束后再应用）
   - 覆盖层（edits.json，页面改动的服务端副本）变了 → 自动采纳（CLI / 另一浏览器写入的）
   - schedule.json 等变了 → 服务端已重建页面，toast 提示刷新查看 */
let lastTodoText = null;
let lastPlanText = null;
let draftSyncApi = null;                       /* draftEl 定义后接线（见文件底部） */
function editingInFlight(){
  const el = document.activeElement;
  if(el && (/^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName) || el.isContentEditable)) return true;
  return !!document.querySelector(".mask.on");
}
if(syncEligible()){
  let pollBase = null, pendingTodo = null, pendingEdits = null, pendingPlan = null;
  let codeChanged = false, reloadHinted = false;
  function applyTodoText(txt){
    lastTodoText = txt;
    SYNC.ok = true; SYNC.items = parseTodoMd(txt); render();
  }
  function applyPlanText(txt){
    lastPlanText = txt;
    SYNC.ok = true; SYNC.plan = parseTasksMd(txt); render();
  }
  function applyEditsObj(d, mtime){
    editsSuppress = true;
    try{
      edits = Object.assign(emptyEdits(), d || {});
      if(!edits.ddl) edits.ddl = {ovr:{}, add:[], del:[]};
      if(!edits.links) edits.links = {ovr:{}, add:[], del:[]};
      localStorage.setItem(LS_KEY, JSON.stringify(edits));
    }finally{ editsSuppress = false; }
    if(mtime) lastEditsMtime = mtime;
    render();
  }
  function applyPending(){
    if(pendingTodo !== null && !editingInFlight()){
      const txt = pendingTodo; pendingTodo = null;
      if(txt !== lastTodoText) applyTodoText(txt);
    }
    if(pendingPlan !== null && !editingInFlight()){
      const txt = pendingPlan; pendingPlan = null;
      if(txt !== lastPlanText) applyPlanText(txt);
    }
    if(pendingEdits !== null && !editingInFlight()){
      const d = pendingEdits; pendingEdits = null;
      applyEditsObj(d.edits, d.mtime);
    }
    if(draftSyncApi) draftSyncApi.applyPending();
  }
  function pollOnce(){
    if(document.hidden) return;
    fetch("/api/poll", {cache:"no-store"})
      .then(r=>r.json())
      .then(s=>{
        if(pollBase === null){ pollBase = s; return; }   /* 第一次只记基线 */
        if(s.todo !== pollBase.todo){
          pollBase.todo = s.todo;
          fetch("/api/todo", {cache:"no-store"})
            .then(r=> r.ok ? r.text() : Promise.reject())
            .then(txt=>{
              if(txt === lastTodoText || txt === pendingTodo) return;
              if(editingInFlight()) pendingTodo = txt;
              else applyTodoText(txt);
            }).catch(()=>{});
        }
        if(s.tasks !== undefined && s.tasks !== pollBase.tasks){
          pollBase.tasks = s.tasks;
          fetch("/api/tasks", {cache:"no-store"})
            .then(r=> r.ok ? r.text() : Promise.reject())
            .then(txt=>{
              if(txt === lastPlanText || txt === pendingPlan) return;
              if(editingInFlight()) pendingPlan = txt;
              else applyPlanText(txt);
            }).catch(()=>{});
        }
        if(s.edits !== undefined && s.edits !== pollBase.edits){
          pollBase.edits = s.edits;
          if(s.edits === lastEditsMtime) return;         /* 自己刚 POST 的回声 */
          fetch("/api/edits", {cache:"no-store"})
            .then(r=> r.ok ? r.json() : Promise.reject())
            .then(d=>{
              if(!d || JSON.stringify(d.edits) === JSON.stringify(edits)){ if(d) lastEditsMtime = d.mtime; return; }
              if(editingInFlight()) pendingEdits = d;
              else applyEditsObj(d.edits, d.mtime);
            }).catch(()=>{});
        }
        if(s.html !== pollBase.html){
          pollBase.html = s.html;
          toast("日程数据已更新，刷新页面查看");
        }
        /* 前端代码变了（我改了前端但浏览器还跑着旧版本）：自动刷新，
           正在编辑就先等编辑结束，免得把没保存的内容冲掉。 */
        if(s.code && BUILD && s.code !== BUILD){
          codeChanged = true;
          if(!reloadHinted && editingInFlight()){
            reloadHinted = true;
            toast("页面已更新，改完手头的东西会自动刷新");
          }
        }
        if(codeChanged && !editingInFlight()) location.reload();
        if(draftSyncApi) draftSyncApi.onPoll(s);
      }).catch(()=>{});
  }
  setInterval(pollOnce, 4000);
  document.addEventListener("visibilitychange", ()=>{ if(!document.hidden){ pollOnce(); applyPending(); } });
  document.addEventListener("focusout", applyPending);
  /* 新浏览器 / 清过缓存：本地没有覆盖层而服务端有 → 恢复自己的页面改动 */
  if(!localStorage.getItem(LS_KEY)){
    fetch("/api/edits", {cache:"no-store"})
      .then(r=> r.ok ? r.json() : Promise.reject())
      .then(d=>{
        if(d && d.edits && Object.keys(d.edits).length){
          applyEditsObj(d.edits, d.mtime);
          toast("已从本地服务恢复页面改动");
        }
      }).catch(()=>{});
  }
}
function ddlPlain(){ return ddlList().map(x=>({date:x.date, task:x.task, done:x.done})); }
function saveUI(){ try{ localStorage.setItem(LS_KEY+"_ui", JSON.stringify(ui)); }catch(e){} }

/* ---------------- day view ---------------- */
function insZone(after){
  return '<div class="ins" data-after="'+esc(after)+'"><button class="plus" title="在这里插入新安排">＋</button></div>';
}
function renderCell(it, cf){
  const meta = typeMeta(it.type);
  let h = '<div class="cell'+(cf&&cf.with.length?" hasconflict":"")+'" data-id="'+esc(it.id)+'">';
  h += '<div class="tcol"><div class="k" style="background:'+meta.v+'"></div><b>'+esc(it.t||"—")+'</b>'+(it.d?'<span>'+esc(it.d)+'</span>':'')+'</div>';
  h += '<div class="cbody"><div class="chead"><h3>'+esc(it.title)+'<span class="tag '+meta.c+'">'+meta.label+'</span>';
  if(it.edited) h += '<span class="edited">已本地修改</span>';
  h += '</h3><div class="cact">';
  h += '<button class="iconbtn edit" title="编辑" data-edit="'+esc(it.id)+'">✎</button>';
  h += '<button class="iconbtn del" title="删除" data-del="'+esc(it.id)+'">×</button>';
  h += '</div></div>';
  if(it.detail) h += '<p>'+esc(it.detail)+'</p>';
  if(it.list && it.list.length) h += '<ul class="mini">'+it.list.map(x=>'<li>'+esc(x)+'</li>').join("")+'</ul>';
  if(it.links && it.links.length){
    h += '<div class="lkgroup" style="margin-top:9px"><b>资料</b></div>';
    it.links.forEach(l=>{ h += lnkHtml(l); });
  }
  if(it.out) h += '<div class="output"><b>产出：</b>'+esc(it.out)+'</div>';
  if(cf && cf.with.length) h += '<div class="corner">⚠ 与 '+cf.with.map(w=>esc(w.t||"该段")).join("、")+' 重叠</div>';
  h += '</div></div>';
  return h;
}
function renderDay(k){
  const d = parseKey(k);
  const plan = BAKED[k];
  const list = buildList(k);
  const cf = conflicts(list);
  const sec = daySections(k);
  let h = "";
  h += '<div class="dayhead">';
  h += '<h2>'+d.getFullYear()+' 年 '+(d.getMonth()+1)+' 月 '+d.getDate()+' 日 <small>'+WEEK[d.getDay()]+'</small>';
  if(k===key(TODAY)) h += '<span class="tag today-tag">今天</span>';
  h += '</h2></div>';

  const tdone = (sec.tasks||[]).filter(t=>taskDone(k, taskText(t))).length;
  const tprog = (sec.tasks||[]).length
    ? '<span class="chip prog'+(tdone===sec.tasks.length?" all":"")+'"><b>'+tdone+'</b> / '+sec.tasks.length+' 已完成</span>' : '';
  if(sec.tasks && sec.tasks.length){
    h += '<div class="sechead"><h2>今日主要任务</h2>'+tprog+'<button class="iconbtn" data-secedit="tasks" title="编辑今日主要任务">✎</button></div>';
    h += '<div class="taskbox">';
    h += '<div class="taskbar'+(tdone===sec.tasks.length?" done":"")+'" title="已完成 '+tdone+' / '+sec.tasks.length+'">'+
         '<i style="width:'+Math.round(tdone/sec.tasks.length*100)+'%"></i></div>';
    sec.tasks.forEach(t=>{
      const txt = taskText(t);
      const lnk = typeof t==="string" ? null : t.link;
      const done = taskDone(k, txt);
      /* 自动匹配到的资料：显式链接在前，自动补的在后，同一个文件不重复 */
      const auto = matchTaskPaths(txt).filter(p=> !lnk || !sameTarget(lnk, p));
      const chips = (lnk? lnkHtml(lnk) : "") +
        auto.map(p=>lnkHtml({url:p.path, path:p.path, label:p.label, kind:p.kind, mode:"app"})).join("");
      h += '<div class="task'+(done?" done":"")+'" data-task="'+esc(txt)+'" role="checkbox" aria-checked="'+(done?"true":"false")+'" tabindex="0" '+
           'title="'+(done?"点击取消勾选":"点击标记完成")+'">'+
           '<span class="tkbox" aria-hidden="true"></span>'+
           '<div class="tmain"><span class="tx">'+esc(txt)+'</span>'+
           (chips? '<div class="tlinks">'+chips+'</div>' : '')+
           '</div></div>';
    });
    h += '</div>';
  }else{
    h += '<div class="sechead"><h2>今日主要任务</h2><button class="iconbtn" data-secedit="tasks" title="编辑今日主要任务">✎</button></div>';
    h += '<div class="taskbox"><div class="tasknone">还没有记录 —— 点右上角 ✎ 写下今天要完成的事。</div></div>';
  }

  if(list.length){
    h += '<div class="sechead"><h2>时间安排</h2><span class="chip act" id="addInline">＋ 新增</span></div>';
    h += '<div class="cells">'+insZone("__head__");
    list.forEach((it,i)=>{
      h += renderCell(it, cf[it.id]);
      h += insZone(i===list.length-1 ? "__tail__" : list[i+1].id);
    });
    h += '</div>';
  }else{
    h += '<div class="sechead"><h2>时间安排</h2><span class="chip act" id="addInline">＋ 新增</span></div>';
    h += '<div class="empty" style="margin-top:14px"><h3>这天还没排具体时间</h3></div>';
  }
  return h;
}

/* ---------------- render ---------------- */
function taskSummary(k){
  const list = daySections(k).tasks || [];
  if(!list.length) return "";
  const done = list.filter(t=>taskDone(k, taskText(t))).length;
  return " · 任务 "+done+"/"+list.length;
}
function renderMain(){
  document.getElementById("todayline").innerHTML =
    "<b>今天 "+TODAY.getFullYear()+"."+pad(TODAY.getMonth()+1)+"."+pad(TODAY.getDate())+" "+WEEK[TODAY.getDay()]+"</b>共 "+
    buildList(key(TODAY)).length+" 项安排"+taskSummary(key(TODAY))+'';
  document.getElementById("main").innerHTML = renderDay(sel);
  bind();
}
function render(){
  renderMain(); renderCal(); renderStrip(); renderRight();
}
function bind(){
  document.querySelectorAll("[data-go]").forEach(a=>a.onclick=e=>{e.preventDefault();sel=a.dataset.go;render();});
  const add = document.getElementById("addInline");
  if(add) add.onclick = ()=>openAdd("__tail__");
  document.querySelectorAll(".ins .plus").forEach(p=>p.onclick = e=>{
    e.stopPropagation(); openAdd(p.parentElement.dataset.after);
  });
  document.querySelectorAll("[data-edit]").forEach(b=>b.onclick = e=>{e.stopPropagation(); openEdit(b.dataset.edit);});
  document.querySelectorAll("[data-del]").forEach(b=>b.onclick = e=>{e.stopPropagation(); delItem(b.dataset.del);});
  document.querySelectorAll("[data-secedit]").forEach(b=>b.onclick = e=>{e.stopPropagation(); openSecEditor(b.dataset.secedit);});
  document.querySelectorAll(".task[data-task]").forEach(el=>{
    const txt = el.dataset.task;
    const hit = e => e.target.closest("a");
    el.onclick = e=>{ if(hit(e)) return; toggleTask(sel, txt); };
    el.onkeydown = e=>{ if(e.key===" "||e.key==="Enter"){ e.preventDefault(); toggleTask(sel, txt); } };
  });
  document.querySelectorAll(".quick button").forEach(b=>b.onclick=()=>{
    const p=b.dataset.q.split("|"); document.getElementById("fTime").value=p[0]; document.getElementById("fDur").value=p[1];
  });
  bindDrag();
}

/* ---------------- add / edit 条目 ---------------- */
function describePos(after){
  if(after==="__head__") return "最前面";
  if(after==="__tail__") return "最后面";
  const list = buildList(sel);
  const i = list.findIndex(x=>x.id===after);
  if(i<0) return "末尾";
  return "「"+(list[i].title||"").slice(0,14)+"」之后";
}
function suggestStart(after){
  const list = buildList(sel);
  const endOf = it => { const s=toMin(it.t), d=durMin(it.d); return (s==null)?null:s+d; };
  if(after==="__head__"){
    const f=list[0]; if(f){ const s=toMin(f.t), d=durMin(f.d); if(s!=null && d>0) return pad(Math.floor(Math.max(0,s-d)/60))+":"+pad(Math.max(0,s-d)%60); }
    return "09:00";
  }
  if(after==="__tail__"){
    const l=list[list.length-1]; if(l){ const e=endOf(l); if(e!=null) return pad(Math.floor(e/60)%24)+":"+pad(e%60); }
    return "20:00";
  }
  const i=list.findIndex(x=>x.id===after);
  if(i>=0){ const e=endOf(list[i]); if(e!=null) return pad(Math.floor(e/60)%24)+":"+pad(e%60); }
  return "20:00";
}
function openAdd(after){
  modalMode="add"; modalAnchor=after; modalId=null;
  document.getElementById("mTitle").textContent = "新增安排";
  document.getElementById("mHint").innerHTML = "插入到 <b>"+esc(sel)+"</b> 的 "+esc(describePos(after));
  document.getElementById("fTime").value = suggestStart(after);
  document.getElementById("fDur").value = "1h";
  document.getElementById("fTitle").value = "";
  document.getElementById("fType").value = "study";
  document.getElementById("fDetail").value = "";
  document.getElementById("fList").value = "";
  renderLinkRows([]);
  document.getElementById("fOut").value = "";
  document.getElementById("mDelete").style.display = "none";
  document.getElementById("mask").classList.add("on");
  setTimeout(()=>document.getElementById("fTitle").focus(),30);
}
function openEdit(id){
  const it = buildList(sel).find(x=>x.id===id);
  if(!it) return;
  modalMode="edit"; modalId=id;
  document.getElementById("mTitle").textContent = "编辑安排";
  document.getElementById("mHint").innerHTML = "日期 <b>"+esc(sel)+"</b>";
  document.getElementById("fTime").value = (it.t && it.t!=="—")?it.t:"";
  document.getElementById("fDur").value = it.d||"";
  document.getElementById("fTitle").value = it.title||"";
  document.getElementById("fType").value = typeKey(it.type);
  document.getElementById("fDetail").value = it.detail||"";
  document.getElementById("fList").value = (it.list||[]).join("\n");
  renderLinkRows(it.links||[]);
  document.getElementById("fOut").value = it.out||"";
  document.getElementById("mDelete").style.display = "";
  document.getElementById("mask").classList.add("on");
  setTimeout(()=>document.getElementById("fTitle").focus(),30);
}
function readForm(){
  return {
    t: document.getElementById("fTime").value.trim(),
    d: document.getElementById("fDur").value.trim(),
    title: document.getElementById("fTitle").value.trim(),
    type: document.getElementById("fType").value,
    detail: document.getElementById("fDetail").value.trim(),
    list: document.getElementById("fList").value.split("\n").map(s=>s.trim()).filter(Boolean),
    links: collectLinks(),
    out: document.getElementById("fOut").value.trim()
  };
}
document.getElementById("mSave").onclick = ()=>{
  const f = readForm();
  if(!f.title){ alert("请填写事项"); return; }
  if(modalMode==="add"){
    if(!edits.adds[sel]) edits.adds[sel]=[];
    edits.adds[sel].push(Object.assign({id:"u"+Date.now(), after:modalAnchor, user:true}, f));
  }else{
    const it = buildList(sel).find(x=>x.id===modalId);
    if(!it) return;
    if(it.src==="user"){
      const arr = edits.adds[sel]||[];
      const j = arr.findIndex(x=>x.id===modalId);
      if(j>=0) arr[j] = Object.assign({}, arr[j], f);
    }else{
      if(!edits.ovr[sel]) edits.ovr[sel]={};
      edits.ovr[sel][modalId] = f;
    }
  }
  saveEdits();
  document.getElementById("mask").classList.remove("on");
  render();
};
function delItem(id){
  const it = buildList(sel).find(x=>x.id===id);
  if(!it) return;
  if(!confirm("删除「"+(it.title||"")+"」？")) return;
  if(it.src==="user"){
    edits.adds[sel] = (edits.adds[sel]||[]).filter(x=>x.id!==id);
  }else{
    if(!edits.hides[sel]) edits.hides[sel]=[];
    edits.hides[sel].push(id);
    if(edits.ovr[sel]) delete edits.ovr[sel][id];
  }
  saveEdits(); render();
}
document.getElementById("mDelete").onclick = ()=>{
  document.getElementById("mask").classList.remove("on");
  delItem(modalId);
};

/* ---------------- 拖动改时间 ----------------
   在日视图里按住时间块上下拖 = 改开始时间（按 5 分钟吸附）；
   页面自己加的条目改写 edits.adds，文件里的条目写覆盖 edits.ovr。 */
const DRAG_PX_PER_MIN = 2;    /* 拖 2px = 1 分钟（1 小时 = 120px） */
const DRAG_SNAP_MIN  = 5;     /* 吸附到 5 分钟 */
function setItemTime(id, m){
  const it = buildList(sel).find(x=>x.id===id);
  if(!it) return;
  const t = pad(Math.floor(m/60)) + ":" + pad(m%60);
  if(it.src==="user"){
    const arr = edits.adds[sel]||[];
    const j = arr.findIndex(x=>x.id===id);
    if(j<0) return;
    arr[j] = Object.assign({}, arr[j], {t:t});
  }else{
    if(!edits.ovr[sel]) edits.ovr[sel] = {};
    edits.ovr[sel][id] = Object.assign({}, edits.ovr[sel][id]||{}, {t:t});
  }
  saveEdits(); render();
  toast("「"+(it.title||"")+"」时间改为 "+t);
}
function bindDrag(){
  document.querySelectorAll(".cell").forEach(el=>{
    el.addEventListener("pointerdown", e=>{
      if(e.button !== 0) return;
      if(e.target.closest("button,a,input,textarea,select")) return;
      const id = el.dataset.id;
      const it = buildList(sel).find(x=>x.id===id);
      if(!it) return;
      const s0 = toMin(it.t);
      if(s0===null) return;                 /* 没有时间的块不拖 */
      const y0 = e.clientY;
      let moved = false, nt = s0;
      try{ el.setPointerCapture(e.pointerId); }catch(err){}
      const move = ev=>{
        const dy = ev.clientY - y0;
        if(!moved && Math.abs(dy) < 5) return;
        if(!moved){ moved = true; el.classList.add("dragging"); }
        const dm = Math.round(dy / DRAG_PX_PER_MIN / DRAG_SNAP_MIN) * DRAG_SNAP_MIN;
        nt = Math.max(0, Math.min(23*60+59, s0 + dm));
        const lab = el.querySelector(".tcol b");
        if(lab) lab.textContent = pad(Math.floor(nt/60)) + ":" + pad(nt%60);
      };
      const up = ()=>{
        el.removeEventListener("pointermove", move);
        el.removeEventListener("pointerup", up);
        el.removeEventListener("pointercancel", up);
        el.classList.remove("dragging");
        if(moved && nt !== s0) setItemTime(id, nt);
      };
      el.addEventListener("pointermove", move);
      el.addEventListener("pointerup", up);
      el.addEventListener("pointercancel", up);
    });
  });
}

/* ---------------- 段落编辑（今日主要任务） ---------------- */
function openSecEditor(kind){
  secMode = kind;
  const sec = daySections(sel);
  document.getElementById("sTitle").textContent = "编辑 · 今日主要任务";
  document.getElementById("sHint").innerHTML = "日期 <b>"+esc(sel)+"</b>";
  const box = document.getElementById("secBody");
  if(kind==="tasks"){
    const txt = (sec.tasks||[]).map(t=> typeof t==="string"? t : (t.t||"")).join("\n");
    box.innerHTML = '<div class="fld"><label>今天要完成的事（一行一条）</label>'+
      '<textarea id="tasksBox" style="min-height:220px" placeholder="例：&#10;读论文 30 页&#10;写代码 + 出图">'+
      esc(txt)+'</textarea></div>'+
      '<div style="font-size:11.5px;color:#adb5bd">改完保存，我排时间时会按这里的顺序和 DDL 一起综合。</div>';
  }
  document.getElementById("maskSec").classList.add("on");
  setTimeout(()=>{const b=document.getElementById("tasksBox"); if(b) b.focus();},30);
}
document.getElementById("sCancel").onclick = ()=>document.getElementById("maskSec").classList.remove("on");
document.getElementById("sSave").onclick = ()=>{
  if(!edits.sections[sel]) edits.sections[sel] = {};
  if(secMode==="tasks"){
    const old = daySections(sel).tasks || [];
    const lines = document.getElementById("tasksBox").value.split("\n").map(s=>s.trim()).filter(Boolean);
    // 文字未变的任务保留原有链接
    edits.sections[sel].tasks = lines.map(line=>{
      const hit = old.find(t => (typeof t==="string"? t : (t.t||"")) === line);
      if(hit && typeof hit!=="string" && hit.link) return {t:line, link:hit.link};
      return line;
    });
  }
  saveEdits();
  document.getElementById("maskSec").classList.remove("on");
  render();
};

/* ---------------- 链接行 ---------------- */
/* 资料类型徽标：路径/链接能自己说明它是什么，不再让人手选分类 */
const EXT_BADGE = {
  pdf:"PDF", doc:"DOC", docx:"DOC", ppt:"PPT", pptx:"PPT", xls:"XLS", xlsx:"XLS", csv:"CSV",
  md:"MD", txt:"TXT", json:"JSON", html:"HTML", tex:"TEX", py:"PY", ipynb:"IPYNB",
  zip:"ZIP", rar:"ZIP", "7z":"ZIP",
  png:"图片", jpg:"图片", jpeg:"图片", gif:"图片", svg:"图片", webp:"图片",
  mp4:"视频", mov:"视频", mkv:"视频", mp3:"音频", wav:"音频", m4a:"音频"
};
function fileBadge(l){
  const u = String((l && (l.path || l.url)) || "").trim();
  if(!u) return "";
  if(/^https?:/i.test(u)) return "网页";
  if(/^mailto:/i.test(u)) return "邮件";
  const clean = u.replace(/[?#].*$/, "").replace(/[\\/]+$/, "");
  const m = /\.([A-Za-z0-9]{1,6})$/.exec(clean);
  if(!m) return "文件夹";
  const ext = m[1].toLowerCase();
  return EXT_BADGE[ext] || ext.toUpperCase();
}
/* 打开方式：app = 系统默认应用（文件夹→资源管理器，md→默认 markdown 编辑器）；browser = 浏览器打开。
   本地路径（file:// 或手填的 D:\x / \\server\x）在 http 页面统一由下方拦截器交给 /api/open。 */
function linkHref(l){
  if(!l) return "";
  const u = String(l.url||"").trim();
  if(!u) return "";
  if(/^(https?:|mailto:|file:)/i.test(u)) return u;
  /* 手填的本地路径规范成 file:// URL，否则浏览器会把 D:\x 当相对地址解析掉 */
  if(/^[A-Za-z]:[\\/]/.test(u) || /^\\\\/.test(u))
    return "file:///" + encodeURIComponent(u.replace(/\\/g,"/"));
  return u;
}
/* http 模式（serve.py 在跑）时，浏览器不允许网页直接导航本地文件链接，
   交给本地服务用系统默认程序打开；file:// 模式下不拦截，走原生导航。 */
if(/^https?:$/i.test(location.protocol)){
  document.addEventListener("click", function(e){
    const a = e.target.closest && e.target.closest("a[href]");
    if(!a) return;
    const href = a.getAttribute("href") || "";
    let p = null;
    if(/^file:\/\//i.test(href)){
      p = href.replace(/^file:\/\/\/?/i, "");
      try{ p = decodeURIComponent(p); }catch(err){}
    }else if(/^[A-Za-z]:[\\/]/.test(href) || /^\\\\/.test(href)){
      p = href;                                /* 旧数据里存过的裸路径 */
    }
    if(p === null) return;
    e.preventDefault();
    fetch("/api/open", {method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({path:p})})
      .then(function(r){ return r.json().catch(function(){ return null; }); })
      .then(function(d){
        if(d && d.error) toast(d.error);
        else if(!d || !d.ok) toast("打开失败：本地服务没有在运行");
      })
      .catch(function(){ toast("打开失败：本地服务没有在运行"); });
  });
}
function renderLinkRows(list){
  const box = document.getElementById("linkRows");
  box.innerHTML = "";
  (list||[]).forEach(l=>addLinkRow(l));
  if(!(list||[]).length) addLinkRow();
}
function addLinkRow(l){
  l = l || {};
  const mode = l.mode || "app";
  const box = document.getElementById("linkRows");
  const div = document.createElement("div");
  div.className = "linkrow";
  div.innerHTML =
    '<input class="lk-label" placeholder="显示名（如：Chapter4 课件）" value="'+esc(l.label||"")+'">'+
    '<input class="lk-url" placeholder="路径或链接" value="'+esc(l.url||"")+'">'+
    '<select class="lk-mode"><option value="app"'+(mode!=="browser"?" selected":"")+'>系统应用</option>'+
      '<option value="browser"'+(mode==="browser"?" selected":"")+'>浏览器</option></select>'+
    '<span class="lk-badge" title="按路径自动识别">'+esc(fileBadge(l)||"—")+'</span>'+
    '<button class="rm" title="移除这条">×</button>';
  box.appendChild(div);
  div.querySelector(".rm").onclick = ()=>div.remove();
  const urlIn = div.querySelector(".lk-url"), badge = div.querySelector(".lk-badge");
  urlIn.addEventListener("input", ()=>{ badge.textContent = fileBadge({url:urlIn.value}) || "—"; });
}
function collectLinks(){
  const out = [];
  document.querySelectorAll("#linkRows .linkrow").forEach(r=>{
    const url = r.querySelector(".lk-url").value.trim();
    const label = r.querySelector(".lk-label").value.trim();
    const mode = r.querySelector(".lk-mode").value;
    if(url || label) out.push({url:url, label:label, mode:mode});
  });
  return out;
}
function fillQuickLinks(){
  const box = document.getElementById("linkQuick");
  box.innerHTML = QUICK_LINKS.map((q,i)=>'<button class="qbtn" data-qk="'+i+'" style="border-style:solid">'+esc(q.short)+'</button>').join("");
  box.querySelectorAll("[data-qk]").forEach(b=>b.onclick=()=>{
    const q = QUICK_LINKS[+b.dataset.qk];
    const div = document.createElement("div");
    div.className = "linkrow";
    div.innerHTML =
      '<input class="lk-label" placeholder="显示名" value="'+esc(q.label)+'">'+
      '<input class="lk-url" placeholder="链接地址" value="'+esc(q.url)+'">'+
      '<select class="lk-mode"><option value="app"'+(q.mode!=="browser"?" selected":"")+'>系统应用</option>'+
        '<option value="browser"'+(q.mode==="browser"?" selected":"")+'>浏览器</option></select>'+
      '<span class="lk-badge" title="按路径自动识别">'+esc(fileBadge({path:q.path,url:q.url})||"—")+'</span>'+
      '<button class="rm" title="移除">×</button>';
    div.querySelector(".rm").onclick = ()=>div.remove();
    const u = div.querySelector(".lk-url"), bd = div.querySelector(".lk-badge");
    u.addEventListener("input", ()=>{ bd.textContent = fileBadge({url:u.value}) || "—"; });
    document.getElementById("linkRows").appendChild(div);
  });
}

/* ---------------- 布局：宽度 / 收起 / 上下分栏 / 草稿 ---------------- */
const app = document.getElementById("app");
const rightEl = document.getElementById("right");
const LEFT_MIN = 212, LEFT_MAX = 470, RIGHT_MIN = 220, RIGHT_MAX = 560;

function applyUI(){
  app.classList.toggle("lc", !!ui.lc);
  app.classList.toggle("rc", !ui.rc);
  app.style.setProperty("--lw", (ui.lc ? 64 : ui.lw) + "px");
  app.style.setProperty("--rw", (ui.rc ? ui.rw : 0) + "px");
  rightEl.style.setProperty("--draft-h", ui.draftH + "px");
  document.getElementById("left").style.setProperty("--chat-h", (ui.chatH || 250) + "px");
  const hl = document.getElementById("handleL"), hr = document.getElementById("handleR");
  document.querySelector("#handleL svg").style.transform = ui.lc ? "" : "rotate(180deg)";
  document.querySelector("#handleR svg").style.transform = ui.rc ? "" : "rotate(180deg)";
  hl.title = ui.lc ? "展开日期栏" : "收起日期栏";
  hr.title = ui.rc ? "收起侧边栏" : "展开侧边栏";
  saveUI();
}

document.getElementById("handleL").onclick = ()=>{
  ui.lc = !ui.lc; applyUI(); render();
  if(ui.lc) requestAnimationFrame(()=>{ sizeStrip(); centerOn(sel, false); fadeStrip(); });
};
document.getElementById("handleR").onclick = ()=>{
  ui.rc = !ui.rc; applyUI(); render();
};

function bindResizer(el, side){
  el.addEventListener("pointerdown", e=>{
    if(side === "l" ? ui.lc : !ui.rc) return;
    e.preventDefault();
    try{ el.setPointerCapture(e.pointerId); }catch(err){}
    el.classList.add("dragging");
    document.body.classList.add("col-resizing");
    const x0 = e.clientX;
    const w0 = side === "l" ? ui.lw : ui.rw;
    const move = ev=>{
      const dx = ev.clientX - x0;
      if(side === "l"){
        ui.lw = Math.max(LEFT_MIN, Math.min(LEFT_MAX, Math.round(w0 + dx)));
        app.style.setProperty("--lw", ui.lw + "px");
      }else{
        ui.rw = Math.max(RIGHT_MIN, Math.min(RIGHT_MAX, Math.round(w0 - dx)));
        app.style.setProperty("--rw", ui.rw + "px");
      }
    };
    const up = ()=>{
      el.classList.remove("dragging");
      document.body.classList.remove("col-resizing");
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      saveUI();
      if(ui.lc){ sizeStrip(); fadeStrip(); }
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  });
}
bindResizer(document.getElementById("resizeL"), "l");
bindResizer(document.getElementById("resizeR"), "r");

(function bindSplitter(){
  const sp = document.getElementById("splitter");
  sp.addEventListener("pointerdown", e=>{
    if(!ui.rc) return;
    e.preventDefault();
    try{ sp.setPointerCapture(e.pointerId); }catch(err){}
    sp.classList.add("dragging");
    document.body.classList.add("row-resizing");
    const box = rightEl.getBoundingClientRect();
    const move = ev=>{
      const h = box.bottom - ev.clientY - 11;
      ui.draftH = Math.max(110, Math.min(Math.round(box.height - 240), Math.round(h)));
      rightEl.style.setProperty("--draft-h", ui.draftH + "px");
    };
    const up = ()=>{
      sp.classList.remove("dragging");
      document.body.classList.remove("row-resizing");
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      saveUI();
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  });
})();

/* 草稿区 */
const draftEl = document.getElementById("draft");
draftEl.value = ui.draft || "";
draftEl.addEventListener("input", ()=>{ ui.draft = draftEl.value; saveUI(); });
/* 草稿 ↔ data/draft.md：页面编辑防抖回写；文件被外部（agent/CLI）改动时自动采纳 */
if(syncEligible()){
  let lastDraft = null, pendingDraft = null, draftTimer = 0;
  function applyDraft(txt){
    lastDraft = txt;
    if(txt !== ui.draft){ ui.draft = txt; draftEl.value = txt; saveUI(); }
  }
  draftSyncApi = {
    onPoll(s){
      if(s.draft === undefined || s.draft === this._mt) return;
      this._mt = s.draft;
      fetch("/api/draft", {cache:"no-store"})
        .then(r=> r.ok ? r.text() : Promise.reject())
        .then(txt=>{
          if(txt === lastDraft || txt === draftEl.value || txt === pendingDraft) return;
          if(editingInFlight() && document.activeElement === draftEl) pendingDraft = txt;
          else applyDraft(txt);
        }).catch(()=>{});
    },
    applyPending(){
      if(pendingDraft !== null && document.activeElement !== draftEl){
        const txt = pendingDraft; pendingDraft = null;
        applyDraft(txt);
      }
    }
  };
  draftEl.addEventListener("input", ()=>{
    clearTimeout(draftTimer);
    draftTimer = setTimeout(()=>{
      const txt = draftEl.value;
      if(txt === lastDraft) return;
      lastDraft = txt;
      fetch("/api/draft", {method:"POST", headers:{"Content-Type":"text/plain; charset=utf-8"},
        body: txt}).catch(()=>{});
    }, 800);
  });
  /* 启动：文件优先；文件不存在时把浏览器里的旧草稿迁移上去 */
  fetch("/api/draft", {cache:"no-store"})
    .then(r=>{ if(r.ok) return r.text(); throw new Error("none"); })
    .then(txt=>{
      lastDraft = txt;
      if(txt !== ui.draft){ ui.draft = txt; draftEl.value = txt; saveUI(); }
    })
    .catch(()=>{
      if(ui.draft){
        lastDraft = ui.draft;
        fetch("/api/draft", {method:"POST", headers:{"Content-Type":"text/plain; charset=utf-8"},
          body: ui.draft}).catch(()=>{});
      }
    });
}

document.getElementById("prevM").onclick = ()=>{ view = new Date(view.getFullYear(), view.getMonth()-1, 1); renderCal(); };
document.getElementById("nextM").onclick = ()=>{ view = new Date(view.getFullYear(), view.getMonth()+1, 1); renderCal(); };
document.getElementById("todayBtn").onclick = ()=>{ sel = key(TODAY); view = new Date(TODAY.getFullYear(), TODAY.getMonth(), 1); render(); };

const mask = document.getElementById("mask");
document.getElementById("mCancel").onclick = ()=>mask.classList.remove("on");
document.getElementById("addLinkRow").onclick = ()=>{ addLinkRow(); };
/* 点遮罩关闭弹窗：必须「在遮罩上按下」且「在遮罩上松开」才算真点了外面。
   否则在输入框里鼠标全选、拖到框外松手，也会把弹窗误关掉。 */
const MASK_IDS = ["mask","maskSec","maskDdl","maskPlan","maskLink","maskCfg"];
const MASK_ON_CLOSE = {};
MASK_IDS.forEach(id=>{
  const m = document.getElementById(id);
  if(!m) return;
  let downOnMask = false;
  m.addEventListener("mousedown", e=>{ downOnMask = (e.target === m); });
  m.addEventListener("mouseup", e=>{
    const close = downOnMask && e.target === m;
    downOnMask = false;
    if(!close) return;
    m.classList.remove("on");
    const cb = MASK_ON_CLOSE[id];
    if(cb) cb();
  });
});
document.addEventListener("keydown", e=>{
  if(e.key !== "Escape") return;
  MASK_IDS.forEach(id=>{
    const m = document.getElementById(id);
    if(!m) return;
    m.classList.remove("on");
    const cb = MASK_ON_CLOSE[id];
    if(cb) cb();
  });
});


/* ---------------- 左栏助手 ---------------- */
const chatlog = document.getElementById("chatlog");
const chatform = document.getElementById("chatform");
const chatinput = document.getElementById("chatinput");
const chatSend = chatform.querySelector("button.send");
const chatHistory = [];
let chatBusy = false;

let toastTimer = 0;
function toast(text){
  let el = document.getElementById("toast");
  if(!el){ el = document.createElement("div"); el.id = "toast"; document.body.appendChild(el); }
  el.textContent = text;
  el.classList.add("on");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(()=>el.classList.remove("on"), 1800);
}
function addMsg(cls, text){
  const d = document.createElement("div");
  d.className = "msg " + cls;
  d.textContent = text;
  chatlog.appendChild(d);
  chatlog.scrollTop = chatlog.scrollHeight;
  return d;
}
if(!syncEligible()){
  chatinput.disabled = true;
  chatinput.placeholder = "本地服务未启动";
  chatSend.disabled = true;
}
chatform.addEventListener("submit", e=>{
  e.preventDefault();
  const q = chatinput.value.trim();
  if(!q || chatBusy) return;
  addMsg("me", q);
  chatinput.value = "";
  chatBusy = true;
  chatSend.disabled = true;
  const wait = addMsg("bot", "…");
  fetch("/api/chat", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({message: q, history: chatHistory.slice(-8)})
  })
    .then(r=>r.json())
    .then(d=>{
      wait.remove();
      if(d.reply){
        addMsg("bot", d.reply);
        chatHistory.push({role:"user", content:q}, {role:"assistant", content:d.reply});
      }else{
        addMsg("err", d.error || "没有返回内容");
      }
    })
    .catch(()=>{ wait.remove(); addMsg("err", "请求失败，确认 serve.py 在运行"); })
    .finally(()=>{ chatBusy = false; chatSend.disabled = false; });
});

/* 左栏：日历 / 助手 的高度分割 */
(function bindChatSplit(){
  const sp = document.getElementById("chatSplit");
  const leftEl2 = document.getElementById("left");
  sp.addEventListener("pointerdown", e=>{
    if(ui.lc) return;
    e.preventDefault();
    try{ sp.setPointerCapture(e.pointerId); }catch(err){}
    sp.classList.add("dragging");
    document.body.classList.add("row-resizing");
    const box = leftEl2.getBoundingClientRect();
    const move = ev=>{
      const hgt = box.bottom - ev.clientY - 10;
      ui.chatH = Math.max(120, Math.min(Math.round(box.height - 210), Math.round(hgt)));
      leftEl2.style.setProperty("--chat-h", ui.chatH + "px");
    };
    const up = ()=>{
      sp.classList.remove("dragging");
      document.body.classList.remove("row-resizing");
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      saveUI();
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  });
})();

/* 供应商配置 */
const maskCfg = document.getElementById("maskCfg");
const PRESETS = {
  deepseek:{baseUrl:"https://api.deepseek.com/v1", model:"deepseek-chat"},
  openai:{baseUrl:"https://api.openai.com/v1", model:"gpt-4o-mini"},
  custom:{baseUrl:"", model:""}
};

/* ---------- 模型池 ---------- */
let POOL = {active: "", providers: []};

function poolIndexOf(id){ return POOL.providers.findIndex(p=>p.id===id); }
function poolCurrent(){
  const i = poolIndexOf(POOL.active);
  return i >= 0 ? POOL.providers[i] : null;
}
function renderPoolSelect(){
  const sel = document.getElementById("cfgActive");
  sel.innerHTML = POOL.providers.map(p=>
    '<option value="'+esc(p.id)+'">'+esc(p.name || p.model || p.baseUrl || "未命名")+'</option>').join("")
    || '<option value="">（空，点「＋ 新增」）</option>';
  if(poolCurrent()) sel.value = POOL.active;
}
function fillPoolFields(){
  const p = poolCurrent();
  document.getElementById("cfgName").value  = p ? (p.name || "") : "";
  document.getElementById("cfgBase").value  = p ? (p.baseUrl || "") : "";
  document.getElementById("cfgModel").value = p ? (p.model || "") : "";
  const key = document.getElementById("cfgKey");
  key.value = "";
  key.placeholder = p && p.hasKey ? "已保存，留空不改" : "sk-…";
  const del = document.getElementById("cfgDel");
  del.disabled = POOL.providers.length === 0;
}
function stashFields(){
  const p = poolCurrent();
  if(!p) return;
  p.name = document.getElementById("cfgName").value.trim();
  p.baseUrl = document.getElementById("cfgBase").value.trim();
  p.model = document.getElementById("cfgModel").value.trim();
  const k = document.getElementById("cfgKey").value.trim();
  if(k) p.apiKey = k;
}

/* ---------- 全局快捷键（唤起日程 / 再按一次收进托盘） ---------- */
const hkKeys = document.getElementById("hkKeys");
const hkHint = document.getElementById("hkHint");
let hkCapture = false, hkPaused = false;

function hkState(s){
  if(!s.supported){ hkHint.textContent = "当前系统不支持全局快捷键（仅 Windows 可用）"; return; }
  if(s.paused){ hkHint.textContent = "已暂停注册（录制中），保存后恢复"; return; }
  if(s.enabled) hkHint.textContent = "已生效：" + s.keys + "（按一下唤起独立日程窗口并回到顶部，再按一下收进托盘）";
  else hkHint.textContent = "当前未生效：" + (s.error || "未知原因");
}
function hkLoad(){
  if(!syncEligible()){ hkHint.textContent = "需要先启动 serve.py"; return; }
  fetch("/api/hotkey").then(r=>r.json()).then(s=>{
    hkKeys.value = s.keys || "";
    hkState(s);
  }).catch(()=>{ hkHint.textContent = "读取失败，确认 serve.py 在运行"; });
}
function hkPost(payload){
  return fetch("/api/hotkey", {method:"POST", headers:{"Content-Type":"application/json"},
                                body: JSON.stringify(payload)})
    .then(r=>r.json().then(d=>({ok:r.ok, d:d})));
}
document.getElementById("hkRec").onclick = ()=>{
  hkCapture = true;
  hkKeys.placeholder = "按下组合键（如 Alt+S），Esc 取消";
  hkKeys.focus();
  /* 录制期间先取消系统注册，否则当前这个组合键会被系统吃掉，录不到 */
  hkPost({pause:true}).then(({d})=>{ hkPaused = true; hkState(d || {}); }).catch(()=>{});
};
hkKeys.addEventListener("keydown", e=>{
  e.preventDefault();
  if(!hkCapture) return;
  if(e.key === "Escape"){ hkCapture = false; hkKeys.placeholder = "Alt+S"; return; }
  const mods = [];
  if(e.ctrlKey) mods.push("Ctrl");
  if(e.altKey) mods.push("Alt");
  if(e.shiftKey) mods.push("Shift");
  if(e.metaKey) mods.push("Win");
  if(["Control","Alt","Shift","Meta","OS","CapsLock","AltGraph"].indexOf(e.key) >= 0) return;
  let key = e.key;
  if(key === " ") key = "Space";
  else if(key.length === 1) key = key.toUpperCase();
  if(!mods.length){ toast("要带上 Ctrl / Alt / Shift / Win 里的至少一个"); return; }
  hkKeys.value = mods.join("+") + "+" + key;
  hkCapture = false;
  hkKeys.placeholder = "Alt+S";
});
document.getElementById("hkSave").onclick = ()=>{
  const keys = hkKeys.value.trim();
  if(!keys){ toast("先点「录制」设一个组合键"); return; }
  hkPost({keys:keys}).then(({ok, d})=>{
    hkPaused = false;
    if(!ok || d.error){ hkHint.textContent = d.error || "保存失败"; toast(d.error || "保存失败"); return; }
    hkState(d);
    toast("快捷键已设为 " + keys);
  }).catch(()=>{ hkHint.textContent = "保存失败，确认 serve.py 在运行"; });
};
/* 关掉设置面板时，如果还停在"已暂停"状态，把系统注册恢复回去 */
MASK_ON_CLOSE["maskCfg"] = ()=>{
  if(!hkPaused) return;
  hkPaused = false;
  hkPost({resume:true}).catch(()=>{});
};

document.getElementById("chatcfg").onclick = ()=>{
  if(!syncEligible()){ addMsg("err", "需要先启动 serve.py"); return; }
  fetch("/api/config").then(r=>r.json()).then(c=>{
    POOL = {active: c.active || "", providers: (c.providers || []).map(p=>Object.assign({}, p))};
    renderPoolSelect();
    fillPoolFields();
    hkLoad();
    maskCfg.classList.add("on");
  }).catch(()=>addMsg("err", "读取配置失败"));
};
document.getElementById("cfgActive").addEventListener("change", e=>{
  stashFields();
  POOL.active = e.target.value;
  fillPoolFields();
});
document.getElementById("cfgAdd").onclick = ()=>{
  stashFields();
  const id = "p" + Date.now();
  POOL.providers.push({id:id, name:"新模型", baseUrl:"https://api.deepseek.com/v1", model:"deepseek-chat", apiKey:"", hasKey:false});
  POOL.active = id;
  renderPoolSelect();
  fillPoolFields();
  document.getElementById("cfgName").focus();
};
document.getElementById("cfgDel").onclick = ()=>{
  const i = poolIndexOf(POOL.active);
  if(i < 0) return;
  POOL.providers.splice(i, 1);
  POOL.active = POOL.providers.length ? POOL.providers[0].id : "";
  renderPoolSelect();
  fillPoolFields();
};
document.getElementById("cfgCancel").onclick = ()=>maskCfg.classList.remove("on");
document.getElementById("cfgSave").onclick = (e)=>{
  e.preventDefault();
  stashFields();
  const payload = {
    active: POOL.active,
    providers: POOL.providers.map(p=>({
      id: p.id, name: p.name || "", baseUrl: p.baseUrl || "",
      model: p.model || "",
      apiKey: p.apiKey || ""            // 空串表示沿用服务端已存的 Key
    }))
  };
  fetch("/api/config", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(payload)})
    .then(r=>r.json())
    .then(()=>{ maskCfg.classList.remove("on"); toast("模型池已保存"); })
    .catch(()=>addMsg("err", "保存失败，确认 serve.py 在运行"));
};
/* 示例版（构建时带 BAKED_ANCHOR）：把示例数据整体平移到看的人「今天」，
   这样别人什么时候下载都能看到内容，而不是一个空白的日子。 */
if(typeof BAKED_ANCHOR !== "undefined" && BAKED_ANCHOR){
  try{
    const delta = Math.round((parseKey(key(TODAY)) - parseKey(BAKED_ANCHOR)) / 86400000);
    if(delta){
      const moved = {};
      Object.keys(BAKED).forEach(k=>{
        const d = parseKey(k); d.setDate(d.getDate() + delta); moved[key(d)] = BAKED[k];
      });
      Object.keys(BAKED).forEach(k=>{ delete BAKED[k]; });
      Object.assign(BAKED, moved);
      DDL.forEach(d=>{
        if(!d.date) return;
        const t = parseKey(d.date); t.setDate(t.getDate() + delta);
        d.date = key(t);
      });
    }
  }catch(e){}
}

/* ---------------- 快捷键唤起：页面滚回最上方 ----------------
   服务端把日程窗口唤起时会发一个通知，这里收到就把页面拉回顶部。 */
(function bindNotice(){
  if(!syncEligible()) return;
  let lastSeq = null, lastReload = null;
  function scrollTop(){
    try{
      window.scrollTo(0, 0);
      ["main","rbody","lbody","slist","strip"].forEach(id=>{
        const el = document.getElementById(id);
        if(el && el.scrollTop) el.scrollTop = 0;
      });
    }catch(e){}
  }
  function loop(){
    fetch("/api/notice?since="+(lastSeq === null ? 0 : lastSeq), {cache:"no-store"})
      .then(r=>r.json())
      .then(d=>{
        if(lastSeq === null){                 /* 刚打开的页面记下当前状态，不触发刷新 */
          lastSeq = d.seq; lastReload = d.reload || 0;
        }else{
          if(d.seq !== lastSeq){ lastSeq = d.seq; scrollTop(); }
          /* 服务端说前端代码换了 → 自己刷新，免得一直跑着旧版本 */
          if(d.reload && d.reload !== lastReload){
            lastReload = d.reload;
            if(!editingInFlight()) location.reload();
            else toast("页面已更新，改完手头的东西会自动刷新");
          }
        }
        loop();
      })
      .catch(()=>setTimeout(loop, 3000));
  }
  loop();
})();

applyUI();
fillQuickLinks();
render();
syncLoad();
syncLoadPlan();

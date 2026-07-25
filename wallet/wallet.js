/* wallet.js — Larz Wallet app logic. Non-custodial: the private key is
   generated here, encrypted with your PIN, stored only in localStorage, and
   used to sign transactions locally. It is never sent to any server. */
"use strict";
const C = LarzCrypto;
const COIN = 100000000;
const DEFAULT_NODE = (location.origin.startsWith("http") ? location.origin : "https://larzos.com") + "/larzchain/rpc";
const LS = { enc: "larzwallet.enc", node: "larzwallet.node" };

let WALLET = { priv: null, address: null };
let PENDING = null;   // {priv, address} awaiting PIN during onboarding

/* ---------- small helpers ---------- */
const $ = id => document.getElementById(id);
const enc = new TextEncoder();
const b64 = b => btoa(String.fromCharCode.apply(null, new Uint8Array(b)));
const unb64 = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));
function nodeUrl(){ return localStorage.getItem(LS.node) || DEFAULT_NODE; }
function larz(sparks){ return (sparks / COIN).toLocaleString(undefined,{maximumFractionDigits:8}); }
function toast(msg){ const t=$("toast"); t.textContent=msg; t.classList.add("on");
  clearTimeout(toast._t); toast._t=setTimeout(()=>t.classList.remove("on"),1800); }

/* ---------- PIN-based encryption (PBKDF2 + AES-GCM via WebCrypto) ---------- */
async function deriveKey(pin, salt){
  const base = await crypto.subtle.importKey("raw", enc.encode(pin), "PBKDF2", false, ["deriveKey"]);
  return crypto.subtle.deriveKey(
    {name:"PBKDF2", salt, iterations:150000, hash:"SHA-256"},
    base, {name:"AES-GCM", length:256}, false, ["encrypt","decrypt"]);
}
async function encryptKey(privHex, pin){
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const key = await deriveKey(pin, salt);
  const ct = await crypto.subtle.encrypt({name:"AES-GCM", iv}, key, enc.encode(privHex));
  return { salt:b64(salt), iv:b64(iv), ct:b64(ct), addr:PENDING.address };
}
async function decryptKey(blob, pin){
  const key = await deriveKey(pin, unb64(blob.salt));
  const pt = await crypto.subtle.decrypt({name:"AES-GCM", iv:unb64(blob.iv)}, key, unb64(blob.ct));
  return new TextDecoder().decode(pt);
}

/* ---------- node API ---------- */
async function api(path, opts){
  const r = await fetch(nodeUrl()+path, opts);
  if(!r.ok) throw new Error("node "+r.status);
  return r.json();
}
async function refreshBalance(){
  try{
    const d = await api("/utxos/"+WALLET.address);
    $("balamt").textContent = larz(d.balance);
    $("sendavail").textContent = larz(d.balance);
    $("netdot").textContent = "● online";
    return d;
  }catch(e){ $("netdot").textContent = "● offline"; throw e; }
}
async function loadHistory(elId){
  const el = $(elId);
  try{
    const d = await api("/history/"+WALLET.address);
    if(!d.history.length){ el.innerHTML = '<li class="small">No activity yet.</li>'; return; }
    el.innerHTML = d.history.map(h =>
      `<li><div><b>${h.coinbase?"Mining reward":"Received"}</b>
       <div class="sub">block #${h.height}</div></div>
       <div class="pos">+${larz(h.amount)} LARZ</div></li>`).join("");
  }catch(e){ el.innerHTML = '<li class="small">Could not reach the node.</li>'; }
}

/* ---------- transaction building (client-side sign) ---------- */
async function buildAndSend(toAddr, amountSparks){
  const d = await api("/utxos/"+WALLET.address);
  const utxos = d.utxos.slice().sort((a,b)=>b.amount-a.amount);
  let picked=[], sum=0;
  for(const u of utxos){ picked.push(u); sum+=u.amount; if(sum>=amountSparks) break; }
  if(sum < amountSparks) throw new Error("Insufficient funds");
  const inputs = picked.map(u=>({txid:u.txid, index:u.index}));
  const outputs = [{address:toAddr, amount:amountSparks}];
  const change = sum - amountSparks;
  if(change>0) outputs.push({address:WALLET.address, amount:change});
  const tx = {inputs, outputs, is_coinbase:false, note:""};
  C.signTx(tx, picked.map(()=>WALLET.priv));           // sign locally with our key
  const res = await api("/tx", {method:"POST", headers:{"Content-Type":"application/json"},
                                body: JSON.stringify(txToDict(tx))});
  if(!res.accepted) throw new Error("Rejected by node (inputs may be unconfirmed)");
  return C.txid(tx);
}
function txToDict(tx){
  return {inputs: tx.inputs.map(i=>({txid:i.txid,index:i.index,pubkey:i.pubkey,signature:i.signature})),
          outputs: tx.outputs.map(o=>({address:o.address,amount:o.amount})),
          is_coinbase:false, note:tx.note||""};
}

/* ---------- PIN widget ---------- */
function buildPin(containerId){
  const c = $(containerId); c.innerHTML="";
  for(let i=0;i<4;i++){ const inp=document.createElement("input");
    inp.type="tel"; inp.maxLength=1; inp.inputMode="numeric"; inp.autocomplete="off";
    inp.oninput=()=>{ if(inp.value && inp.nextSibling) inp.nextSibling.focus(); };
    inp.onkeydown=e=>{ if(e.key==="Backspace"&&!inp.value&&inp.previousSibling) inp.previousSibling.focus(); };
    c.appendChild(inp); }
}
function readPin(containerId){ return Array.from($(containerId).children).map(i=>i.value).join(""); }

/* ---------- UI controller ---------- */
const UI = {
  show(name){
    document.querySelectorAll(".screen").forEach(s=>s.classList.remove("on"));
    $("s-"+name).classList.add("on");
    const walletScreens = ["home","send","receive","history","settings"];
    $("tabbar").style.display = walletScreens.includes(name) ? "flex" : "none";
    document.querySelectorAll(".tabbar a").forEach(a=>a.classList.toggle("on", a.dataset.tab===name));
    if(name==="home"){ $("homeaddr").textContent=WALLET.address; refreshBalance().catch(()=>{}); loadHistory("homehist"); }
    if(name==="receive"){ $("recvaddr").textContent=WALLET.address; }
    if(name==="history"){ loadHistory("fullhist"); }
    if(name==="send"){ $("senderr").textContent=""; $("sendto").value=""; $("sendamt").value=""; refreshBalance().catch(()=>{}); }
    if(name==="settings"){ $("nodeurl").value=nodeUrl(); $("revealed").style.display="none"; }
    if(name==="setpin"){ buildPin("pinset"); }
    if(name==="unlock"){ buildPin("pinunlock"); $("unlockerr").textContent=""; }
  },
  createFlow(){
    const priv = C.genPrivkey();
    const privHex = priv.toString(16).padStart(64,"0");
    const address = C.pubToAddress(C.privToPub(priv));
    PENDING = { priv, privHex, address };
    $("newkey").textContent = privHex;
    $("backedup").checked=false; $("createnext").disabled=true;
    this.show("create");
  },
  importFlow(){
    const hex = ($("impkey").value||"").trim().toLowerCase().replace(/^0x/,"");
    if(!/^[0-9a-f]{64}$/.test(hex)){ toast("Enter a 64-character hex key"); return; }
    const priv = BigInt("0x"+hex);
    if(priv<1n || priv>=C.N){ toast("Invalid key"); return; }
    const address = C.pubToAddress(C.privToPub(priv));
    PENDING = { priv, privHex:hex, address };
    this.show("setpin");
  },
  async setPinFlow(){
    const pin = readPin("pinset");
    if(!/^\d{4}$/.test(pin)){ toast("Enter a 4-digit PIN"); return; }
    const blob = await encryptKey(PENDING.privHex, pin);
    localStorage.setItem(LS.enc, JSON.stringify(blob));
    WALLET = { priv:PENDING.priv, address:PENDING.address };
    PENDING = null;
    toast("Wallet ready");
    this.show("home");
  },
  async unlockFlow(){
    const pin = readPin("pinunlock");
    const blob = JSON.parse(localStorage.getItem(LS.enc));
    try{
      const hex = await decryptKey(blob, pin);
      WALLET = { priv:BigInt("0x"+hex), address:blob.addr };
      this.show("home");
    }catch(e){ $("unlockerr").textContent="Wrong PIN. Try again."; buildPin("pinunlock"); }
  },
  async sendFlow(){
    $("senderr").textContent="";
    const to = ($("sendto").value||"").trim();
    const amt = parseFloat($("sendamt").value||"0");
    if(!to.startsWith("L")||to.length<26){ $("senderr").textContent="Enter a valid L… address"; return; }
    if(!(amt>0)){ $("senderr").textContent="Enter an amount"; return; }
    const sparks = Math.round(amt*COIN);
    if(!confirm("Send "+amt+" LARZ to\n"+to+" ?")) return;
    $("sendbtn").disabled=true; $("sendbtn").textContent="Sending…";
    try{
      const txid = await buildAndSend(to, sparks);
      toast("Sent! Confirms next block");
      this.show("home");
    }catch(e){ $("senderr").textContent=e.message; }
    $("sendbtn").disabled=false; $("sendbtn").textContent="Review & send";
  },
  async faucet(){
    const b=$("faucetbtn"); b.disabled=true; b.textContent="Requesting…";
    try{ const r=await api("/faucet/"+WALLET.address);
      if(r.sent){ toast("Test LARZ sent! Confirms next block"); setTimeout(()=>refreshBalance().catch(()=>{}),4000); }
      else toast(r.error==="rate limited" ? "Already claimed — try again later" : (r.error||"Faucet unavailable")); }
    catch(e){ toast("Faucet unreachable"); }
    b.disabled=false; b.textContent="Get test LARZ (faucet)";
  },
  copy(text,msg){ navigator.clipboard?.writeText(text).then(()=>toast(msg||"Copied"),()=>toast("Copy failed")); },
  shareAddr(){ if(navigator.share) navigator.share({title:"My LarzCoin address", text:WALLET.address});
    else this.copy(WALLET.address,"Address copied"); },
  saveNode(){ const u=($("nodeurl").value||"").trim().replace(/\/$/,""); localStorage.setItem(LS.node,u); toast("Node saved"); refreshBalance().catch(()=>{}); },
  async exportKey(){
    const pin = prompt("Enter your PIN to reveal the private key");
    if(!pin) return;
    try{ const hex = await decryptKey(JSON.parse(localStorage.getItem(LS.enc)), pin);
      const el=$("revealed"); el.textContent=hex; el.style.display="block";
      toast("Never share this key"); }
    catch(e){ toast("Wrong PIN"); }
  },
  resetFlow(){
    if(!confirm("Remove this wallet from the device? Make sure your private key is backed up — this cannot be undone.")) return;
    localStorage.removeItem(LS.enc);
    WALLET={priv:null,address:null};
    this.show("onboard");
  }
};
window.UI = UI; window.WALLET = WALLET;

/* enable "Continue" only after backup confirmed */
document.addEventListener("change", e=>{ if(e.target.id==="backedup") $("createnext").disabled=!e.target.checked; });

/* boot: locked wallet -> unlock; else onboarding */
(function boot(){
  if(localStorage.getItem(LS.enc)) UI.show("unlock");
  else UI.show("onboard");
})();

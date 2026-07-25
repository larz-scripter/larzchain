/* larzwallet_crypto.js — LarzCoin client-side crypto (pure JS, BigInt).
   Mirrors larzchain/crypto.py + tx.py so JS-signed transactions verify on the
   Python node. Runs identically in a browser WebView and in Node (for testing). */
(function (root) {
"use strict";

/* ---------- SHA-256 (pure JS) ---------- */
function sha256(bytes) {
  const K = [0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
  let h=[0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
  const l=bytes.length, bl=l*8;
  const withOne=l+1; let k=(56-withOne%64+64)%64;
  const total=withOne+k+8; const m=new Uint8Array(total);
  m.set(bytes); m[l]=0x80;
  const hi=Math.floor(bl/0x100000000), lo=bl>>>0;
  m[total-8]=(hi>>>24)&255;m[total-7]=(hi>>>16)&255;m[total-6]=(hi>>>8)&255;m[total-5]=hi&255;
  m[total-4]=(lo>>>24)&255;m[total-3]=(lo>>>16)&255;m[total-2]=(lo>>>8)&255;m[total-1]=lo&255;
  const rotr=(x,n)=>(x>>>n)|(x<<(32-n));
  const w=new Uint32Array(64);
  for(let i=0;i<total;i+=64){
    for(let t=0;t<16;t++) w[t]=(m[i+t*4]<<24)|(m[i+t*4+1]<<16)|(m[i+t*4+2]<<8)|m[i+t*4+3];
    for(let t=16;t<64;t++){const s0=rotr(w[t-15],7)^rotr(w[t-15],18)^(w[t-15]>>>3);
      const s1=rotr(w[t-2],17)^rotr(w[t-2],19)^(w[t-2]>>>10);
      w[t]=(w[t-16]+s0+w[t-7]+s1)|0;}
    let [a,b,c,d,e,f,g,hh]=h;
    for(let t=0;t<64;t++){const S1=rotr(e,6)^rotr(e,11)^rotr(e,25);
      const ch=(e&f)^(~e&g);const t1=(hh+S1+ch+K[t]+w[t])|0;
      const S0=rotr(a,2)^rotr(a,13)^rotr(a,22);const maj=(a&b)^(a&c)^(b&c);
      const t2=(S0+maj)|0;hh=g;g=f;f=e;e=(d+t1)|0;d=c;c=b;b=a;a=(t1+t2)|0;}
    h[0]=(h[0]+a)|0;h[1]=(h[1]+b)|0;h[2]=(h[2]+c)|0;h[3]=(h[3]+d)|0;
    h[4]=(h[4]+e)|0;h[5]=(h[5]+f)|0;h[6]=(h[6]+g)|0;h[7]=(h[7]+hh)|0;
  }
  const out=new Uint8Array(32);
  for(let i=0;i<8;i++){out[i*4]=(h[i]>>>24)&255;out[i*4+1]=(h[i]>>>16)&255;out[i*4+2]=(h[i]>>>8)&255;out[i*4+3]=h[i]&255;}
  return out;
}
function sha256d(b){return sha256(sha256(b));}

/* ---------- RIPEMD-160 (pure JS) ---------- */
function ripemd160(data){
  const rol=(x,n)=>((x<<n)|(x>>>(32-n)))>>>0;
  const zl=[0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,7,4,13,1,10,6,15,3,12,0,9,5,2,14,11,8,
    3,10,14,4,9,15,8,1,2,7,0,6,13,11,5,12,1,9,11,10,0,8,12,4,13,3,7,15,14,5,6,2,
    4,0,5,9,7,12,2,10,14,1,3,8,11,6,15,13];
  const zr=[5,14,7,0,9,2,11,4,13,6,15,8,1,10,3,12,6,11,3,7,0,13,5,10,14,15,8,12,4,9,1,2,
    15,5,1,3,7,14,6,9,11,8,12,2,10,0,4,13,8,6,4,1,3,11,15,0,5,12,2,13,9,7,10,14,
    12,15,10,4,1,5,8,7,6,2,13,14,0,3,9,11];
  const sl=[11,14,15,12,5,8,7,9,11,13,14,15,6,7,9,8,7,6,8,13,11,9,7,15,7,12,15,9,11,7,13,12,
    11,13,6,7,14,9,13,15,14,8,13,6,5,12,7,5,11,12,14,15,14,15,9,8,9,14,5,6,8,6,5,12,
    9,15,5,11,6,8,13,12,5,12,13,14,11,8,5,6];
  const sr=[8,9,9,11,13,15,15,5,7,7,8,11,14,14,12,6,9,13,15,7,12,8,9,11,7,7,12,7,6,15,13,11,
    9,7,15,11,8,6,6,14,12,13,5,14,13,13,7,5,15,5,8,11,14,14,6,14,6,9,12,9,12,5,15,8,
    8,5,12,9,12,5,14,6,8,13,6,5,15,13,11,11];
  const hl=[0x00000000,0x5a827999,0x6ed9eba1,0x8f1bbcdc,0xa953fd4e];
  const hr=[0x50a28be6,0x5c4dd124,0x6d703ef3,0x7a6d76e9,0x00000000];
  const f=(j,x,y,z)=>j<16?(x^y^z):j<32?((x&y)|(~x&z)):j<48?((x|~y)^z):j<64?((x&z)|(y&~z)):(x^(y|~z));
  const l=data.length; const withOne=l+1; let k=(56-withOne%64+64)%64;
  const total=withOne+k+8; const m=new Uint8Array(total);
  m.set(data); m[l]=0x80;
  const bl=l*8; const lo=bl>>>0, hi=Math.floor(bl/0x100000000);
  m[total-8]=lo&255;m[total-7]=(lo>>>8)&255;m[total-6]=(lo>>>16)&255;m[total-5]=(lo>>>24)&255;
  m[total-4]=hi&255;m[total-3]=(hi>>>8)&255;m[total-2]=(hi>>>16)&255;m[total-1]=(hi>>>24)&255;
  let h0=0x67452301,h1=0xefcdab89,h2=0x98badcfe,h3=0x10325476,h4=0xc3d2e1f0;
  const X=new Int32Array(16);
  for(let i=0;i<total;i+=64){
    for(let j=0;j<16;j++) X[j]=(m[i+j*4])|(m[i+j*4+1]<<8)|(m[i+j*4+2]<<16)|(m[i+j*4+3]<<24);
    let al=h0,bl_=h1,cl=h2,dl=h3,el=h4,ar=h0,br=h1,cr=h2,dr=h3,er=h4;
    for(let j=0;j<80;j++){
      let t=(al+f(j,bl_,cl,dl)+X[zl[j]]+hl[(j/16)|0])|0; t=(rol(t>>>0,sl[j])+el)|0;
      al=el;el=dl;dl=rol(cl>>>0,10);cl=bl_;bl_=t;
      t=(ar+f(79-j,br,cr,dr)+X[zr[j]]+hr[(j/16)|0])|0; t=(rol(t>>>0,sr[j])+er)|0;
      ar=er;er=dr;dr=rol(cr>>>0,10);cr=br;br=t;
    }
    const tmp=(h1+cl+dr)|0; h1=(h2+dl+er)|0; h2=(h3+el+ar)|0; h3=(h4+al+br)|0; h4=(h0+bl_+cr)|0; h0=tmp;
  }
  const out=new Uint8Array(20); const hs=[h0,h1,h2,h3,h4];
  for(let i=0;i<5;i++){out[i*4]=hs[i]&255;out[i*4+1]=(hs[i]>>>8)&255;out[i*4+2]=(hs[i]>>>16)&255;out[i*4+3]=(hs[i]>>>24)&255;}
  return out;
}

/* ---------- HMAC-SHA256 ---------- */
function hmacSha256(key,msg){
  const B=64; if(key.length>B) key=sha256(key);
  const pad=new Uint8Array(B); pad.set(key);
  const ipad=new Uint8Array(B), opad=new Uint8Array(B);
  for(let i=0;i<B;i++){ipad[i]=pad[i]^0x36;opad[i]=pad[i]^0x5c;}
  return sha256(concat(opad,sha256(concat(ipad,msg))));
}

/* ---------- helpers ---------- */
function concat(){const a=[].slice.call(arguments);let n=0;a.forEach(x=>n+=x.length);
  const o=new Uint8Array(n);let p=0;a.forEach(x=>{o.set(x,p);p+=x.length;});return o;}
function hexToBytes(h){const o=new Uint8Array(h.length/2);for(let i=0;i<o.length;i++)o[i]=parseInt(h.substr(i*2,2),16);return o;}
function bytesToHex(b){let s="";for(let i=0;i<b.length;i++)s+=b[i].toString(16).padStart(2,"0");return s;}
function bytesToBig(b){let x=0n;for(let i=0;i<b.length;i++)x=(x<<8n)|BigInt(b[i]);return x;}
function bigToBytes(x,len){const o=new Uint8Array(len);for(let i=len-1;i>=0;i--){o[i]=Number(x&255n);x>>=8n;}return o;}
function utf8(s){const o=[];for(const ch of s){let c=ch.codePointAt(0);
  if(c<128)o.push(c);else if(c<2048){o.push(192|(c>>6),128|(c&63));}
  else if(c<65536){o.push(224|(c>>12),128|((c>>6)&63),128|(c&63));}
  else{o.push(240|(c>>18),128|((c>>12)&63),128|((c>>6)&63),128|(c&63));}}
  return new Uint8Array(o);}

/* ---------- secp256k1 ---------- */
const P=0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2Fn;
const N=0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141n;
const Gx=0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798n;
const Gy=0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8n;
const G=[Gx,Gy];
const ADDRESS_VERSION=0x30;
function mod(a,m){return ((a%m)+m)%m;}
function invMod(a,m){a=mod(a,m);let [lm,hm]=[1n,0n],[low,high]=[a,m];
  while(low>1n){const r=high/low;[lm,hm]=[hm-lm*r,lm];[low,high]=[high-low*r,low];}return mod(lm,m);}
function ptAdd(p,q){if(!p)return q;if(!q)return p;const [x1,y1]=p,[x2,y2]=q;
  if(x1===x2&&mod(y1+y2,P)===0n)return null;let m;
  if(x1===x2&&y1===y2)m=mod((3n*x1*x1)*invMod(2n*y1,P),P);
  else m=mod((y2-y1)*invMod(mod(x2-x1,P),P),P);
  const x3=mod(m*m-x1-x2,P),y3=mod(m*(x1-x3)-y1,P);return [x3,y3];}
function ptMul(k,pt){pt=pt||G;let r=null,a=pt;while(k>0n){if(k&1n)r=ptAdd(r,a);a=ptAdd(a,a);k>>=1n;}return r;}
function privToPub(priv){return ptMul(priv,G);}
function compressPub(pt){const [x,y]=pt;const prefix=(y%2n===0n)?0x02:0x03;return concat(new Uint8Array([prefix]),bigToBytes(x,32));}
function hash160(b){return ripemd160(sha256(b));}

/* base58check */
const B58="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
function b58encode(bytes){let x=bytesToBig(bytes),out="";while(x>0n){const r=Number(x%58n);out=B58[r]+out;x/=58n;}
  for(let i=0;i<bytes.length&&bytes[i]===0;i++)out=B58[0]+out;return out;}
function b58checkEncode(version,payload){const data=concat(new Uint8Array([version]),payload);
  return b58encode(concat(data,sha256d(data).slice(0,4)));}
function pubToAddress(pt){return b58checkEncode(ADDRESS_VERSION,hash160(compressPub(pt)));}

/* RFC6979 deterministic k */
function rfc6979k(h1,priv){let v=new Uint8Array(32).fill(1),k=new Uint8Array(32);
  const x=bigToBytes(priv,32);
  k=hmacSha256(k,concat(v,new Uint8Array([0]),x,h1));v=hmacSha256(k,v);
  k=hmacSha256(k,concat(v,new Uint8Array([1]),x,h1));v=hmacSha256(k,v);
  while(true){v=hmacSha256(k,v);const c=bytesToBig(v);if(c>=1n&&c<N)return c;
    k=hmacSha256(k,concat(v,new Uint8Array([0])));v=hmacSha256(k,v);}}
function signHash(msgHash,priv){const z=bytesToBig(msgHash);
  while(true){const k=rfc6979k(msgHash,priv);const [x]=ptMul(k,G);const r=mod(x,N);if(r===0n)continue;
    let s=mod(invMod(k,N)*(z+r*priv),N);if(s===0n)continue;if(s>N/2n)s=N-s;
    return concat(bigToBytes(r,32),bigToBytes(s,32));}}

/* ---------- canonical LarzChain tx (matches Python json.dumps sort_keys) ---------- */
function jstr(s){return JSON.stringify(s);}   // matches Python json string escaping for ASCII
function canonicalTx(tx,includeSig){
  const ins=tx.inputs.map(i=>includeSig
    ? '{"index":'+i.index+',"pubkey":'+(i.pubkey?jstr(i.pubkey):'null')+',"signature":'+(i.signature?jstr(i.signature):'null')+',"txid":'+jstr(i.txid)+'}'
    : '{"index":'+i.index+',"txid":'+jstr(i.txid)+'}').join(',');
  const outs=tx.outputs.map(o=>'{"address":'+jstr(o.address)+',"amount":'+o.amount+'}').join(',');
  return '{"inputs":['+ins+'],"is_coinbase":'+(tx.is_coinbase?'true':'false')+',"note":'+jstr(tx.note||"")+',"outputs":['+outs+']}';
}
function sighash(tx){return sha256d(utf8(canonicalTx(tx,false)));}
function txid(tx){return bytesToHex(sha256d(utf8(canonicalTx(tx,true))));}
function signTx(tx,privkeys){const h=sighash(tx);
  tx.inputs.forEach((inp,i)=>{const priv=privkeys[i];const pub=privToPub(priv);
    inp.pubkey=bytesToHex(compressPub(pub));inp.signature=bytesToHex(signHash(h,priv));});
  return tx;}

/* ---------- key generation ---------- */
function randBytes(n){const b=new Uint8Array(n);
  if(root.crypto&&root.crypto.getRandomValues)root.crypto.getRandomValues(b);
  else{const c=require("crypto");c.randomFillSync(b);}return b;}
function genPrivkey(){while(true){const k=bytesToBig(randBytes(32));if(k>=1n&&k<N)return k;}}

const API={sha256,sha256d,ripemd160,hmacSha256,hexToBytes,bytesToHex,bytesToBig,bigToBytes,utf8,
  privToPub,compressPub,pubToAddress,hash160,b58checkEncode,signHash,rfc6979k,
  canonicalTx,sighash,txid,signTx,genPrivkey,N,P,G};
if(typeof module!=="undefined"&&module.exports)module.exports=API;
root.LarzCrypto=API;
})(typeof self!=="undefined"?self:this);

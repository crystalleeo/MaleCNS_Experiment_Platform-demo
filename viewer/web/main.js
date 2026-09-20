import * as THREE from './vendor/three.module.js';
import { OrbitControls } from './vendor/OrbitControls.js';

const container = document.getElementById('app');
const statusEl = document.getElementById('status');
statusEl.textContent = 'V5 main.js parsed';

function setStatus(s, bad=false){
  statusEl.textContent=s;
  statusEl.style.color=bad ? '#ff8f8f' : '#cbd7e4';
  statusEl.style.maxWidth='65vw';
  statusEl.style.whiteSpace='normal';
}

window.addEventListener('error', e=>{
  setStatus('JS ERROR · '+(e.message||String(e.error||e)), true);
});
window.addEventListener('unhandledrejection', e=>{
  setStatus('PROMISE ERROR · '+(e.reason?.message||String(e.reason)), true);
});

async function fetchChecked(url, kind='arrayBuffer', timeoutMs=90000){
  setStatus('loading · '+url.split('/').pop());
  const ctrl=new AbortController();
  const timer=setTimeout(()=>ctrl.abort(),timeoutMs);
  try{
    const r=await fetch(url,{cache:'no-store',signal:ctrl.signal});
    if(!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
    return kind==='json' ? await r.json() : await r.arrayBuffer();
  } finally {
    clearTimeout(timer);
  }
}

const scene=new THREE.Scene();
scene.background=new THREE.Color(0x020407);
scene.fog=new THREE.FogExp2(0x020407,0.0011);

const camera=new THREE.PerspectiveCamera(42,innerWidth/innerHeight,0.1,8000);
camera.position.set(0,-520,220);

const renderer=new THREE.WebGLRenderer({
  antialias:true,
  alpha:false,
  powerPreference:'high-performance'
});
renderer.setPixelRatio(Math.min(devicePixelRatio,2));
renderer.setSize(innerWidth,innerHeight);
renderer.outputColorSpace=THREE.SRGBColorSpace;
container.appendChild(renderer.domElement);

const controls=new OrbitControls(camera,renderer.domElement);
controls.enableDamping=true;
controls.dampingFactor=.07;
controls.rotateSpeed=.55;
controls.zoomSpeed=.75;
controls.panSpeed=.65;

scene.add(new THREE.HemisphereLight(0xbcd8ff,0x14202b,1.35));
const dl=new THREE.DirectionalLight(0xffffff,2.2);
dl.position.set(-2,-3,4);
scene.add(dl);

const shellMats=[];
let activity=null, vertexNeuron=null, actAttr=null, bodyIds=[], bodyToIdx=new Map();
let neuronLines=null, lastFreshFrameAt=0, neuronGain=.65;
let activityThreshold=.22;
let activeOnly=true;
let lastFrameKey=null;

function hslFromId(id){
  const h=((Number(id)*0.618033988749895)%1+1)%1;
  const c=new THREE.Color();
  c.setHSL(h,.80,.58);
  return c;
}

async function loadMesh(url){
  const ab=await fetchChecked(url,'arrayBuffer');
  const dv=new DataView(ab);
  const magic=String.fromCharCode(...new Uint8Array(ab,0,4));
  if(magic!=='M5MS') throw new Error('bad mesh header: '+url);

  const nv=dv.getUint32(4,true);
  const ni=dv.getUint32(8,true);
  const expected=16+nv*12+ni*4;
  if(ab.byteLength<expected){
    throw new Error(`truncated mesh ${url}: ${ab.byteLength} < ${expected}`);
  }

  const pos=new Float32Array(ab,16,nv*3);
  const idx=new Uint32Array(ab,16+nv*12,ni);

  const g=new THREE.BufferGeometry();
  g.setAttribute('position',new THREE.BufferAttribute(pos,3));
  g.setIndex(new THREE.BufferAttribute(idx,1));
  g.computeVertexNormals();
  g.computeBoundingSphere();
  return g;
}

async function addShell(url,color,opacity){
  const g=await loadMesh(url);
  const baseColor=new THREE.Color(color);

  const m=new THREE.ShaderMaterial({
    transparent:true,
    depthWrite:false,
    depthTest:true,
    side:THREE.DoubleSide,
    blending:THREE.NormalBlending,
    uniforms:{
      uColor:{value:baseColor},
      uOpacity:{value:opacity},
      uRimStrength:{value:2.2},
      uRimPower:{value:1.8}
    },
    vertexShader:`
      varying vec3 vNormalW;
      varying vec3 vViewDirW;
      void main(){
        vec4 worldPos=modelMatrix*vec4(position,1.0);
        vNormalW=normalize(mat3(modelMatrix)*normal);
        vViewDirW=normalize(cameraPosition-worldPos.xyz);
        gl_Position=projectionMatrix*viewMatrix*worldPos;
      }`,
    fragmentShader:`
      uniform vec3 uColor;
      uniform float uOpacity;
      uniform float uRimStrength;
      uniform float uRimPower;
      varying vec3 vNormalW;
      varying vec3 vViewDirW;

      void main(){
        float facing=abs(dot(normalize(vNormalW),normalize(vViewDirW)));
        float rim=pow(clamp(1.0-facing,0.0,1.0),uRimPower);
        float alpha=clamp(
          uOpacity*0.24 + rim*uOpacity*uRimStrength,
          0.0, 0.78
        );
        vec3 col=uColor*(0.62+rim*1.15);
        gl_FragColor=vec4(col,alpha);
      }`
  });

  shellMats.push(m);
  const mesh=new THREE.Mesh(g,m);
  mesh.renderOrder=1;
  scene.add(mesh);
  return mesh;
}

async function loadNeurons(){
  const meta=await fetchChecked('./assets/neurons.json','json',30000);
  bodyIds=meta.body_ids||[];
  bodyIds.forEach((b,i)=>bodyToIdx.set(String(b),i));
  activity=new Float32Array(bodyIds.length);

  const ab=await fetchChecked('./assets/neurons_lines.bin','arrayBuffer');
  const dv=new DataView(ab);
  const magic=String.fromCharCode(...new Uint8Array(ab,0,4));
  if(magic!=='M5LN') throw new Error('bad neuron line header');

  const nv=dv.getUint32(4,true);
  const expected=16+nv*12+nv*4;
  if(ab.byteLength<expected){
    throw new Error(`truncated neurons_lines.bin: ${ab.byteLength} < ${expected}`);
  }

  const pos=new Float32Array(ab,16,nv*3);
  vertexNeuron=new Uint32Array(ab,16+nv*12,nv);

  const colors=new Float32Array(nv*3);
  const acts=new Float32Array(nv);
  const cache=bodyIds.map(hslFromId);

  for(let i=0;i<nv;i++){
    const idx=vertexNeuron[i];
    const c=cache[idx] || new THREE.Color(1,1,1);
    colors[i*3]=c.r;
    colors[i*3+1]=c.g;
    colors[i*3+2]=c.b;
  }

  const g=new THREE.BufferGeometry();
  g.setAttribute('position',new THREE.BufferAttribute(pos,3));
  g.setAttribute('aColor',new THREE.BufferAttribute(colors,3));

  actAttr=new THREE.BufferAttribute(acts,1);
  actAttr.setUsage(THREE.DynamicDrawUsage);
  g.setAttribute('aActivity',actAttr);
  g.computeBoundingSphere();

  const mat=new THREE.ShaderMaterial({
    transparent:true,
    depthWrite:false,
    blending:THREE.AdditiveBlending,
    uniforms:{
      uGain:{value:neuronGain},
      uThreshold:{value:activityThreshold},
      uActiveOnly:{value:1.0}
    },
    vertexShader:`
      attribute vec3 aColor;
      attribute float aActivity;
      varying vec3 vColor;
      varying float vActivity;

      void main(){
        vColor=aColor;
        vActivity=aActivity;
        gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);
      }`,
    fragmentShader:`
      uniform float uGain;
      uniform float uThreshold;
      uniform float uActiveOnly;
      varying vec3 vColor;
      varying float vActivity;

      void main(){
        float a=clamp(vActivity,0.0,1.0);

        if(uActiveOnly > 0.5 && a < uThreshold){
          discard;
        }

        float vis=smoothstep(uThreshold,1.0,a);
        if(uActiveOnly < 0.5){
          vis=max(vis,.10);
        }

        vec3 base=vColor*(.42*uGain)*vis;
        vec3 hot=vColor*(1.35*uGain)+vec3(.38)*a;
        float alpha=(uActiveOnly>.5) ? (.15+.83*vis) : max(.06,.90*vis);

        gl_FragColor=vec4(mix(base,hot,a),alpha);
      }`
  });

  const lines=new THREE.LineSegments(g,mat);
  lines.renderOrder=2;
  scene.add(lines);

  if(g.boundingSphere){
    const s=g.boundingSphere;
    const r=Math.max(10,s.radius);
    controls.target.copy(s.center);
    camera.position.copy(s.center).add(new THREE.Vector3(0,-r*2.1,r*.65));
    camera.near=Math.max(.1,r/1000);
    camera.far=r*12;
    camera.updateProjectionMatrix();
    controls.update();
  }

  return lines;
}

function updateActivityAttribute(){
  if(!actAttr||!vertexNeuron||!activity) return;

  const a=actAttr.array;
  for(let i=0;i<a.length;i++){
    a[i]=activity[vertexNeuron[i]];
  }
  actAttr.needsUpdate=true;
}

function decayActivity(factor=.82){
  if(!activity) return;
  for(let i=0;i<activity.length;i++){
    activity[i]*=factor;
    if(activity[i]<.01) activity[i]=0;
  }
}

function getFrameKey(obj){
  if(!obj) return null;

  const candidates=[
    obj.t_ms,
    obj.time_ms,
    obj.timestamp_ms,
    obj.frame,
    obj.frame_id,
    obj.seq,
    obj.step,
    obj.meta?.t_ms,
    obj.meta?.frame,
    obj.task?.t_ms
  ];

  for(const v of candidates){
    if(v!==undefined && v!==null){
      return String(v);
    }
  }
  return null;
}

function applyFreshFrame(obj){
  if(!activity||!obj) return false;

  const ids=obj.body_ids||obj.bodyIds||obj.ids;
  const vals=obj.values||obj.activity||obj.activities;

  if(!Array.isArray(ids)||!Array.isArray(vals)){
    return false;
  }

  // Frame-exact mode: every new frame replaces the previous activity set.
  // This prevents neurons from remaining bright just because they appeared
  // in an earlier frame.
  activity.fill(0);

  let hit=0;
  for(let j=0;j<Math.min(ids.length,vals.length);j++){
    const k=bodyToIdx.get(String(ids[j]));
    if(k!==undefined){
      activity[k]=Math.max(0,Math.min(1,Number(vals[j])||0));
      hit++;
    }
  }

  return hit>0;
}

async function pollActivity(){
  try{
    const r=await fetch('/api/activity?ts='+Date.now(),{cache:'no-store'});
    if(!r.ok) return false;

    const obj=await r.json();
    const key=getFrameKey(obj);

    // The server returns the final JSONL line until a new frame arrives.
    // Never re-apply an already-consumed frame.
    if(key!==null && key===lastFrameKey){
      return false;
    }

    if(key!==null){
      lastFrameKey=key;
    }

    const fresh=applyFreshFrame(obj);
    if(fresh){
      lastFreshFrameAt=performance.now();
    }
    return fresh;
  }catch(_){
    return false;
  }
}

function installThresholdControl(){
  const hud=document.getElementById('hud');
  if(!hud || document.getElementById('activityThreshold')) return;

  const row=document.createElement('div');
  row.className='row';
  row.id='thresholdRow';

  const label=document.createElement('label');
  label.textContent='Activation threshold';

  const input=document.createElement('input');
  input.id='activityThreshold';
  input.type='range';
  input.min='0.02';
  input.max='0.90';
  input.step='0.01';
  input.value=String(activityThreshold);

  const value=document.createElement('span');
  value.id='thresholdValue';
  value.textContent=activityThreshold.toFixed(2);

  row.appendChild(label);
  row.appendChild(input);
  row.appendChild(value);

  const activityRow=[...hud.querySelectorAll('.row')]
    .find(x=>x.textContent.includes('Activity'));

  if(activityRow){
    hud.insertBefore(row,activityRow);
  }else{
    hud.appendChild(row);
  }

  input.addEventListener('input',()=>{
    activityThreshold=Number(input.value);
    value.textContent=activityThreshold.toFixed(2);

    if(neuronLines?.material?.uniforms?.uThreshold){
      neuronLines.material.uniforms.uThreshold.value=activityThreshold;
    }
  });
}

async function boot(){
  try{
    setStatus('loading · brain_shell.bin');
    await addShell('./assets/brain_shell.bin',0xe8f4ff,.20);

    setStatus('loading · vnc_shell.bin');
    await addShell('./assets/vnc_shell.bin',0xddeefa,.18);

    setStatus('loading · neurons');
    neuronLines=await loadNeurons();

    installThresholdControl();

    setStatus(`ready · ${bodyIds.length.toLocaleString()} neurons sampled`);
  }catch(e){
    console.error(e);
    setStatus('ERROR · '+(e?.name||'Error')+' · '+(e?.message||String(e)),true);
  }
}
boot();

setInterval(async ()=>{
  const fresh=await pollActivity();

  // If there is no new frame, let the current activity disappear.
  // Therefore the final line in live.jsonl cannot keep neurons permanently lit.
  if(!fresh){
    decayActivity(.82);
  }

  updateActivityAttribute();

  if(activity&&neuronLines){
    let n=0;
    for(let i=0;i<activity.length;i++){
      if(activity[i]>=activityThreshold) n++;
    }

    const live=(performance.now()-lastFreshFrameAt)<650;
    setStatus(`${live?'LIVE':'IDLE'} · active ${n}/${activity.length} · threshold ${activityThreshold.toFixed(2)}`);
  }
},100);

const so=document.getElementById('shellOpacity');
const soTxt=document.getElementById('so');
so.value='.20';
soTxt.textContent='.20';

so.oninput=()=>{
  const v=Number(so.value);
  soTxt.textContent=v.toFixed(2);

  shellMats.forEach((m,i)=>{
    if(m.uniforms?.uOpacity){
      m.uniforms.uOpacity.value=v*(i ? .90 : 1.0);
    }
  });
};

const gain=document.getElementById('gain');
const gv=document.getElementById('gv');
gain.value='.65';
gv.textContent='.65';

gain.oninput=()=>{
  neuronGain=Number(gain.value);
  gv.textContent=neuronGain.toFixed(2);

  if(neuronLines?.material?.uniforms?.uGain){
    neuronLines.material.uniforms.uGain.value=neuronGain;
  }
};

const activeBtn=document.getElementById('demoBtn');
activeBtn.textContent='Only active';

activeBtn.onclick=()=>{
  activeOnly=!activeOnly;
  activeBtn.textContent=activeOnly ? 'Only active' : 'Show all';

  if(neuronLines?.material?.uniforms?.uActiveOnly){
    neuronLines.material.uniforms.uActiveOnly.value=activeOnly ? 1.0 : 0.0;
  }
};

const clearBtn=document.getElementById('resetBtn');
clearBtn.textContent='Clear stale';

clearBtn.onclick=()=>{
  if(activity){
    activity.fill(0);
    lastFrameKey=null;
    updateActivityAttribute();
  }
};

window.addEventListener('resize',()=>{
  camera.aspect=innerWidth/innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth,innerHeight);
});

function animate(){
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene,camera);
}
animate();


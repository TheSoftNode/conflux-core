/* CONFLUX CORE — self-contained WebGL2 3D reactor.
   All geometry and materials are procedural. No external 3D libraries or network assets.
   Multiplayer authority remains on the FastAPI server. */
(() => {
'use strict';
const canvas = document.getElementById('reactor-canvas');
const gl = canvas.getContext('webgl2',{antialias:true,alpha:false,powerPreference:'high-performance'});
if (!gl) { document.getElementById('canvas-hint').textContent='COMPATIBILITY MODE • WEBGL2 UNAVAILABLE — USE THE RING CONTROLS'; window.ConfluxScene=window.createConfluxFallback?.(canvas)||{setState:()=>{},resetCamera:()=>{},select:()=>{}};return; }
const VS = `#version 300 es
precision highp float;
in vec3 aPosition;in vec3 aNormal;
uniform mat4 uMVP;uniform mat4 uModel;
out vec3 vNormal;out vec3 vWorld;out float vDepth;
void main(){vec4 p=uModel*vec4(aPosition,1.);vWorld=p.xyz;vNormal=normalize(mat3(uModel)*aNormal);gl_Position=uMVP*vec4(aPosition,1.);vDepth=gl_Position.w;}`;
const FS = `#version 300 es
precision highp float;
in vec3 vNormal;in vec3 vWorld;in float vDepth;
uniform vec3 uColor;uniform vec3 uEmissive;uniform float uAlpha;uniform vec3 uCam;
out vec4 outColor;
void main(){
vec3 n=normalize(vNormal);vec3 viewDir=normalize(uCam-vWorld);
vec3 lightA=normalize(vec3(-0.4,1.2,0.7));vec3 lightB=normalize(vec3(0.7,0.8,-0.65));
float diff=max(dot(n,lightA),0.)*.85+max(dot(n,lightB),0.)*.31;
float radialLight=clamp(4./(1.+length(vWorld.xz)*.13),.25,1.8);
float spec=pow(max(dot(reflect(-lightA,n),viewDir),0.),28.)*.24;
float rim=pow(1.-max(0.,dot(n,viewDir)),3.)*.4;
vec3 lit=uColor*(.18+diff*radialLight+spec+rim)+uEmissive;
float fog=clamp((vDepth-20.)/66.,0.,.58);
vec3 color=mix(lit,vec3(.018,.035,.061),fog);
outColor=vec4(color,uAlpha);
}`;
const compile=(source,type)=>{const shader=gl.createShader(type);gl.shaderSource(shader,source);gl.compileShader(shader);if(!gl.getShaderParameter(shader,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(shader));return shader};
let program;
try {program=gl.createProgram();gl.attachShader(program,compile(VS,gl.VERTEX_SHADER));gl.attachShader(program,compile(FS,gl.FRAGMENT_SHADER));gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(program));}catch(e){console.error('WebGL shader initialization failed; activating compatibility mode.',e);window.ConfluxScene=window.createConfluxFallback?.(canvas)||{setState:()=>{},resetCamera:()=>{},select:()=>{}};return;}
gl.useProgram(program);
const at={position:gl.getAttribLocation(program,'aPosition'),normal:gl.getAttribLocation(program,'aNormal')};
const un={MVP:gl.getUniformLocation(program,'uMVP'),model:gl.getUniformLocation(program,'uModel'),color:gl.getUniformLocation(program,'uColor'),emissive:gl.getUniformLocation(program,'uEmissive'),alpha:gl.getUniformLocation(program,'uAlpha'),cam:gl.getUniformLocation(program,'uCam')};
gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LEQUAL);gl.clearColor(.009,.019,.034,1);
const PI=Math.PI, TAU=2*PI;
const palette=['#51e7ff','#ffab3a','#f37bff','#7b9fff'];
const hex=s=>{const v=parseInt(s.replace('#',''),16);return [(v>>16&255)/255,(v>>8&255)/255,(v&255)/255]};
const MAT={obs:'#0a121b',iron:'#182633',iron2:'#243441',iron3:'#394b5a',edge:'#5a6a75',black:'#050a10',silver:'#94a9b6',warm:'#725443'};
// Matrix helpers: column-major, compatible with WebGL.
const ident=()=>new Float32Array([1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]);
const mul=(a,b)=>{const c=new Float32Array(16);for(let j=0;j<4;j++)for(let i=0;i<4;i++){let v=0;for(let k=0;k<4;k++)v+=a[k*4+i]*b[j*4+k];c[j*4+i]=v;}return c};
const model=(x,y,z,sx=1,sy=1,sz=1,ry=0)=>{const c=Math.cos(ry),s=Math.sin(ry);return new Float32Array([c*sx,0,-s*sx,0,0,sy,0,0,s*sz,0,c*sz,0,x,y,z,1])};
const perspective=(fov,aspect,near,far)=>{let f=1/Math.tan(fov/2);let a=ident();a[0]=f/aspect;a[5]=f;a[10]=(far+near)/(near-far);a[11]=-1;a[14]=2*far*near/(near-far);a[15]=0;return a};
const norm=v=>{const l=Math.hypot(...v)||1;return v.map(n=>n/l)};
const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
const dot=(a,b)=>a.reduce((s,v,i)=>s+v*b[i],0);
const lookAt=(eye,at)=>{const z=norm(eye.map((v,i)=>v-at[i]));const x=norm(cross([0,1,0],z));const y=cross(z,x);return new Float32Array([x[0],y[0],z[0],0,x[1],y[1],z[1],0,x[2],y[2],z[2],0,-dot(x,eye),-dot(y,eye),-dot(z,eye),1])};
function geometry(v,n,idx){const vao=gl.createVertexArray();gl.bindVertexArray(vao);const b=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,b);const combined=[];for(let i=0;i<v.length;i+=3)combined.push(v[i],v[i+1],v[i+2],n[i],n[i+1],n[i+2]);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(combined),gl.STATIC_DRAW);gl.enableVertexAttribArray(at.position);gl.vertexAttribPointer(at.position,3,gl.FLOAT,false,24,0);gl.enableVertexAttribArray(at.normal);gl.vertexAttribPointer(at.normal,3,gl.FLOAT,false,24,12);const ib=gl.createBuffer();gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,ib);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,new Uint16Array(idx),gl.STATIC_DRAW);gl.bindVertexArray(null);return{vao,count:idx.length}}
function box(){let v=[],n=[],idx=[];const faces=[[[1,0,0],[[1,-1,-1],[1,1,-1],[1,1,1],[1,-1,1]]],[[-1,0,0],[[-1,-1,1],[-1,1,1],[-1,1,-1],[-1,-1,-1]]],[[0,1,0],[[-1,1,-1],[-1,1,1],[1,1,1],[1,1,-1]]],[[0,-1,0],[[-1,-1,1],[-1,-1,-1],[1,-1,-1],[1,-1,1]]],[[0,0,1],[[1,-1,1],[1,1,1],[-1,1,1],[-1,-1,1]]],[[0,0,-1],[[-1,-1,-1],[-1,1,-1],[1,1,-1],[1,-1,-1]]]];for(const [nor,vs] of faces){const base=v.length/3;for(const p of vs){v.push(...p);n.push(...nor)}idx.push(base,base+1,base+2,base,base+2,base+3)}return geometry(v,n,idx)}
function cylinder(segments=64){const v=[],n=[],idx=[];for(let j=0;j<=segments;j++){const a=j*TAU/segments,c=Math.cos(a),s=Math.sin(a);v.push(c,-.5,s,c,.5,s);n.push(c,0,s,c,0,s);if(j<segments){const i=2*j;idx.push(i,i+1,i+3,i,i+3,i+2)}}for(let end=0;end<2;end++){const y=end? .5:-.5,base=v.length/3;v.push(0,y,0);n.push(0,end?1:-1,0);for(let j=0;j<=segments;j++){const a=j*TAU/segments;v.push(Math.cos(a),y,Math.sin(a));n.push(0,end?1:-1,0);if(j<segments){if(end)idx.push(base,base+j+2,base+j+1);else idx.push(base,base+j+1,base+j+2)}}}return geometry(v,n,idx)}
function torus(segments=80,tubeSegments=10){const v=[],n=[],idx=[];for(let i=0;i<=segments;i++){const a=i*TAU/segments;for(let j=0;j<=tubeSegments;j++){const b=j*TAU/tubeSegments;let c=Math.cos(a),s=Math.sin(a),cb=Math.cos(b),sb=Math.sin(b);v.push((1+.07*cb)*c,.07*sb,(1+.07*cb)*s);n.push(c*cb,sb,s*cb);if(i<segments&&j<tubeSegments){const k=i*(tubeSegments+1)+j,h=k+tubeSegments+1;idx.push(k,h,k+1,h,h+1,k+1)}}}return geometry(v,n,idx)}
function sphere(segments=32,rings=18){let v=[],n=[],idx=[];for(let i=0;i<=rings;i++){const p=i*PI/rings;for(let j=0;j<=segments;j++){const a=j*TAU/segments;const q=[Math.sin(p)*Math.cos(a),Math.cos(p),Math.sin(p)*Math.sin(a)];v.push(...q);n.push(...q);if(i<rings&&j<segments){const k=i*(segments+1)+j,h=k+segments+1;idx.push(k,h,k+1,k+1,h,h+1)}}}return geometry(v,n,idx)}
const geom={box:box(),cyl:cylinder(),torus:torus(),sphere:sphere()};
const objects=[];const moving=[];
function add(kind,x,y,z,sx,sy,sz,color,emissive=null,alpha=1,ry=0,target=objects){const item={kind,x,y,z,sx,sy,sz,ry,color:hex(color),emissive:emissive?hex(emissive):[0,0,0],alpha};target.push(item);return item}
const cube=(x,y,z,sx,sy,sz,color,em=null,ry=0,target=objects)=>add('box',x,y,z,sx,sy,sz,color,em,1,ry,target);
const disk=(x,y,z,r,h,color,em=null,target=objects)=>add('cyl',x,y,z,r,h,r,color,em,1,0,target);
const ring=(x,y,z,r,t,color,em=null,target=objects)=>add('torus',x,y,z,r,t,r,color,em,1,0,target);
function bar(a,b,width,height,color,em=null,target=objects){const dx=b[0]-a[0],dz=b[2]-a[2],len=Math.hypot(dx,dz);return cube((a[0]+b[0])/2,(a[1]+b[1])/2,(a[2]+b[2])/2,len/2,height/2,width/2,color,em,-Math.atan2(dz,dx),target)}
// Architecture — forge platform, ringwork, raised observation decks, monoliths.
disk(0,-1.47,0,17,.74,'#0a111a');disk(0,-1.03,0,16.5,.12,'#1d2a35');ring(0,-.9,0,15.6,2,'#273844');ring(0,-.87,0,15.18,.7,'#192f40','#072b3a');ring(0,-.88,0,14.94,.32,'#244859','#0d3850');
for(let i=0;i<40;i++){const a=i*TAU/40,r=15.9;xzPillar(Math.cos(a)*r,Math.sin(a)*r,a,i)}
function xzPillar(x,z,a,i){cube(x,-.84,z,.57,.12,.21,'#344553',null,-a);if(i%2===0)cube(x,-.61,z,.29,.03,.12,'#7290a1','#142f40',-a)}
for(let i=0;i<16;i++){const a=i*TAU/16,r=20;let x=Math.sin(a)*r,z=Math.cos(a)*r;disk(x,4.3,z,.65,12.8,'#0d1b29');disk(x,11.1,z,.86,.3,'#2a4050');ring(x,11.3,z,.85,.45,'#23475e','#0b364e');if(i%2===0){cube(x,7.1,z,.3,4,.3,'#263746')}}
for(let k=0;k<5;k++)ring(0,9.9+k*.65,0,2.7+k*.23,.28,k%2?'#283f53':'#3d5c70',k%2?'#07233d':'#0e4a7b');
for(let i=0;i<16;i++){const a=i*TAU/16;let x=Math.cos(a)*12.8,z=Math.sin(a)*12.8;bar([x,-.84,z],[Math.cos(a)*14,-.84,Math.sin(a)*14],.045,.035,'#435766',i%2===0?'#174f60':null)}
// Conduits and cable systems.
const stations=[[-5.45,-4.4],[5.45,-4.4],[-5.45,4.45],[5.45,4.45]];
const reactors=[];
for(let i=0;i<4;i++){
 const [x,z]=stations[i],color=palette[i];
 // Twinned structural braces, orange metal rails, 3D conduit segments
 bar([x*.19,-.58,z*.19],[x*.89,-.58,z*.89],.4,.12,'#283746');
 bar([x*.19,-.38,z*.19],[x*.92,-.38,z*.92],.07,.13,'#15485d',color);
 bar([x*.19,-.17,z*.19],[x*.92,-.17,z*.92],.06,.05,color,color);
 disk(x,-.53,z,3.42,.72,'#192634');disk(x,-.15,z,3.15,.12,'#354554');
 ring(x,-.06,z,2.92,2.2,'#374853');ring(x,.10,z,2.84,.85,'#0e1724');ring(x,.12,z,2.72,.55,color,color);
 ring(x,.16,z,2.48,.42,'#8196a0','#132331');ring(x,.20,z,2.26,.73,'#091724');
 disk(x,.23,z,1.83,.12,'#070f1a');ring(x,.32,z,1.95,.7,'#445867');ring(x,.33,z,1.72,.32,color,color);
 disk(x,.34,z,1.38,.20,'#07111c');
 // Kinetic rotor: mechanical concentric rings with alloy vanes and sequenced index markers.
 for(const radius of [1.54,1.26])ring(x,.46,z,radius,.29,'#5a7381');
 for(let j=0;j<12;j++){const angle=j*TAU/12;const rr=2.78;const px=x+rr*Math.cos(angle),pz=z+rr*Math.sin(angle);cube(px,.28,pz,.17,.21,.32,j%3?'#263c4b':'#758999',j%3?null:color,-angle)}
 const rotor={x,z,index:i,angle:0,desired:0,logical:0,ready:false,entries:[],color};
 // Dynamic 6 spokes + pointer and center rune
 for(let j=0;j<6;j++){const a=j*TAU/6;const sx=Math.cos(a),sz=Math.sin(a);rotor.entries.push({angle:a,radius:1.99,y:.55,type:'spoke'});rotor.entries.push({angle:a,radius:1.15,y:.55,type:'pip'});}
 const central=disk(x,.52,z,.63,.22,'#101c2c',color,moving);rotor.disc=central;
 const glyph=ring(x,.67,z,.55,1.8,color,color,moving);rotor.glyph=glyph;
 const wedge=add('box',x,.71,z,.12,.14,.35,color,color,1,0,moving);rotor.pointer=wedge;
 // Fixed target beacon (will be moved to target arc position)
 rotor.target=add('cyl',x+2.7,.61,z,.25,.22,.25,'#fff3d9',color,1,0,moving);
 for(const a of [0,PI/2,PI,1.5*PI]){let sx=Math.cos(a),sz=Math.sin(a);cube(x+sx*3.16,-.16,z+sz*3.16,.33,.3,.52,'#73808b',null,-a)}
 reactors.push(rotor);
}
// Central reactor: stacked gimbals and glowing levitating core.
disk(0,-.44,0,3.4,.8,'#293948');ring(0,.03,0,3.28,2,'#304b5d');ring(0,.18,0,2.8,1.3,'#5296b8','#0d516f');ring(0,.33,0,2.52,.45,'#c1e8fa','#286988');
disk(0,.35,0,2.05,.22,'#06101c');ring(0,.53,0,2.05,.5,'#45bad6','#1b7295');
for(let j=0;j<14;j++){const a=j*TAU/14;cube(Math.cos(a)*2.85,.41,Math.sin(a)*2.85,.19,.37,.29,'#6b8491',null,-a)}
const coreSphere=add('sphere',0,1.43,0,1.25,1.25,1.25,'#83dfff','#2c9bff',1);
const coreHalo=ring(0,1.35,0,1.74,.8,'#66d7ee','#3e8bde',moving);
const orbitA=ring(0,1.4,0,1.95,.6,'#23668d','#1c6694',moving);
const orbitB=ring(0,1.4,0,1.62,.55,'#ffffff','#479cd9',moving);
const coreSpire=add('cyl',0,4.3,0,.135,5.5,.135,'#184e7c','#16517e',.68);
// Stage legs and suspended ceiling arcature.
for(let j=0;j<8;j++){const a=j*TAU/8;cube(Math.cos(a)*3.1,2.0,Math.sin(a)*3.1,.2,1.6,.24,'#3c5361',null,-a)}
// Distant scatter/structural silhouettes.
for(let i=0;i<25;i++){const a=i*TAU/25,r=25+(i%4)*2;cube(Math.cos(a)*r,2+((i*7)%6),Math.sin(a)*r,.8,5+((i*13)%5),.85,'#0a1a2c',null,-a)}
// Star dust uses point sprites in a separate program, for true 3D parallax.
const PVS=`#version 300 es
precision highp float;in vec3 aPos;uniform mat4 uVP;uniform float uTime;out float alpha;void main(){gl_Position=uVP*vec4(aPos,1.);gl_PointSize=clamp(60./gl_Position.w,1.,3.);alpha=.35+.3*sin(uTime+aPos.x*3.);}`;
const PFS=`#version 300 es
precision highp float;in float alpha;out vec4 outColor;void main(){float d=length(gl_PointCoord-.5);outColor=vec4(.40,.83,1.,alpha*smoothstep(.5,.05,d));}`;
let pointProgram=null,pointCount=0,pointVAO=null;
try {pointProgram=gl.createProgram();gl.attachShader(pointProgram,compile(PVS,gl.VERTEX_SHADER));gl.attachShader(pointProgram,compile(PFS,gl.FRAGMENT_SHADER));gl.linkProgram(pointProgram);const stars=[];for(let i=0;i<200;i++){let a=i*2.39996,r=13+((i*97)%190)/10;stars.push(Math.sin(a)*r,1+((i*23)%160)/10,Math.cos(a)*r)}pointCount=stars.length/3;pointVAO=gl.createVertexArray();gl.bindVertexArray(pointVAO);const buf=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buf);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(stars),gl.STATIC_DRAW);const loc=gl.getAttribLocation(pointProgram,'aPos');gl.enableVertexAttribArray(loc);gl.vertexAttribPointer(loc,3,gl.FLOAT,false,12,0);gl.bindVertexArray(null);}catch(e){console.warn('Particles unavailable:',e.message);pointProgram=null;}
// Animation/camera, World <-> screen projection for pointer picking.
let yaw=0,pitch=.55,distance=27.8,targetYaw=0,targetPitch=.55,targetDist=27.8;
let viewportW=0,viewportH=0,vp=ident(),cam=[0,15,23],lastT=0,active=false,sceneSolved=false,reducedMotion=window.matchMedia('(prefers-reduced-motion: reduce)').matches,selected=-1;
function resize(){const width=Math.max(1,canvas.clientWidth),height=Math.max(1,canvas.clientHeight);const dpr=Math.min(window.devicePixelRatio||1,1.6);const w=Math.floor(width*dpr),h=Math.floor(height*dpr);if(w!==canvas.width||h!==canvas.height){canvas.width=w;canvas.height=h;gl.viewport(0,0,w,h)}viewportW=width;viewportH=height}
function project(p){const x=p[0],y=p[1],z=p[2];const w=vp[3]*x+vp[7]*y+vp[11]*z+vp[15];return {x:((vp[0]*x+vp[4]*y+vp[8]*z+vp[12])/w*.5+.5)*viewportW,y:(.5-(vp[1]*x+vp[5]*y+vp[9]*z+vp[13])/w*.5)*viewportH,visible:w>0}}
function draw(item){let mesh=geom[item.kind];if(!mesh)return;const m=model(item.x,item.y,item.z,item.sx,item.sy,item.sz,item.ry),mvp=mul(vp,m);gl.uniformMatrix4fv(un.MVP,false,mvp);gl.uniformMatrix4fv(un.model,false,m);gl.uniform3fv(un.color,item.color);gl.uniform3fv(un.emissive,item.emissive);gl.uniform1f(un.alpha,item.alpha);gl.bindVertexArray(mesh.vao);gl.drawElements(gl.TRIANGLES,mesh.count,gl.UNSIGNED_SHORT,0)}
function updateRotor(r,t){const smooth=reducedMotion?1:.11;r.angle+=(r.desired-r.angle)*smooth;
for(let j=0;j<r.entries.length;j++){let e=r.entries[j],a=e.angle+r.angle;const x=r.x+Math.cos(a)*e.radius,z=r.z+Math.sin(a)*e.radius;
if(!r.vanes)r.vanes=[];
if(!r.vanes[j]){r.vanes[j]=add('box',x,e.y,z,e.type==='spoke'?.23:.18,.08,e.type==='spoke'?.42:.19,e.type==='spoke'?'#8aa2b0':'#d2eaff',e.type==='spoke'?null:r.color,1,-a,moving)}
const v=r.vanes[j];v.x=x;v.z=z;v.ry=-a;}
r.pointer.x=r.x+Math.cos(r.angle)*.95;r.pointer.z=r.z+Math.sin(r.angle)*.95;r.pointer.ry=-r.angle;
r.glyph.y=.69+Math.sin(t*1.4+r.index)*.015;
}
function render(timestamp){const t=timestamp/1000,dt=Math.min(.1,t-lastT||.016);lastT=t;if(document.hidden||!document.body.classList.contains('native-mode')){requestAnimationFrame(render);return;}resize();
yaw+=(targetYaw-yaw)*.09;pitch+=(targetPitch-pitch)*.12;distance+=(targetDist-distance)*.12;
const cp=Math.cos(pitch);cam=[Math.sin(yaw)*cp*distance,Math.sin(pitch)*distance+1.5,Math.cos(yaw)*cp*distance];let view=lookAt(cam,[0,.6,0]);let proj=perspective(51*PI/180,viewportW/viewportH,.2,180);vp=mul(proj,view);
gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.useProgram(program);gl.uniform3fv(un.cam,cam);gl.disable(gl.BLEND);
coreSphere.sy=1.1+Math.sin(t*2.8)*(sceneSolved?.23:.06);coreSphere.sx=coreSphere.sz=coreSphere.sy;
coreHalo.ry=t*.3;orbitA.ry=t*.2;orbitB.ry=-t*.26;
for(const r of reactors)updateRotor(r,t);
for(const o of objects)draw(o);for(const o of moving)draw(o);
if(pointProgram){gl.useProgram(pointProgram);gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE);gl.depthMask(false);gl.uniformMatrix4fv(gl.getUniformLocation(pointProgram,'uVP'),false,vp);gl.uniform1f(gl.getUniformLocation(pointProgram,'uTime'),t);gl.bindVertexArray(pointVAO);gl.drawArrays(gl.POINTS,0,pointCount);gl.depthMask(true);gl.disable(gl.BLEND)}
requestAnimationFrame(render)}
function setState(data){active=data?.phase==='playing'&&!data.paused;sceneSolved=data?.phase==='intermission'&&data?.result==='solved';if(data?.positions){reactors.forEach((r,i)=>{const pos=data.positions[i];if(!r.ready){r.logical=pos;r.angle=r.desired=(pos*TAU/6);r.ready=true}else if(pos!==r.logical){let d=(pos-r.logical+6)%6;if(d>3)d-=6;r.desired+=d*TAU/6;r.logical=pos}const targetIndex=data.target?.[i]??0,a=targetIndex*TAU/6;r.target.x=r.x+2.68*Math.cos(a);r.target.z=r.z+2.68*Math.sin(a);r.target.color=hex(r.color);r.target.emissive=hex('#fff6d3');});}}
let dragging=false,pointer=null,moved=false;
canvas.addEventListener('pointerdown',e=>{dragging=true;moved=false;pointer={x:e.clientX,y:e.clientY};canvas.setPointerCapture(e.pointerId)});
canvas.addEventListener('pointermove',e=>{if(!dragging||!pointer)return;const dx=e.clientX-pointer.x,dy=e.clientY-pointer.y;pointer={x:e.clientX,y:e.clientY};if(Math.abs(dx)+Math.abs(dy)>1)moved=true;targetYaw+=dx*.006;targetPitch=Math.max(.27,Math.min(1.32,targetPitch+dy*.0048));});
canvas.addEventListener('pointerup',e=>{if(!dragging)return;dragging=false;if(!moved){let best=-1,bd=Infinity;for(let i=0;i<4;i++){let r=reactors[i],p=project([r.x,1,r.z]);let d=Math.hypot(p.x-e.clientX,p.y-e.clientY);if(d<bd){bd=d;best=i}}if(best>=0&&bd<130){selected=best;window.dispatchEvent(new CustomEvent('conflux-select',{detail:{dial:best}}));}}});
canvas.addEventListener('wheel',e=>{e.preventDefault();targetDist=Math.min(43,Math.max(18,targetDist+e.deltaY*.025))},{passive:false});
function select(i){selected=i;}function resetCamera(){targetYaw=0;targetPitch=.55;targetDist=27.8}
window.ConfluxScene={setState,resetCamera,select,palette};
requestAnimationFrame(render);
})();

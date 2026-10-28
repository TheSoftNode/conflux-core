/* 2D compatibility view, used ONLY if this device blocks WebGL2.
   The game still uses the same authoritative multiplayer game state. */
window.createConfluxFallback=function(canvas){
 const ctx=canvas.getContext('2d');if(!ctx)return{setState(){},resetCamera(){},select(){}};
 let state=null,theta=0,viewTheta=0,zoom=1,selected=-1;
 // Clockwise station order: Aether (TL), Ember (TR), Pulse (BR), Prism (BL).
 const hues=['#4ce6ff','#ffab3c','#84a4ff','#ec78ff'],pts=[[-5.55,-4.4],[5.55,-4.4],[5.55,4.4],[-5.55,4.4]];
 const TAU=Math.PI*2;let w=0,h=0,s=1,frame=0;
 function resize(){const dpr=Math.min(devicePixelRatio||1,1.5);w=canvas.clientWidth;h=canvas.clientHeight;let nw=Math.floor(w*dpr),nh=Math.floor(h*dpr);if(canvas.width!==nw||canvas.height!==nh){canvas.width=nw;canvas.height=nh;}ctx.setTransform(dpr,0,0,dpr,0,0);s=Math.min(w/30,h/21)*zoom;}
 function point(x,z,y=0){let a=viewTheta,c=Math.cos(a),sn=Math.sin(a),rx=x*c-z*sn,rz=x*sn+z*c;return [w*.5+rx*s,h*.54+rz*s*.47-y*s*.82,1-rz*.014];}
 function ellipse(x,y,rx,ry,fill,stroke=null,lw=1){ctx.beginPath();ctx.ellipse(x,y,rx,ry,0,0,TAU);if(fill){ctx.fillStyle=fill;ctx.fill()}if(stroke){ctx.strokeStyle=stroke;ctx.lineWidth=lw;ctx.stroke()}}
 function line(x,y,x2,y2,color,width=1,blur=0){ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(x2,y2);ctx.strokeStyle=color;ctx.lineWidth=width;ctx.shadowColor=color;ctx.shadowBlur=blur;ctx.stroke();ctx.shadowBlur=0}
 function arc(x,y,r,ratio,color,width,start=0,end=TAU){ctx.beginPath();ctx.ellipse(x,y,r,r*ratio,0,start,end);ctx.strokeStyle=color;ctx.lineWidth=width;ctx.shadowBlur=12;ctx.shadowColor=color;ctx.stroke();ctx.shadowBlur=0}
 function scene(t){resize();ctx.clearRect(0,0,w,h);const sky=ctx.createRadialGradient(w/2,h*.43,25,w/2,h*.54,Math.max(w,h)*.8);sky.addColorStop(0,'#143147');sky.addColorStop(.35,'#0a1627');sky.addColorStop(1,'#01050d');ctx.fillStyle=sky;ctx.fillRect(0,0,w,h);
 // Vertical machine architecture, bridges and reactor cathedral.
 for(let i=0;i<15;i++){const x=(i/14)*w;const near=i%2===0;ctx.fillStyle=near?'#07131f':'#091b2b';ctx.fillRect(x-20,0,near?28:18,h*.52);ctx.fillStyle='#24465c';ctx.fillRect(x-12,0,2,h*.33);line(x-17,h*.09,x-17,h*.47,'#0d344c',3);if(i%3===0)line(x+13,0,x+13,h*.25,'#d990455a',4,8)}
 for(let i=0;i<68;i++){const px=(i*147.37)%w,py=(i*79.17)%(h*.8),r=.4+(i%3)*.3;ellipse(px,py,r,r,'#8bd8ee81')}
 const center=point(0,0),baseR=15*s;ellipse(center[0],center[1]+s*.15,baseR,baseR*.49,'#111c2b','#334353',3);
 for(let k=0;k<5;k++)arc(center[0],center[1]-s*.06,baseR-k*s*.17,.49,k%2?'#1a3949':'#41515d',k===0?8:3);
 for(let k=0;k<46;k++){let a=k*TAU/46;const x=center[0]+Math.cos(a)*baseR,y=center[1]+Math.sin(a)*baseR*.48;ellipse(x,y,3,2,k%4===0?'#ffbc5b':'#244453');}
 // Draw colorful power conduits first, then circular machinery front-to-back.
 pts.forEach(([x,z],i)=>{const p=point(x,z),p2=point(0,0),color=hues[i];line(p[0],p[1]-8,p2[0],p2[1]-10,'#344e62',19);line(p[0],p[1]-10,p2[0],p2[1]-10,color,5,20);line(p[0],p[1]-10,p2[0],p2[1]-10,'#e6fcff',1,6)});
 const order=[0,1,2,3].sort((a,b)=>pts[a][1]-pts[b][1]);
 order.forEach(i=>{const [x,z]=pts[i],p=point(x,z),R=2.72*s,color=hues[i],raw=state?.positions?.[i]??i,goal=state?.target?.[i]??i;const [cx,cy]=p;
 ctx.shadowBlur=38;ctx.shadowColor='#000';ellipse(cx,cy+12,R*1.15,R*.48,'#050b14');ctx.shadowBlur=0;
 ellipse(cx,cy+6,R*1.1,R*.44,'#223340','#667686',3);ellipse(cx,cy+1,R,R*.42,'#060d17','#485e6c',4);
 for(let j=0;j<4;j++)arc(cx,cy,R*(.92-j*.08),.42,j%2===0?color:'#374d62',j===0?4:3);
 for(let j=0;j<24;j++){let a=j*TAU/24;let rr=R*.87;let xx=cx+Math.cos(a)*rr,yy=cy+Math.sin(a)*rr*.42;ellipse(xx,yy,j%3===0?3:2,2,j%3===0?color:'#536c79');}
 const a=raw*TAU/6-t*.02;ctx.save();ctx.translate(cx,cy);ctx.rotate(a);ctx.strokeStyle='#adcbd8';ctx.lineWidth=4;ellipse(0,0,R*.48,R*.205,'#07101d',null,0);
 for(let k=0;k<6;k++){const b=k*TAU/6;line(Math.cos(b)*R*.44,Math.sin(b)*R*.17,Math.cos(b)*R*.66,Math.sin(b)*R*.26,color,7,14)}
 ctx.restore();
 // Target beacon and live marker
 let angle=goal*TAU/6;let tx=cx+Math.cos(angle)*R*.97,ty=cy+Math.sin(angle)*R*.408;
 ellipse(tx,ty,8,5,'#fff2c1',color,3);
 ellipse(cx,cy,R*.26,R*.12,'#0e2635',color,3);ctx.fillStyle=color;ctx.shadowBlur=16;ctx.shadowColor=color;ctx.font=`bold ${Math.max(15,R*.3)}px sans-serif`;ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(['✦','◆','⬢','✳','◈','●'][raw],cx,cy+2);if(state?.positions&&raw===goal)arc(cx,cy,R*.36,.42,'#6cffc6',3);ctx.shadowBlur=0;
 if(selected===i)arc(cx,cy,R*1.13,.44,'#f8ffff',2,0,TAU);
 });
 // Central machine, floating nucleus and upper ring gantry.
 const [cx,cy]=center;const R=3.15*s;ellipse(cx,cy+12,R,R*.43,'#030a13','#4b7386',4);for(let k=0;k<4;k++)arc(cx,cy+7,R*(1-k*.18),.43,k===0?'#6bbdd4':k===2?'#9cefff':'#2f7895',6);
 let radial=ctx.createRadialGradient(cx,cy-s*.6,4,cx,cy-s*.6,R*.55);radial.addColorStop(0,'#ffffff');radial.addColorStop(.2,'#c5faff');radial.addColorStop(.48,'#53b1ff');radial.addColorStop(1,'#3d79f300');ctx.fillStyle=radial;ctx.beginPath();ctx.arc(cx,cy-s*.6,R*.58,0,TAU);ctx.fill();arc(cx,cy-s*.5,R*.55,.4,'#b8eeff',4);
 const beam=ctx.createLinearGradient(cx,0,cx,cy);beam.addColorStop(0,'#5dd8ff07');beam.addColorStop(.7,'#74d9ff88');beam.addColorStop(1,'#d4ffffe2');ctx.fillStyle=beam;ctx.fillRect(cx-6,0,12,cy-s*.45);
 for(let k=0;k<5;k++)arc(cx,cy-s*5-k*s*.55,s*(2+k*.24),.28,'#426581',3);
 ctx.textAlign='center';ctx.fillStyle='#89c6d3';ctx.font='10px sans-serif';ctx.fillText('REACTOR ARRAY // V.02',cx,cy+R*.53);
 }
 function animate(t){viewTheta+=(theta-viewTheta)*.05;scene(t*.001);frame=requestAnimationFrame(animate)}requestAnimationFrame(animate);
 canvas.addEventListener('pointerdown',e=>canvas.__p={x:e.clientX,y:e.clientY});
 canvas.addEventListener('pointerup',e=>{const p=canvas.__p;if(!p)return;const dx=e.clientX-p.x;if(Math.abs(dx)>15){theta+=dx*.006;return}let best=-1,bd=Infinity;for(let i=0;i<4;i++){const q=point(...pts[i]),d=Math.hypot(q[0]-e.clientX,q[1]-e.clientY);if(d<bd){best=i;bd=d}}if(bd<125){selected=best;window.dispatchEvent(new CustomEvent('conflux-select',{detail:{dial:best}}))}});
 canvas.addEventListener('wheel',e=>{e.preventDefault();zoom=Math.min(1.4,Math.max(.7,zoom-e.deltaY*.0004))},{passive:false});
 return {setState(s){state=s},resetCamera(){theta=0;zoom=1},select(i){selected=i},palette:hues};
};

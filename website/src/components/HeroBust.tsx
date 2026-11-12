import { useEffect, useMemo } from 'react';
import { useThree } from '@react-three/fiber';
import { Html, OrbitControls, useGLTF } from '@react-three/drei';
import * as T from 'three';
import { channelInfo, core } from '../data/research';

export function HeroBust({selected,onSelect}:{selected:string;onSelect:(name:string)=>void}) {
 const {scene:asset}=useGLTF('./models/neurolink-head-bust.glb');
 const {camera}=useThree();
 useEffect(()=>{camera.position.set(-3,1.15,5);camera.lookAt(0,0,0);},[camera]);
 const {model,equipment,sensors}=useMemo(()=>{
  const model=asset.clone(true);const bounds=new T.Box3().setFromObject(model);const scale=2.8/bounds.getSize(new T.Vector3()).y;
  model.position.copy(bounds.getCenter(new T.Vector3())).multiplyScalar(-scale);model.scale.setScalar(scale);
  model.traverse(o=>{if(o instanceof T.Mesh){o.geometry=o.geometry.clone();o.geometry.computeVertexNormals();o.material=new T.MeshStandardMaterial({color:'#ECEEF0',roughness:.7});}});model.updateMatrixWorld(true);
  const ray=new T.Raycaster();const origin=new T.Vector3(0,.65,0);
  const surface=(theta:number,phi:number)=>{const d=new T.Vector3(Math.sin(theta)*Math.cos(phi),Math.cos(theta),Math.sin(theta)*Math.sin(phi));ray.set(origin.clone().addScaledVector(d,4),d.clone().negate());const h=ray.intersectObject(model,true)[0];return h?{p:h.point,n:h.face!.normal.clone().transformDirection(h.object.matrixWorld)}:null;};
  const channels:[string,number,number][]=[['Fp1',1.1,1.92],['Fp2',1.1,1.22],['F7',1.1,2.65],['F3',.65,2.2],['F4',.65,.94],['F8',1.1,.49],['T7',1.5,3.14],['C3',.8,3.14],['Cz',0,0],['C4',.8,0],['T8',1.5,0],['P7',1.1,3.7],['Pz',.65,4.71],['P8',1.1,5.72],['O1',1.3,4.3],['O2',1.3,5.12]];
  const equipment=new T.Group();const cable=new T.MeshStandardMaterial({color:'#E6EBEF',roughness:.6});
  const sensors=channels.flatMap(([name,theta,phi])=>{const s=surface(theta,phi);if(!s)return [];const points:T.Vector3[]=[];for(let i=0;i<=32;i++){const p=surface(theta*i/32,phi);if(p)points.push(p.p.addScaledVector(p.n,.022));}if(points.length>2)equipment.add(new T.Mesh(new T.TubeGeometry(new T.CatmullRomCurve3(points),64,.008,8,false),cable));return [{name,position:s.p.addScaledVector(s.n,.03),rotation:new T.Quaternion().setFromUnitVectors(new T.Vector3(0,1,0),s.n)}];});
  const verts:number[]=[];const indices:number[]=[];for(let r=0;r<=20;r++)for(let c=0;c<=64;c++){const s=surface(.02+r/20*1.27,c/64*Math.PI*2);const p=s?s.p.addScaledVector(s.n,.009):origin;verts.push(p.x,p.y,p.z);}for(let r=0;r<20;r++)for(let c=0;c<64;c++){const a=r*65+c;indices.push(a,a+65,a+1,a+1,a+65,a+66);}const geometry=new T.BufferGeometry();geometry.setAttribute('position',new T.Float32BufferAttribute(verts,3));geometry.setIndex(indices);geometry.computeVertexNormals();equipment.add(new T.Mesh(geometry,new T.MeshStandardMaterial({color:'#E5E9EC',transparent:true,opacity:.22,side:T.DoubleSide,depthWrite:false,roughness:.8})));
  const s=surface(1.4,3.6);if(s){const module=new T.Mesh(new T.BoxGeometry(.14,.23,.08),new T.MeshStandardMaterial({color:'#B8C4CE',roughness:.55,metalness:.3}));module.position.copy(s.p).addScaledVector(s.n,.06);module.quaternion.setFromUnitVectors(new T.Vector3(0,0,1),s.n);equipment.add(module);}
  return {model,equipment,sensors};
 },[asset]);
 return <><hemisphereLight args={['#ffffff','#879b9a',2]}/><directionalLight position={[-3,5,4]} intensity={3}/><directionalLight position={[4,2,2]} intensity={1}/><directionalLight position={[1,4,-3]} intensity={2}/><primitive object={model}/><primitive object={equipment}/>{sensors.map(s=><group key={s.name} position={s.position} quaternion={s.rotation} onClick={e=>{e.stopPropagation();onSelect(s.name);}}><mesh><cylinderGeometry args={[.085,.085,.045,32]}/><meshStandardMaterial color={selected===s.name?'#527C98':'#DCE5EB'} metalness={.4} roughness={.45}/></mesh><mesh position={[0,.029,0]}><cylinderGeometry args={[.052,.052,.012,32]}/><meshStandardMaterial color={core.includes(s.name)?'#39776F':'#A8B8C5'} roughness={.5}/></mesh>{core.includes(s.name)&&<Html center position={[0,.14,0]}><button className={`electrode ${selected===s.name?'selected':''}`} title={channelInfo(s.name)} onClick={()=>onSelect(s.name)}>{s.name}</button></Html>}</group>)}<OrbitControls makeDefault enablePan={false} enableZoom={false}/></>;
}

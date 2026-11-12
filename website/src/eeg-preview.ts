import * as T from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
const scene = new T.Scene();
const renderer = new T.WebGLRenderer({antialias:true,alpha:true});
renderer.setSize(innerWidth,innerHeight);renderer.setPixelRatio(Math.min(devicePixelRatio,2));document.body.append(renderer.domElement);
const camera=new T.PerspectiveCamera(34,innerWidth/innerHeight,.01,100);
const controls=new OrbitControls(camera,renderer.domElement);controls.target.set(0,0,0);controls.enableDamping=true;
const views:Record<string,number[]>={'3/4':[-3,1.4,5],'정면':[0,.3,5],'측면':[5,.3,0],'후면':[0,.3,-5]};
for(const [name,pos] of Object.entries(views)){const b=document.createElement('button');b.textContent=name;b.onclick=()=>{camera.position.set(pos[0],pos[1],pos[2]);controls.update();};document.querySelector('#views')!.append(b);}
camera.position.set(-3,1.4,5);
scene.add(new T.HemisphereLight(0xffffff,0x879b9a,2));
for(const [x,y,z,power] of [[-3,5,4,3],[4,2,2,1],[1,4,-3,2]]){const l=new T.DirectionalLight(0xffffff,power);l.position.set(x,y,z);scene.add(l);}
const equipment=new T.Group();scene.add(equipment);
document.querySelector('#equipment')!.addEventListener('click',e=>{equipment.visible=!equipment.visible;(e.target as HTMLElement).textContent=equipment.visible?'EEG 장비 숨기기':'EEG 장비 표시';});
const mat=(color:string,metalness=0)=>new T.MeshStandardMaterial({color,roughness:.55,metalness});
new GLTFLoader().load('/models/neurolink-head-bust.glb',g=>{
 const model=g.scene;const box=new T.Box3().setFromObject(model);const center=box.getCenter(new T.Vector3());const size=box.getSize(new T.Vector3());const scale=2.8/size.y;
 model.position.copy(center).multiplyScalar(-scale);model.scale.setScalar(scale);model.traverse(o=>{if(o instanceof T.Mesh){o.geometry.computeVertexNormals();o.material=mat('#ECEEF0');}});scene.add(model);model.updateMatrixWorld(true);
 const ray=new T.Raycaster();const scalpCenter=new T.Vector3(0,.65,0);
 function surface(theta:number,phi:number){const dir=new T.Vector3(Math.sin(theta)*Math.cos(phi),Math.cos(theta),Math.sin(theta)*Math.sin(phi));ray.set(scalpCenter.clone().addScaledVector(dir,4),dir.clone().negate());const hit=ray.intersectObject(model,true)[0];if(!hit)return null;const normal=hit.face!.normal.clone().transformDirection(hit.object.matrixWorld);return {p:hit.point,n:normal};}
 const channels:[string,number,number][]=[['Fp1',1.1,1.92],['Fp2',1.1,1.22],['F7',1.1,2.65],['F3',.65,2.2],['F4',.65,.94],['F8',1.1,.49],['T7',1.5,3.14],['C3',.8,3.14],['Cz',0,0],['C4',.8,0],['T8',1.5,0],['P7',1.1,3.7],['Pz',.65,4.71],['P8',1.1,5.72],['O1',1.3,4.3],['O2',1.3,5.12]];
 for(const [name,theta,phi] of channels){const s=surface(theta,phi);if(!s)continue;const group=new T.Group();group.position.copy(s.p).addScaledVector(s.n,.025);group.quaternion.setFromUnitVectors(new T.Vector3(0,1,0),s.n);const housing=new T.Mesh(new T.CylinderGeometry(.085,.085,.045,32),mat('#DCE5EB',.4));group.add(housing);const contact=new T.Mesh(new T.CylinderGeometry(.052,.052,.012,32),mat(['F3','F4','C3','Cz','C4'].includes(name)?'#39776F':'#A8B8C5',.25));contact.position.y=.029;group.add(contact);equipment.add(group);
 const points:T.Vector3[]=[];for(let i=0;i<=24;i++){const p=surface(theta*i/24,phi);if(p)points.push(p.p.addScaledVector(p.n,.018));}if(points.length>2)equipment.add(new T.Mesh(new T.TubeGeometry(new T.CatmullRomCurve3(points),64,.009,8,false),mat('#E6EBEF')));
 }
 document.querySelector('#status')!.textContent='neurolink-head-bust.glb · 아이보리 재질 · 16채널 장비 1차 배치';
},undefined,e=>{document.querySelector('#status')!.textContent=String(e);});
addEventListener('resize',()=>{camera.aspect=innerWidth/innerHeight;camera.updateProjectionMatrix();renderer.setSize(innerWidth,innerHeight);});
renderer.setAnimationLoop(()=>{controls.update();renderer.render(scene,camera);});

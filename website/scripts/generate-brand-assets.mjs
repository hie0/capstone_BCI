// Resize/crop only; supplied artwork is never regenerated or recolored.
import { chromium } from 'playwright-core';
import { readFileSync, writeFileSync, copyFileSync, mkdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
const [logoPath,symbolPath]=process.argv.slice(2);
if(!logoPath||!symbolPath)throw new Error('Usage: node scripts/generate-brand-assets.mjs LOGO.png SYMBOL.png');
const output=resolve('public/brand');mkdirSync(output,{recursive:true});
const inputs=[logoPath,symbolPath].map(p=>readFileSync(p));
const browser=await chromium.launch({channel:'chrome',headless:true});
let result;
try {
 const page=await browser.newPage();
 result=await page.evaluate(async sources=>{
  const images=await Promise.all(sources.map(async source=>{const image=new Image();image.src=source;await image.decode();return image;}));
  const bounds=images.map(image=>{
   const c=document.createElement('canvas');c.width=image.width;c.height=image.height;const ctx=c.getContext('2d',{willReadFrequently:true});ctx.drawImage(image,0,0);
   const pixels=ctx.getImageData(0,0,c.width,c.height).data;let left=image.width,top=image.height,right=0,bottom=0;
   for(let y=0;y<image.height;y++)for(let x=0;x<image.width;x++)if(pixels[(y*image.width+x)*4+3]>16){left=Math.min(left,x);top=Math.min(top,y);right=Math.max(right,x);bottom=Math.max(bottom,y);}
   const pad=Math.ceil(Math.max(right-left,bottom-top)*0.012);left=Math.max(0,left-pad);top=Math.max(0,top-pad);right=Math.min(image.width-1,right+pad);bottom=Math.min(image.height-1,bottom+pad);
   return {left,top,width:right-left+1,height:bottom-top+1,originalWidth:image.width,originalHeight:image.height};
  });
  const resize=(image,box,width,height,inset=0)=>{const c=document.createElement('canvas');c.width=width;c.height=height;const ctx=c.getContext('2d');ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality='high';const scale=Math.min((width-2*inset)/box.width,(height-2*inset)/box.height);const w=box.width*scale,h=box.height*scale;ctx.drawImage(image,box.left,box.top,box.width,box.height,(width-w)/2,(height-h)/2,w,h);return c.toDataURL('image/png').split(',')[1];};
  const width=Math.min(720,bounds[0].width),height=Math.round(width*bounds[0].height/bounds[0].width);
  const files={'neurolink-logo-header.png':resize(images[0],bounds[0],width,height)};
  for(const size of [16,32,48,180])files[size===180?'apple-touch-icon.png':`favicon-${size}x${size}.png`]=resize(images[1],bounds[1],size,size,Math.max(1,Math.round(size*.03)));
  return {files,bounds,header:{width,height}};
 },inputs.map(b=>'data:image/png;base64,'+b.toString('base64')));
}finally{await browser.close();}
copyFileSync(logoPath,resolve(output,'neurolink-logo.png'));copyFileSync(symbolPath,resolve(output,'neurolink-symbol.png'));
const generated={};for(const [name,data]of Object.entries(result.files)){const bytes=Buffer.from(data,'base64');writeFileSync(resolve(output,name),bytes);generated[name]={bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex')};}
const sizes=[16,32,48],chunks=sizes.map(n=>readFileSync(resolve(output,`favicon-${n}x${n}.png`)));
const directory=Buffer.alloc(6+16*sizes.length);directory.writeUInt16LE(1,2);directory.writeUInt16LE(sizes.length,4);let offset=directory.length;
sizes.forEach((size,i)=>{const p=6+i*16;directory[p]=size;directory[p+1]=size;directory.writeUInt16LE(1,p+4);directory.writeUInt16LE(32,p+6);directory.writeUInt32LE(chunks[i].length,p+8);directory.writeUInt32LE(offset,p+12);offset+=chunks[i].length;});
writeFileSync(resolve(output,'favicon.ico'),Buffer.concat([directory,...chunks]));
writeFileSync(resolve(output,'asset-info.json'),JSON.stringify({sourceHashes:inputs.map(b=>createHash('sha256').update(b).digest('hex')),bounds:result.bounds,header:result.header,generated},null,2)+'\n');
console.log(JSON.stringify({bounds:result.bounds,header:result.header,generated},null,2));

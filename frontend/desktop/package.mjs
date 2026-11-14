import { cp, mkdir, rename, writeFile, access } from 'node:fs/promises';
import path from 'node:path';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
const output = path.resolve('release/Marswalk-win32-x64');
await access('node_modules/electron/dist/electron.exe');
await mkdir(output, { recursive:true });
const executable = path.join(output,'Marswalk.exe');
const existing = await access(executable).then(()=>true,()=>false);
if (!existing) {
  await cp('node_modules/electron/dist', output, { recursive:true });
  await rename(path.join(output,'electron.exe'), executable);
} else {
  const hash = buffer => createHash('sha256').update(buffer).digest('hex');
  if (hash(await readFile(executable)) !== hash(await readFile('node_modules/electron/dist/electron.exe'))) throw new Error('Runtime-ul Electron s-a schimbat. Închide aplicația și creează distribuția într-un folder release nou.');
}
const appDir = path.join(output,'resources/app');
await mkdir(path.join(appDir,'desktop'), { recursive:true });
await cp('dist',path.join(appDir,'dist'),{recursive:true});
await cp('desktop/main.cjs',path.join(appDir,'desktop/main.cjs'));
await writeFile(path.join(appDir,'package.json'),JSON.stringify({name:'marswalk',version:'0.1.0',main:'desktop/main.cjs'}));
console.log(path.join(output,'Marswalk.exe'));

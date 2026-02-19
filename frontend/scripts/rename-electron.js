import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const distElectron = path.join(__dirname, '..', 'dist-electron');

if (!fs.existsSync(distElectron)) {
  console.error('dist-electron directory not found');
  process.exit(1);
}

const files = fs.readdirSync(distElectron);

files.forEach(file => {
  if (file.endsWith('.js')) {
    const oldPath = path.join(distElectron, file);
    const newPath = path.join(distElectron, file.replace('.js', '.cjs'));
    
    if (fs.existsSync(oldPath) && !fs.existsSync(newPath)) {
      fs.renameSync(oldPath, newPath);
      console.log(`Renamed: ${file} -> ${file.replace('.js', '.cjs')}`);
    }
  }
});

console.log('Electron files renamed successfully');
